from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .api import router
from .database import Base, SessionLocal, engine, migrate_sqlite_schema
from .services.bootstrap import ensure_reference_entities, import_validated_history


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema()
    db = SessionLocal()
    try:
        ensure_reference_entities(db)
        import_validated_history(db)
    finally:
        db.close()
    yield


app = FastAPI(title="EH4000 Structural Integrity API", version="1.0.0",
              description="Historical inspections, deterministic maintenance, work orders and 3D hotspot calibration.",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:4173", "http://127.0.0.1:4173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
def root():
    return {"application":"EH4000 Structural Integrity", "api":"/api", "openapi":"/docs"}
