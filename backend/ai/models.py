from pydantic import BaseModel


class JarvisChatRequest(BaseModel):
    message: str