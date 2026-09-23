"""Real auth via Clerk (OIDC + magic link) — M12, replacing the hand-rolled single
password this repo started with. Clerk owns sign-up, sign-in and sending the magic-link
email itself; FastAPI only *verifies* the session token it issues (invariant-3-adjacent:
`CLERK_SECRET_KEY` never leaves the backend, same as `ANTHROPIC_API_KEY`).

`ALLOWED_EMAILS` is enforced in `apps/api/core/deps.py`, by this app, not left to Clerk's
own dashboard configuration — `ARCHITECTURE.md`'s own framing: "quem não está na lista não
cria conta, mesmo tendo a URL."
"""

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from clerk_backend_api.security.types import RequestState
from fastapi import Request


def verify_request(request: Request, secret_key: str) -> RequestState:
    """Verifies the Clerk session token on `request` (Bearer header or cookie — Clerk
    checks both on its own). `.status` is `AuthStatus.SIGNED_IN`/`SIGNED_OUT`; when signed
    in, `.payload` is the verified JWT's claims, which must include `email` — see the
    Clerk dashboard's "customize session token" step this milestone's plan called for."""
    return authenticate_request(request, AuthenticateRequestOptions(secret_key=secret_key))
