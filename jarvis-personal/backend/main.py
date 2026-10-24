import os
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
import logging
import re
import time
from uuid import uuid4

from backend.core.brain import process_input
from backend.core import database as _database
from backend.core.database import init_database
from backend.core.events import add_event, get_events
from backend.core.logs import get_logs
from backend.finance.routes import router as finance_router
from backend.goals.routes import router as goals_router
from backend.decision_engine.routes import router as decision_router
from backend.reports.routes import router as reports_router
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from backend.transactions.routes import router as transactions_router
from backend.importers.routes import router as importers_router
from backend.advisor.routes import router as advisor_router
from backend.auth.routes import router as auth_router
from backend.ai.routes import router as ai_router
from backend.email_monitor.routes import router as email_monitor_router
from backend.notifications.routes import router as notifications_router
from backend.finance.daily_history_routes import router as financial_history_router
from backend.finance.investment_center import router as investment_center_router
from backend.finance.business_center import router as business_center_router
from backend.auth.current_user import require_owner, reset_current_user, set_current_user
from backend.auth.service import authenticate_access_token
from backend.auth.owner_bridge import authenticate_owner_bridge_token
from backend.users_admin.routes import router as users_admin_router
from backend.auth.owner_bridge_routes import router as owner_bridge_router
from backend.user_product.routes import router as user_product_router
from backend.deployment_monitor.routes import router as deployment_monitor_router
from backend.integrations.ibkr_readonly import router as ibkr_readonly_router
from backend.product_ops.posthog_events import capture_backend_event_later
from backend.core import observability as ops
from backend.product_ops.observability_routes import router as observability_router
from backend.product_ops.routes import router as product_ops_router
from backend.product_ops.store_routes import router as store_billing_router
from backend.financial_lifecycle.routes import router as financial_lifecycle_router
from backend.core.idempotency import (
    IDEMPOTENCY_KEY_PATTERN,
    OperationSuperseded,
    activate_operation,
    complete_operation,
    deactivate_operation,
    is_recoverable_operation,
    request_hash,
    reserve_operation,
    safe_abandon_operation,
)
from backend.core.feature_flags import disabled_feature_for_request
from backend.core.i18n import is_dincr_users_path, language_for_request, reset_dincr_users, reset_language, set_dincr_users, set_language, tx, use_language
from backend.core import write_limit

# The web app is the only process exempt from declaring a workspace for deletes.
_database.APPLICATION_NAME = os.getenv("DINCR_DB_APPLICATION_NAME", "dincr-backend")

app = FastAPI(title="Jarvis Core")
logger = logging.getLogger("jarvis.api")

ALLOWED_APP_ORIGINS = {
    "http://localhost",
    "https://localhost",
    "capacitor://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://jarvis-frontend-delta.vercel.app",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_APP_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The offline queue reads these to tell "still processing" from a final failure.
    expose_headers=["X-Idempotency-Status", "X-Idempotency-Replayed", "X-Request-ID", "Retry-After"],
)


PUBLIC_PATHS = {
    "/",
    "/status",
    "/health/live",
    "/health/ready",
    "/product-ops/release-policy",
    "/auth/health",
    "/email-monitor/cron",
    "/email-monitor/gmail-watch",
    "/email-monitor/gmail-push",
    "/user-product/vip/gmail/callback",
    # Microsoft redirects the system browser here without a DINCR session; the
    # signed state identifies the account, as in the Gmail callback.
    "/user-product/vip/mail/microsoft/callback",
    "/user-product/vip/gmail/maintenance",
    "/user-product/vip/gmail/push",
    "/notifications/cron",
    "/financial-history/cron",
    # App Store / Google Play: authenticated by Apple's signature, Google's OIDC
    # token or the cron secret (backend/product_ops/store_verification.py).
    "/product-ops/billing/store/apple/notifications",
    "/product-ops/billing/store/google/notifications",
    "/product-ops/billing/store/cron",
    "/deployment-monitor/webhook/github",
    "/deployment-monitor/webhook/vercel",
    "/deployment-monitor/webhook/render",
    "/integrations/ibkr/snapshot",
    "/integrations/ibkr/flex/cron",
    "/internal/owner-bridge/verify",
}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def _request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", "")
    if existing:
        return existing
    supplied = request.headers.get("X-Request-ID", "").strip()
    value = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
    request.state.request_id = value
    return value


# One line that explains an unexpected error without leaking data (moved to core so
# every module can log failures the same way).
_safe_exception_summary = ops.exception_summary


def _internal_error_payload(error_id: str) -> dict[str, str]:
    return {
        "detail": "Ocurrió un error interno. Intentá nuevamente.",
        "error_id": error_id,
        "request_id": error_id,
    }


