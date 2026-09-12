from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from apps.api.core.config import settings
from packages.db.session import make_session_factory

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
session_factory = make_session_factory(settings.database_url)


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with session_factory() as session:
        yield session
