from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from app.database import Base, engine
from app.config import APP_VERSION
from app import migrations, settings, ha, backup
from app.routers import notes, folders, tags, search, export_import, settings as settings_router, images
from app.routers import ha as ha_router

Base.metadata.create_all(bind=engine)
settings.ensure_table()
migrations.run_all()

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


# ---------------------------------------------------------------------------
# Standby write-block middleware
# ---------------------------------------------------------------------------

HA_PREFIX = "/api/ha/"
STANDBY_OPEN_PATHS = {"/api/health"}


@app.middleware("http")
async def standby_gate(request: Request, call_next):
    if ha.ha_enabled() and ha.current_role() == "standby":
        path = request.url.path
        if path in STANDBY_OPEN_PATHS or path.startswith(HA_PREFIX) or not path.startswith("/api/"):
            return await call_next(request)
        # Allow GETs against the API so a misrouted reader still gets data.
        if request.method == "GET":
            return await call_next(request)
        return JSONResponse(
            {
                "detail": "This node is in standby. Direct writes to the primary.",
                "primary_url": ha.peer_base_url(),
            },
            status_code=503,
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
def _startup():
    ha.on_startup()
    backup.start_scheduler()


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(notes.router)
app.include_router(folders.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(export_import.router)
app.include_router(settings_router.router)
app.include_router(images.router)
app.include_router(ha_router.router)

STATIC_DIR = Path("/app/static")

if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
