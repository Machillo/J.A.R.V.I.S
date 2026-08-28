from backend.core.interpreter import interpret
from backend.core.router import route
from backend.core.time import get_time
from backend.core.user import get_user
from backend.core.logs import add_log


def process_input(text: str):
    intent = interpret(text)
    result = route(intent, text)

    add_log(
        action="USER_INPUT",
        detail=f"Text: {text} | Intent: {intent}"
    )

    return {
        "user": get_user(),
        "time": get_time(),
        "intent": intent,
        "response": result
    }