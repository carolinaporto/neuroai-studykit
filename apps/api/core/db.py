from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
