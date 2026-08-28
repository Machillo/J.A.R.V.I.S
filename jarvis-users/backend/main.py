from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.auth.current_user import reset_current_user, set_current_user
from backend.auth.routes import router as auth_router
from backend.auth.service import authenticate_access_token
from backend.core.database import close_database, init_database
from backend.finance.routes import router as finance_router
from backend.goals.routes import router as goals_router
from backend.transactions.routes import router as transactions_router


app = FastAPI(title="JARVIS Users API", version="0.1.0")

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/", "/docs", "/redoc", "/openapi.json", "/auth/health"}
ONBOARDING_PATHS = {"/auth/me", "/auth/plans", "/auth/plan", "/auth/onboarding"}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or _is_public_path(request.url.path):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Falta Authorization: Bearer <token>."})

    try:
        user = await run_in_threadpool(authenticate_access_token, authorization.removeprefix("Bearer ").strip())
    except Exception as exc:
        return JSONResponse(
            status_code=getattr(exc, "status_code", 401),
            content={"detail": getattr(exc, "detail", "No se pudo autenticar el usuario.")},
        )

    if not user.get("plan_selected") and request.url.path not in {"/auth/me", "/auth/plans", "/auth/plan"}:
        return JSONResponse(
            status_code=428,
            content={"detail": "Elegí un plan antes de continuar.", "code": "plan_required"},
        )

    if not user.get("onboarding_completed") and request.url.path not in ONBOARDING_PATHS:
        return JSONResponse(
            status_code=428,
            content={"detail": "Completá el onboarding financiero antes de continuar.", "code": "onboarding_required"},
        )

    request.state.user = user
    token = set_current_user(user)
    try:
        return await call_next(request)
    finally:
        reset_current_user(token)


app.include_router(auth_router)
app.include_router(finance_router)
app.include_router(goals_router)
app.include_router(transactions_router)


@app.on_event("startup")
def startup_event():
    init_database()


@app.on_event("shutdown")
def shutdown_event():
    close_database()


@app.get("/")
def home():
    return {"status": "ok", "service": "JARVIS Users API"}
