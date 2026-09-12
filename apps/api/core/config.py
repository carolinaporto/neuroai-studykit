import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studykit:studykit@localhost:5433/studykit"
    # Owner fixo até o M12 existir (auth) — mesmo default de packages/db/session.DbSettings.
    dev_owner_id: uuid.UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")


settings = Settings()
