from fastapi import FastAPI, Request
from pydantic import BaseModel

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
from backend.auth.current_user import set_current_user, reset_current_user
from backend.auth.service import authenticate_access_token

app = FastAPI(title="Jarvis Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
}


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True

    if path.startswith("/docs") or path.startswith("/redoc"):
        return True

    return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Falta Authorization: Bearer <token>."},
        )

    access_token = authorization.replace("Bearer ", "", 1).strip()

    try:
        user = authenticate_access_token(access_token)
    except Exception as exc:
        status_code = getattr(exc, "status_code", 401)
        detail = getattr(exc, "detail", "No se pudo autenticar el usuario.")
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
        )

    request.state.user = user
    context_token = set_current_user(user)

    try:
        response = await call_next(request)
    finally:
        reset_current_user(context_token)

    return response

app.include_router(finance_router)
app.include_router(goals_router)
app.include_router(decision_router)
app.include_router(reports_router)
app.include_router(transactions_router)
app.include_router(importers_router)
app.include_router(advisor_router)
app.include_router(auth_router)
app.include_router(ai_router)

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