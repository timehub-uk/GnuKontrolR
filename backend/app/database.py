"""SQLite database setup with SQLAlchemy async."""
import logging
import re
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import event, text
from sqlalchemy.pool import NullPool
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "webpanel.db"
DB_PATH.parent.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,  # Each session gets its own connection — avoids SQLite locking with async tasks
    connect_args={"check_same_thread": False},  # Allow concurrent async task access
)


# Ensure every new connection gets WAL mode + busy_timeout.
# NullPool creates a fresh connection every time, so init_db() pragmas alone are not enough.
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


from sqlalchemy.types import TypeDecorator, String
from app.encrypt import encrypt_field, decrypt_field

class EncryptedString(TypeDecorator):
    """Automatically encrypt string fields at rest using Fernet."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return encrypt_field(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return decrypt_field(value)
        return value


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ── Column migrations ─────────────────────────────────────────────────────────
# SQLAlchemy create_all only creates missing *tables*, not missing *columns*.
# Checks all tables registered in metadata and compares them with SQLite schema,
# adding any missing columns automatically on startup.

# Constants for identifier validation
_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def _validate_id(name: str, label: str) -> None:
    """Reject SQL identifiers that don't match a safe pattern."""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {label}: {name!r}")


async def _run_column_migrations(conn) -> None:
    for table_name, table in Base.metadata.tables.items():
        _validate_id(table_name, "table name")

        # M16: parameterized query for table existence check
        table_check = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :name"),
            {"name": table_name},
        )
        if not table_check.fetchone():
            continue

        # Get existing columns in SQLite
        res = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        existing_cols = {row[1] for row in res.fetchall()}

        # Compare and add missing columns
        for col_name, col in table.columns.items():
            if col_name not in existing_cols:
                _validate_id(col_name, "column name")

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
    from app.models import user, domain, container_port, request_log, ai_provider, app_cache, installed_app, notification, fail2ban, domain_ip_rule, country_data, scanner, email_security, site_backup, ai_session, setup, mfa_device, consent, data_subject_request, breach_notification, data_processing, password_policy, secondary_service, secondary_service_blob  # noqa — registers models
    async with engine.begin() as conn:
        # Enable WAL mode for better concurrent access in async tasks
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))
        await conn.run_sync(Base.metadata.create_all)
        await _run_column_migrations(conn)
