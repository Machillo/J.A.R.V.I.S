from fastapi import FastAPI, Request
from pydantic import BaseModel
import traceback

from backend.core.brain import process_input
from backend.core.database import init_database
from backend.core.user import get_user
from backend.core.config import get_config
from backend.core.time import get_time
from backend.core.events import add_event, get_events
from backend.core.logs import get_logs
from backend.finance.routes import router as finance_router
from backend.goals.routes import router as goals_router
from backend.decision_engine.routes import router as decision_router
from backend.reports.routes import router as reports_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

app = FastAPI(title="Jarvis Core")

app.add_middleware(
    CORSMiddleware,
     allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://jarvis-frontend-delta.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PUBLIC_PATHS = {
    "/",
    "/status",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/health",
    "/auth/check-access",
    "/email-monitor/cron",
    "/email-monitor/gmail-watch",
    "/email-monitor/gmail-push",
    "/notifications/cron",
    "/deployment-monitor/webhook/github",
    "/deployment-monitor/webhook/vercel",
    "/deployment-monitor/webhook/render",
    "/integrations/ibkr/snapshot",
    "/internal/owner-bridge/verify",
}


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True

    if path.startswith("/docs") or path.startswith("/redoc"):
        return True

    return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    origin = request.headers.get("origin")

    cors_headers = {}
    if origin in {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://jarvis-frontend-delta.vercel.app",
    }:
        cors_headers["Access-Control-Allow-Origin"] = origin
        cors_headers["Access-Control-Allow-Credentials"] = "true"

    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Falta Authorization: Bearer <token>."},
            headers=cors_headers,
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
            headers=cors_headers,
        )

    request.state.user = user
    context_token = set_current_user(user)

    try:
        response = await call_next(request)
        return response

    except Exception as error:
        print("[GLOBAL ERROR]", flush=True)
        print(f"Path: {request.url.path}", flush=True)
        print(f"Type: {type(error).__name__}", flush=True)
        print(f"Error: {str(error)}", flush=True)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "path": request.url.path,
                "error_type": type(error).__name__,
                "error": str(error),
            },
            headers=cors_headers,
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
    return {
        "user": get_user(),
        "time": get_time(),
        "config": get_config()
    }


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
