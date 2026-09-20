from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import logging
import re
from uuid import uuid4

from backend.core.brain import process_input
from backend.core.database import init_database
from backend.core.events import add_event, get_events
from backend.core.logs import get_logs
from backend.finance.routes import router as finance_router
from backend.goals.routes import router as goals_router
from backend.decision_engine.routes import router as decision_router
from backend.reports.routes import router as reports_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from backend.transactions.routes import router as transactions_router
from backend.importers.routes import router as importers_router
from backend.advisor.routes import router as advisor_router
from backend.auth.routes import router as auth_router
from backend.ai.routes import router as ai_router
from backend.email_monitor.routes import router as email_monitor_router
from backend.notifications.routes import router as notifications_router
from backend.finance.investment_center import router as investment_center_router
from backend.finance.business_center import router as business_center_router
from backend.auth.current_user import set_current_user, reset_current_user
from backend.auth.service import authenticate_access_token
from backend.auth.owner_bridge import authenticate_owner_bridge_token
from backend.users_admin.routes import router as users_admin_router
from backend.auth.owner_bridge_routes import router as owner_bridge_router
from backend.user_product.routes import router as user_product_router
from backend.deployment_monitor.routes import router as deployment_monitor_router
from backend.integrations.ibkr_readonly import router as ibkr_readonly_router
from backend.product_ops.routes import router as product_ops_router
from backend.financial_lifecycle.routes import router as financial_lifecycle_router
from backend.core.idempotency import (
    IDEMPOTENCY_KEY_PATTERN,
    complete_operation,
    is_recoverable_operation,
    request_hash,
    reserve_operation,
    safe_abandon_operation,
)

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
)


PUBLIC_PATHS = {
    "/",
    "/status",
    "/product-ops/release-policy",
    "/auth/health",
    "/auth/check-access",
    "/email-monitor/cron",
    "/email-monitor/gmail-watch",
    "/email-monitor/gmail-push",
    "/user-product/vip/gmail/callback",
    "/user-product/vip/gmail/maintenance",
    "/user-product/vip/gmail/push",
    "/notifications/cron",
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


def _internal_error_payload(error_id: str) -> dict[str, str]:
    return {
        "detail": "Ocurrió un error interno. Intentá nuevamente.",
        "error_id": error_id,
        "request_id": error_id,
    }


@app.exception_handler(HTTPException)
async def safe_http_error_handler(request: Request, exc: HTTPException):
    if exc.status_code < 500:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    error_id = _request_id(request)
    logger.error("Internal HTTP error id=%s path=%s", error_id, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=_internal_error_payload(error_id))


@app.exception_handler(Exception)
async def safe_unhandled_error_handler(request: Request, exc: Exception):
    error_id = _request_id(request)
    logger.exception("Unhandled API error id=%s path=%s", error_id, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content=_internal_error_payload(error_id))


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    request_id = _request_id(request)
    origin = request.headers.get("origin")

    cors_headers = {}
    if origin in ALLOWED_APP_ORIGINS:
        cors_headers["Access-Control-Allow-Origin"] = origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"

    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        response = await call_next(request)
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

    try:
        if access_token.startswith("jarvis-owner:"):
            user = authenticate_owner_bridge_token(access_token.removeprefix("jarvis-owner:").strip())
        else:
            user = authenticate_access_token(access_token)
    except Exception as exc:
        status_code = getattr(exc, "status_code", 401)
        detail = getattr(exc, "detail", "No se pudo autenticar el usuario.")
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers={**cors_headers, "X-Request-ID": request_id},
        )

    request.state.user = user
    context_token = set_current_user(user)
    idempotency_key = request.headers.get("X-Idempotency-Key", "").strip()
    idempotency_account = str(user.get("account_id") or "")
    idempotency_reserved = False

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
            reservation = reserve_operation(
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
                content={"detail": "No pudimos proteger este cambio todavía. FINVA lo reintentará."},
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

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if idempotency_reserved:
            if 200 <= response.status_code < 300 and "application/json" in response.headers.get("content-type", ""):
                response_body = b"".join([chunk async for chunk in response.body_iterator])
                try:
                    complete_operation(
                        account_id=idempotency_account,
                        key=idempotency_key,
                        status_code=response.status_code,
                        body=response_body,
                    )
                except Exception:
                    logger.exception("Idempotency completion failed id=%s path=%s", request_id, request.url.path)
                    safe_abandon_operation(account_id=idempotency_account, key=idempotency_key)
                response_headers = dict(response.headers)
                response_headers.pop("content-length", None)
                response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=response_headers,
                )
            else:
                safe_abandon_operation(account_id=idempotency_account, key=idempotency_key)
        return response

    except Exception:
        if idempotency_reserved:
            safe_abandon_operation(account_id=idempotency_account, key=idempotency_key)
        error_id = request_id
        logger.exception("Unhandled API error id=%s path=%s", error_id, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_internal_error_payload(error_id),
            headers={**cors_headers, "X-Request-ID": request_id},
        )

    finally:
        reset_current_user(context_token)

app.include_router(finance_router)
app.include_router(goals_router)
app.include_router(decision_router)
app.include_router(reports_router)
app.include_router(transactions_router)
app.include_router(importers_router)
app.include_router(advisor_router)
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(email_monitor_router)
app.include_router(notifications_router)
app.include_router(investment_center_router)
app.include_router(ibkr_readonly_router)
app.include_router(business_center_router)
app.include_router(users_admin_router)
app.include_router(owner_bridge_router)
app.include_router(user_product_router)
app.include_router(deployment_monitor_router)
app.include_router(product_ops_router)
app.include_router(financial_lifecycle_router)

class AskRequest(BaseModel):
    text: str


class EventRequest(BaseModel):
    title: str
    event_date: str
    event_type: str = "general"
    description: str = ""


@app.on_event("startup")
def startup_event():
    init_database()


@app.get("/")
def home():
    return {
        "status": "Jarvis activo"
    }


@app.get("/status")
def status():
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest):
    return process_input(request.text)


@app.get("/events")
def events():
    return get_events()


@app.post("/events")
def create_event(request: EventRequest):
    return add_event(
        title=request.title,
        event_date=request.event_date,
        event_type=request.event_type,
        description=request.description
    )


@app.get("/logs")
def logs():
    return get_logs()
