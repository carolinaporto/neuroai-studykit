from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str


class SessionStatus(BaseModel):
    signed_in: bool
