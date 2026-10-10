from __future__ import annotations

import os
import base64
import binascii
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

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
allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:4173", "http://127.0.0.1:4173"]
allowed_origins += [origin.strip() for origin in os.environ.get("EH4000_CORS_ORIGINS", "").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.middleware("http")
async def site_password(request: Request, call_next):
    password = os.environ.get("EH4000_SITE_PASSWORD")
    if password:
        credentials = request.headers.get("authorization", "")
        authorized = False
        if credentials.startswith("Basic "):
            try:
                decoded = base64.b64decode(credentials[6:], validate=True).decode("utf-8")
                username, supplied = decoded.split(":", 1)
                authorized = secrets.compare_digest(username, "eh4000") and secrets.compare_digest(supplied, password)
            except (ValueError, UnicodeDecodeError, binascii.Error):
                pass
        if not authorized:
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="EH4000"'})
    return await call_next(request)

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        is_page = "." not in Path(path).name and not path.startswith(("api/", "docs", "redoc", "openapi.json"))
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and is_page:
                return FileResponse(DIST / "index.html")
            raise
        if response.status_code == 404 and is_page:
            return FileResponse(DIST / "index.html")
        return response


if DIST.is_dir():
    app.mount("/", SPAStaticFiles(directory=DIST, html=True), name="frontend")


@app.get("/")
def root():
    return {"application":"EH4000 Structural Integrity", "api":"/api", "openapi":"/docs"}
