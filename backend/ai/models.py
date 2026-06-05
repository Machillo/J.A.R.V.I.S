from pydantic import BaseModel


class JarvisChatRequest(BaseModel):
    message: str


class JarvisChatResponse(BaseModel):
    message: str
    intent: str | None = None
    action_type: str | None = None
    status: str = "OK"
    pending: bool = False
    data: dict | None = None
