import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studykit:studykit@localhost:5433/studykit"
    # Fixed id every test fixture creates its rows under (see tests/*'s shared _test_client
    # helpers) — no longer how production resolves "who's logged in" as of M12, but every
    # ingestion script/test still needs one stable owner id to seed rows against.
    dev_owner_id: uuid.UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")
    # Circuit breaker para /api/study/answer — ver apps/api/services/budget.py e
    # ARCHITECTURE.md §7. Mesmos nomes de .env.example.
    daily_token_budget: int = 200_000
    max_gradings_per_day: int = 300
    # M12: real auth via Clerk (OIDC + magic link) — see apps/api/core/auth.py. No default
    # for the secret key on purpose: a request can't be verified as signed-in with an empty
    # key, so auth fails closed until this is configured, same reasoning the old
    # OWNER_PASSWORD had.
    clerk_secret_key: str = ""
    # Whichever ALLOWED_EMAILS address matches this one gets role=owner on first login;
    # every other allowed address gets role=student. Never the User.role column's own
    # default — see apps/api/core/deps.py.
    owner_email: str = ""
    # Comma-separated in .env; ARCHITECTURE.md's own framing: "quem não está na lista não
    # cria conta, mesmo tendo a URL" — enforced by this app, not left to Clerk's dashboard.
    # Raw string field (matches the env var name pydantic-settings expects); use the
    # `allowed_email_set` property below, never this one directly.
    allowed_emails: str = ""
    env: str = "development"
    # M13: the deployed frontend's origin (e.g. https://neuroai-studykit.vercel.app), added
    # to CORS alongside the localhost regex below — empty in dev, where the regex alone
    # already covers Vite's ports.
    web_origin: str = ""

    @property
    def allowed_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.allowed_emails.split(",") if email.strip()}


settings = Settings()
