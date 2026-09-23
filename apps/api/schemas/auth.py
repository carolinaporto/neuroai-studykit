from pydantic import BaseModel


class SessionStatus(BaseModel):
    signed_in: bool
    # This app's own mapped role (owner/student/demo), never Clerk's own claims directly —
    # None whenever signed_in is False.
    role: str | None = None
