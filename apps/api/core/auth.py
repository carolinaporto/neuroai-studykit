"""Single-owner auth: one password (`OWNER_PASSWORD`), one signed session cookie — not an
account system. `design/synapse` requires the site to tell a signed-in owner from a public
visitor (Sources/Quizzes/Notes lock for the visitor, Overview/Homework stay open), and that's
the entire job this module does. Real multi-user auth (OIDC, magic links) is still M12 in
docs/IMPLEMENTATION_PLAN.md; this is deliberately smaller.

The session token is `f"{issued_at}.{hmac_sha256(issued_at, SESSION_SECRET)}"` — no
`itsdangerous`/JWT dependency needed for a token that carries no payload beyond a timestamp,
since the only thing being asserted is "whoever holds this typed the password within
SESSION_TTL_SECONDS," not an identity (there's only ever one).
"""

import hashlib
import hmac
import time

SESSION_COOKIE_NAME = "studykit_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — a personal-site convenience session


def _signature(issued_at: str, secret: str) -> str:
    return hmac.new(secret.encode(), issued_at.encode(), hashlib.sha256).hexdigest()


def create_session_token(secret: str) -> str:
    issued_at = str(int(time.time()))
    return f"{issued_at}.{_signature(issued_at, secret)}"


def verify_session_token(
    token: str, secret: str, *, ttl_seconds: int = SESSION_TTL_SECONDS
) -> bool:
    """`False` for anything malformed, tampered, or expired — never raises, so callers can
    treat any falsy result as "not signed in" without a try/except."""
    issued_at, _, signature = token.partition(".")
    if not issued_at or not signature:
        return False
    if not hmac.compare_digest(_signature(issued_at, secret), signature):
        return False
    try:
        age = time.time() - int(issued_at)
    except ValueError:
        return False
    return 0 <= age <= ttl_seconds


def check_password(candidate: str, expected: str) -> bool:
    """Constant-time comparison; `expected == ""` (unconfigured `OWNER_PASSWORD`) always
    fails rather than matching an empty submission."""
    if not expected:
        return False
    return hmac.compare_digest(candidate, expected)
