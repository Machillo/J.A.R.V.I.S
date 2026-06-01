from fastapi import FastAPI
from pydantic import BaseModel

from backend.core.brain import process_input
from backend.core.database import init_database
from backend.core.user import get_user
from backend.core.config import get_config
from backend.core.time import get_time
from backend.core.events import add_event, get_events
from backend.core.logs import get_logs


app = FastAPI(title="Jarvis Core")


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