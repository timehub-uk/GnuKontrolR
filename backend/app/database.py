"""SQLite database setup with SQLAlchemy async."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "webpanel.db"
DB_PATH.parent.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    from app.models import user, domain, container_port, request_log  # noqa — registers models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
