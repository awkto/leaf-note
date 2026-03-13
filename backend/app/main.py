from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import inspect, text
from app.database import Base, engine
from app.config import APP_VERSION
from app.routers import notes, folders, tags, search, export_import, settings, images

Base.metadata.create_all(bind=engine)

# Migrate: add default_view columns if missing
with engine.connect() as conn:
    inspector = inspect(engine)
    for table in ("notes", "folders"):
        cols = [c["name"] for c in inspector.get_columns(table)]
        if "default_view" not in cols:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN default_view VARCHAR(10)"))
            conn.commit()

app = FastAPI(
    title="Leaf Note",
    description="Markdown-focused note-taking API for humans and LLMs",
    version=APP_VERSION,
    docs_url="/apidocs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notes.router)
app.include_router(folders.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(export_import.router)
app.include_router(settings.router)
app.include_router(images.router)

STATIC_DIR = Path("/app/static")

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
