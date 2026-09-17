from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """A dependency, not a bare import, on purpose: `generate_for_week`
    (`packages/ingest/cli.py`) needs a whole `session_factory` rather than one `AsyncSession`
    because it manages several of its own transactions across a week's chunks. Routing it
    through `Depends` — instead of `apps/api/routers/sources.py` importing the module-level
    `session_factory` above directly — is what lets tests override it with a per-test
    factory, same as `get_session`. Importing the module global directly bound the whole
    call to whatever event loop was live at import time, which broke under pytest-asyncio's
    one-event-loop-per-test model the rest of this suite already depends on."""
    return session_factory
