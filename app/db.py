from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    """Создаёт таблицу message_feedback при старте."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS message_feedback (
                id SERIAL PRIMARY KEY,
                message_id TEXT NOT NULL,
                owner_external_id BIGINT NOT NULL,
                value SMALLINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (owner_external_id, message_id)
            )
        """))