def _report_server_error(request: Request, status_code: int, exc: Exception) -> None:
    """Anonymous reliability signal: route template, method, status and exception type only."""
    route = getattr(request.scope.get("route"), "path", None)
    capture_backend_event_later("server_error", {
        "route": route, "method": request.method, "status_code": status_code, "exception_type": type(exc).__name__,
    })
    # A deliberate 503 (feature paused, store not enabled, provider asked to retry) is a
    # decision, not an outage: logged, never alerted. Unhandled errors alert (deduplicated).
    if type(exc).__name__ == "ClientDisconnect":
        # The client hung up mid-upload (mobile networks do): nothing failed on our side.
        ops.report("api", "client_disconnected", "info", route=route or ops.normalize_route(request.url.path))
        return
    deliberate = isinstance(exc, HTTPException) and status_code == 503
    # A database outage pages once through database.connect_failed/unreachable; per-route
    # failures stay ERROR so one outage is not one CRITICAL page per endpoint.
    ops.report("api", "server_error", "warning" if deliberate else "error",
               route=route or ops.normalize_route(request.url.path), method=request.method, status=status_code,
               error_class=type(exc).__name__, error_code=getattr(exc, "pgcode", None),
               request_id=getattr(getattr(request, "state", None), "request_id", None))


@app.exception_handler(HTTPException)
async def safe_http_error_handler(request: Request, exc: HTTPException):
    if exc.status_code < 500:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    error_id = _request_id(request)
    logger.error("Internal HTTP error id=%s path=%s", error_id, request.url.path)
    _report_server_error(request, exc.status_code, exc)
    return JSONResponse(status_code=exc.status_code, content=_internal_error_payload(error_id))


def _superseded_response(headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Este cambio todavía se está procesando."},
        headers={**(headers or {}), "X-Idempotency-Status": "processing", "Retry-After": "2"},
    )


@app.exception_handler(OperationSuperseded)
async def superseded_operation_handler(request: Request, exc: OperationSuperseded):
    # A newer attempt owns this X-Idempotency-Key; this attempt's write was rolled back.
    return _superseded_response()


@app.exception_handler(Exception)
async def safe_unhandled_error_handler(request: Request, exc: Exception):
    error_id = _request_id(request)
    logger.error("Unhandled API error id=%s path=%s error=%s", error_id, request.url.path, _safe_exception_summary(exc))
    _report_server_error(request, 500, exc)
    return JSONResponse(status_code=500, content=_internal_error_payload(error_id))


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    # Runs inside auth_middleware (registered after it), so the request ID is set and
    # the route template is resolved. One structured line per request; slow requests
    # are reported (deduplicated per route). Never a query string, header or body.
    started = time.monotonic()
    response = await call_next(request)
    ops.access(request.scope.get("route"), request.url.path, request.method, response.status_code,
               int((time.monotonic() - started) * 1000), getattr(request.state, "request_id", None))
    return response


