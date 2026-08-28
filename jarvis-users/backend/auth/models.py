from pydantic import BaseModel


class ProfileStatusRequest(BaseModel):
    status: str


class ProfileRoleRequest(BaseModel):
    role: str
