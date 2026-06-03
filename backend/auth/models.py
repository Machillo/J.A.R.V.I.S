from pydantic import BaseModel


class AllowedUserRequest(BaseModel):
    email: str
    role: str = "user"
    status: str = "active"