@app.middleware("http")
async def language_middleware(request: Request, call_next):
    # Text generated for the public DINCR app follows Accept-Language (es|en).
    token = set_language(language_for_request(request.url.path, request.headers.get("accept-language")))
    users_token = set_dincr_users(is_dincr_users_path(request.url.path))
    try:
        return await call_next(request)
    finally:
        reset_dincr_users(users_token)
        reset_language(token)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    request_id = _request_id(request)
    origin = request.headers.get("origin")

    cors_headers = {}
    if origin in ALLOWED_APP_ORIGINS:
        cors_headers["Access-Control-Allow-Origin"] = origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"

    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    if _is_public_path(request.url.path):
        # Health endpoints have no feature flag; skipping the threadpool hop keeps
        # /health/live answering even when every worker thread is busy.
        disabled_feature = None if request.url.path.startswith("/health/") else await run_in_threadpool(
            disabled_feature_for_request, request.method, request.url.path)
        if disabled_feature:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": disabled_feature["disabled_message_es"],
                    "code": "feature_temporarily_unavailable",
                    "feature": disabled_feature["flag_key"],
                },
                headers={**cors_headers, "X-Request-ID": request_id},
            )
        try:
            response = await call_next(request)
        except Exception as exc:
            # Same redaction as authenticated paths: an escaping exception would be
            # re-raised by Starlette and logged verbatim (URLs with tokens) by uvicorn.
            logger.error("Unhandled API error id=%s path=%s error=%s", request_id, request.url.path, _safe_exception_summary(exc))
            _report_server_error(request, 500, exc)
            return JSONResponse(
                status_code=500,
                content=_internal_error_payload(request_id),
                headers={**cors_headers, "X-Request-ID": request_id},
            )
        response.headers["X-Request-ID"] = request_id
        return response

    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Falta Authorization: Bearer <token>."},
            headers={**cors_headers, "X-Request-ID": request_id},
        )

    access_token = authorization.replace("Bearer ", "", 1).strip()

    # Authentication calls Supabase over HTTP and runs database transactions: it runs
    # in the thread pool (with this context copied), never on the event loop, so one
    # slow or junk request cannot stall every other request of the process.
    try:
        if access_token.startswith("jarvis-owner:"):
            user = await run_in_threadpool(authenticate_owner_bridge_token, access_token.removeprefix("jarvis-owner:").strip())
        else:
            # auth_middleware runs before language_middleware: resolve the language here so
            # identity/deletion messages follow Accept-Language.
            with use_language(language_for_request(request.url.path, request.headers.get("accept-language"))):
                if request.method == "DELETE" and request.url.path == "/auth/me":
                    # Only the account deletion itself may run on a deletion_pending account (retry).
                    user = await run_in_threadpool(authenticate_access_token, access_token, allow_deletion_pending=True)
                else:
                    user = await run_in_threadpool(authenticate_access_token, access_token)
    except Exception as exc:
        # An infrastructure failure (database, network) is not an invalid session:
        # answer 503 so the app retries instead of signing the user out on a 401.
        if not hasattr(exc, "status_code"):
            logger.error("Authentication failed without a verdict id=%s error=%s", request_id, _safe_exception_summary(exc))
            ops.report("auth", "verification_unavailable", "error", method=request.method, status=503,
                       error_class=type(exc).__name__, error_code=getattr(exc, "pgcode", None), request_id=request_id)
        status_code = getattr(exc, "status_code", 503)
        detail = getattr(exc, "detail", "No pudimos verificar tu sesión en este momento. Intentá de nuevo.")
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers={**cors_headers, "X-Request-ID": request_id},
        )

    request.state.user = user
    disabled_feature = await run_in_threadpool(disabled_feature_for_request, request.method, request.url.path, user)
    if disabled_feature:
        return JSONResponse(
            status_code=503,
            content={
                "detail": disabled_feature["disabled_message_es"],
                "code": "feature_temporarily_unavailable",
                "feature": disabled_feature["flag_key"],
            },
            headers={**cors_headers, "X-Request-ID": request_id},
        )
    # SEC-12: a technical cap on writes per account, before any work (core/write_limit.py).
    retry_after = write_limit.retry_after_for(user, request.method, request.url.path)
    if retry_after is not None:
        logger.warning("Write limit reached id=%s method=%s", request_id, request.method)
        with use_language(language_for_request(request.url.path, request.headers.get("accept-language"))):
            detail = tx("Hiciste muchos cambios seguidos. Esperá unos segundos e intentá de nuevo.",
                        "You made many changes in a row. Wait a few seconds and try again.")
        return JSONResponse(
            status_code=429,
            content={"detail": detail, "code": "too_many_writes"},
            headers={**cors_headers, "X-Request-ID": request_id, "Retry-After": str(int(retry_after + 0.999))},
        )
    context_token = set_current_user(user)
    idempotency_key = request.headers.get("X-Idempotency-Key", "").strip()
    idempotency_account = str(user.get("account_id") or "")
    idempotency_reserved = False
    idempotency_lease = None

    if idempotency_key and is_recoverable_operation(request.method, request.url.path):
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) or not idempotency_account:
            reset_current_user(context_token)
            return JSONResponse(
                status_code=422,
                content={"detail": "La referencia de recuperación no es válida."},
                headers={**cors_headers, "X-Request-ID": request_id},
            )
        body = await request.body()
        try:
            reservation = await run_in_threadpool(
                reserve_operation,
                account_id=idempotency_account,
                key=idempotency_key,
                method=request.method,
                path=request.url.path,
                digest=request_hash(request.method, request.url.path, body),
            )
        except Exception:
            logger.exception("Idempotency reservation failed id=%s path=%s", request_id, request.url.path)
            reset_current_user(context_token)
            return JSONResponse(
                status_code=503,
                content={"detail": "No pudimos proteger este cambio todavía. DINCR lo reintentará."},
                headers={**cors_headers, "X-Request-ID": request_id, "Retry-After": "2"},
            )
        if reservation.state == "replay":
            reset_current_user(context_token)
            return JSONResponse(
                status_code=reservation.response_status or 200,
                content=reservation.response_body,
                headers={
                    **cors_headers,
                    "X-Request-ID": request_id,
                    "X-Idempotency-Replayed": "true",
                },
            )
        if reservation.state in {"processing", "unavailable"}:
            reset_current_user(context_token)
            return JSONResponse(
                status_code=409,
                content={"detail": "Este cambio todavía se está procesando."},
                headers={
                    **cors_headers,
                    "X-Request-ID": request_id,
                    "X-Idempotency-Status": "processing",
                    "Retry-After": "2",
                },
            )
        if reservation.state == "conflict":
            reset_current_user(context_token)
            return JSONResponse(
                status_code=409,
                content={"detail": "La referencia de recuperación ya pertenece a otro cambio."},
                headers={**cors_headers, "X-Request-ID": request_id},
            )
        idempotency_reserved = True
        idempotency_lease = reservation.lease

    try:
        operation_token = (
            activate_operation(account_id=idempotency_account, key=idempotency_key, lease=idempotency_lease)
            if idempotency_reserved else None
        )
        try:
            response = await call_next(request)
        finally:
            if operation_token is not None:
                deactivate_operation(operation_token)
        response.headers["X-Request-ID"] = request_id
        if idempotency_reserved:
            if 200 <= response.status_code < 300 and "application/json" in response.headers.get("content-type", ""):
                response_body = b"".join([chunk async for chunk in response.body_iterator])
                try:
                    await run_in_threadpool(
                        complete_operation,
                        account_id=idempotency_account,
                        key=idempotency_key,
                        lease=idempotency_lease,
                        status_code=response.status_code,
                        body=response_body,
                    )
                except Exception:
                    logger.exception("Idempotency completion failed id=%s path=%s", request_id, request.url.path)
                    await run_in_threadpool(safe_abandon_operation, account_id=idempotency_account, key=idempotency_key, lease=idempotency_lease)
                response_headers = dict(response.headers)
                response_headers.pop("content-length", None)
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=response_headers,
                )
            else:
                await run_in_threadpool(safe_abandon_operation, account_id=idempotency_account, key=idempotency_key, lease=idempotency_lease)
        return response

    except Exception as exc:
        if idempotency_reserved:
            await run_in_threadpool(safe_abandon_operation, account_id=idempotency_account, key=idempotency_key, lease=idempotency_lease)
        if isinstance(exc, OperationSuperseded):
            return _superseded_response({**cors_headers, "X-Request-ID": request_id})
        error_id = request_id
        logger.error("Unhandled API error id=%s path=%s error=%s", error_id, request.url.path, _safe_exception_summary(exc))
        _report_server_error(request, 500, exc)
        return JSONResponse(
            status_code=500,
            content=_internal_error_payload(error_id),
            headers={**cors_headers, "X-Request-ID": request_id},
        )

    finally:
        reset_current_user(context_token)

