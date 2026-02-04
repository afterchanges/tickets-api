from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.settings import settings


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)
