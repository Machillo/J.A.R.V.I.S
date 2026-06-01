from backend.core.time import get_time
from backend.core.user import get_user
from backend.core.config import get_config
from backend.core.events import get_events
from backend.core.logs import get_logs


def route(intent: str):
    if intent == "GET_TIME":
        return get_time()

    if intent == "GET_USER":
        return get_user()

    if intent == "GET_CONFIG":
        return get_config()

    if intent == "GET_EVENTS":
        return get_events()

    if intent == "GET_LOGS":
        return get_logs()

    return {
        "message": "No entiendo la intención todavía."
    }