# Legacy DINCR Owner (JARVIS Personal) APIs. Any Google/Apple login provisions an
# account, so these must check the role server-side: the public DINCR app only uses
# /user-product, /product-ops and /auth. Routers with public cron/webhook endpoints
# (notifications, IBKR bridge, email monitor) enforce roles per route instead.
INTERNAL_ONLY = [Depends(require_owner)]

app.include_router(finance_router, dependencies=INTERNAL_ONLY)
app.include_router(goals_router, dependencies=INTERNAL_ONLY)
app.include_router(decision_router, dependencies=INTERNAL_ONLY)
app.include_router(reports_router, dependencies=INTERNAL_ONLY)
app.include_router(transactions_router, dependencies=INTERNAL_ONLY)
app.include_router(importers_router, dependencies=INTERNAL_ONLY)
app.include_router(advisor_router, dependencies=INTERNAL_ONLY)
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(email_monitor_router)
app.include_router(notifications_router)
app.include_router(financial_history_router)
app.include_router(investment_center_router, dependencies=INTERNAL_ONLY)
app.include_router(ibkr_readonly_router)
app.include_router(business_center_router, dependencies=INTERNAL_ONLY)
app.include_router(users_admin_router)
app.include_router(owner_bridge_router)
app.include_router(user_product_router)
app.include_router(deployment_monitor_router)
app.include_router(product_ops_router)
app.include_router(store_billing_router)
app.include_router(financial_lifecycle_router)
app.include_router(observability_router)

class AskRequest(BaseModel):
    text: str


class EventRequest(BaseModel):
    title: str
    event_date: str
    event_type: str = "general"
    description: str = ""


@app.on_event("startup")
def startup_event():
    ops.configure_logging()
    init_database()


@app.get("/")
def home():
    return {
        "status": "Jarvis activo"
    }


@app.get("/status")
def status():
    return {"status": "ok"}


@app.post("/ask", dependencies=INTERNAL_ONLY)
def ask(request: AskRequest):
    return process_input(request.text)


@app.get("/events", dependencies=INTERNAL_ONLY)
def events():
    return get_events()


@app.post("/events", dependencies=INTERNAL_ONLY)
def create_event(request: EventRequest):
    return add_event(
        title=request.title,
        event_date=request.event_date,
        event_type=request.event_type,
        description=request.description
    )


@app.get("/logs", dependencies=INTERNAL_ONLY)
def logs():
    return get_logs()
