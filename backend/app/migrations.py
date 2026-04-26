"""One-shot data migrations run at startup. All migrations must be idempotent."""
import mimetypes
import logging
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import inspect, text
from app.database import engine, SessionLocal
from app.config import IMAGES_DIR
from app.models import Image

log = logging.getLogger(__name__)


def add_default_view_columns():
    with engine.connect() as conn:
        inspector = inspect(engine)
        for table in ("notes", "folders"):
            cols = [c["name"] for c in inspector.get_columns(table)]
            if "default_view" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN default_view VARCHAR(10)"))
                conn.commit()


def migrate_images_to_db():
    """Move any images on disk into the images table.

    Runs on every startup but only does work if there are unmigrated files.
    Successfully migrated files are renamed with a .migrated suffix so a
    re-run is a no-op and the originals stay around for one cycle as a
    safety net before we delete them in a later release.
    """
    if not IMAGES_DIR.exists():
        return

    files = [p for p in IMAGES_DIR.iterdir() if p.is_file() and not p.name.endswith(".migrated")]
    if not files:
        return

    log.info("migrate_images_to_db: %d candidate file(s) to migrate", len(files))
    migrated = 0
    skipped = 0

    with SessionLocal() as db:
        for path in files:
            existing = db.query(Image).filter(Image.filename == path.name).first()
            if existing:
                _mark_migrated(path)
                skipped += 1
                continue

            data = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            db.add(Image(
                filename=path.name,
                content_type=content_type,
                size_bytes=len(data),
                data=data,
                created_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
            ))
            db.commit()
            _mark_migrated(path)
            migrated += 1

    log.info("migrate_images_to_db: migrated=%d skipped=%d", migrated, skipped)


def _mark_migrated(path: Path):
    try:
        path.rename(path.with_suffix(path.suffix + ".migrated"))
    except OSError as e:
        log.warning("could not mark %s as migrated: %s", path, e)


def run_all():
    add_default_view_columns()
    migrate_images_to_db()
