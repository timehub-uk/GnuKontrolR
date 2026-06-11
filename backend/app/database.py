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
# Checks all tables registered in metadata and compares them with SQLite schema,
# adding any missing columns automatically on startup.

async def _run_column_migrations(conn) -> None:
    for table_name, table in Base.metadata.tables.items():
        # Check if table exists in SQLite
        table_check = await conn.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
        if not table_check.fetchone():
            continue
        
        # Get existing columns in SQLite
        res = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        existing_cols = {row[1] for row in res.fetchall()}
        
        # Compare and add missing columns
        for col_name, col in table.columns.items():
            if col_name not in existing_cols:
                t_str = str(col.type).upper()
                sql_type = "TEXT"
                if "INT" in t_str or "BOOL" in t_str:
                    sql_type = "INTEGER"
                elif "FLOAT" in t_str or "DECIMAL" in t_str or "REAL" in t_str:
                    sql_type = "REAL"
                
                default_clause = ""
                if col.default is not None:
                    if hasattr(col.default, 'arg') and not callable(col.default.arg):
                        val = col.default.arg
                        if isinstance(val, bool):
                            val = 1 if val else 0
                        if isinstance(val, (int, float)):
                            default_clause = f" DEFAULT {val}"
                        else:
                            default_clause = f" DEFAULT '{val}'"
                    elif col.type.__class__.__name__ == "Boolean":
                        default_clause = " DEFAULT 0"
                
                ddl = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}{default_clause}"
                log.info("Applying dynamic DB migration: %s", ddl)
                await conn.execute(text(ddl))


async def init_db():
    from app.models import user, domain, container_port, request_log, ai_provider, app_cache, installed_app, notification, fail2ban, domain_ip_rule, country_data, scanner, email_security, site_backup, ai_session, setup, mfa_device, consent, data_subject_request, breach_notification, data_processing, password_policy, secondary_service  # noqa — registers models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_column_migrations(conn)
