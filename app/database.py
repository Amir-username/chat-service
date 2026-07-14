from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables on startup."""
    from app.models import User  # noqa: F401 — ensure model is registered

    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all)