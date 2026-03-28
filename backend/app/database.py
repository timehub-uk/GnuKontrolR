"""SQLite database setup with SQLAlchemy async."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import text
from pathlib import Path

log = logging.getLogger(__name__)

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


# ── Column migrations ─────────────────────────────────────────────────────────
# SQLAlchemy create_all only creates missing *tables*, not missing *columns*.
# List every column addition here as (table, column, sql_type, default).
# Each entry is applied with ALTER TABLE … ADD COLUMN … if the column is absent.
_COLUMN_MIGRATIONS: list[tuple[str, str, str, str]] = [
    ("domains",        "acme_email",   "VARCHAR(128)", "NULL"),
]


async def _run_column_migrations(conn) -> None:
    for table, column, col_type, default in _COLUMN_MIGRATIONS:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        cols = {row[1] for row in result.fetchall()}
        if column not in cols:
            ddl = f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default}"
            await conn.execute(text(ddl))
            log.info("DB migration applied: %s.%s (%s)", table, column, col_type)


async def init_db():
    from app.models import user, domain, container_port, request_log, ai_provider, app_cache, installed_app  # noqa — registers models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_column_migrations(conn)
