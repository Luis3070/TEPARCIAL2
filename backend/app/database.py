from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("EH4000_DB_PATH", ROOT / "backend" / "eh4000_integrity.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("EH4000_DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(connection, _record):
        cursor=connection.cursor();cursor.execute("PRAGMA foreign_keys=ON");cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_sqlite_schema() -> None:
    """Apply additive local-schema changes without discarding user-created rows."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    additions={
        "model_3d_assets": {
            "byte_size":"INTEGER", "is_watertight":"BOOLEAN", "is_winding_consistent":"BOOLEAN",
        },
    }
    inspector=inspect(engine)
    with engine.begin() as conn:
        for table,columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing={column["name"] for column in inspector.get_columns(table)}
            for name,sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}'))
