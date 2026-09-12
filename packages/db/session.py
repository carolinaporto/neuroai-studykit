"""Engine/session factory for `packages/db`, usable from `apps/api` and from
`packages/ingest/cli.py` alike (invariant 4: the latter cannot import `apps.api.core.config`,
so it reads `DATABASE_URL`/`DEV_OWNER_ID` through its own settings here instead).
"""

import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class DbSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://studykit:studykit@localhost:5433/studykit"
    dev_owner_id: uuid.UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def make_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)
