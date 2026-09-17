import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studykit:studykit@localhost:5433/studykit"
    # Identidade fixa da única usuária — auth (abaixo) só decide se uma requisição pode agir
    # como ela; não existe conta de verdade nem OIDC até o M12. Mesmo default de
    # packages/db/session.DbSettings.
    dev_owner_id: uuid.UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")
    # Circuit breaker para /api/study/answer — ver apps/api/services/budget.py e
    # ARCHITECTURE.md §7. Mesmos nomes de .env.example.
    daily_token_budget: int = 200_000
    max_gradings_per_day: int = 300
    # Auth leve de usuária única — ver apps/api/core/auth.py. Uma senha, não uma conta: o
    # site é público em partes (Overview, Homework) e trancado nas outras (Sources, Quizzes,
    # Notes) para todo visitante que não souber a senha. Sem valor default: uma sessão criada
    # com segredo vazio autentica qualquer um, então login fica bloqueado até isto ser
    # configurado (ver auth.py).
    owner_password: str = ""
    session_secret: str = ""
    env: str = "development"
    # Where POST /api/sources/upload writes uploaded files — local disk for now.
    # `storage/` (not `content/`) on purpose: `content/` is reserved for the copyright-
    # sensitive course material workflow (ARCHITECTURE.md §8); `storage/` is .gitignore's
    # existing, separate slot for local uploads. Moves to R2/S3 at deploy time (M13);
    # nothing else in the codebase assumes a local path, only this setting's default.
    upload_dir: str = "storage/uploads"


settings = Settings()
