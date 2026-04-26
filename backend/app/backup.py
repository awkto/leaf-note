"""Dated, gzipped local DB backups with skip-if-unchanged.

Runs on both primary and standby -- every node always has a local snapshot
independent of HA replication.
"""
import gzip
import logging
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import (
    BACKUP_DIR,
    BACKUP_INTERVAL_SECONDS,
    BACKUP_RETENTION_DAYS,
    DB_PATH,
)

logger = logging.getLogger(__name__)

DB_PATH_STR = str(DB_PATH)

_last_data_version: int | None = None


def _read_data_version() -> int | None:
    if not os.path.exists(DB_PATH_STR):
        return None
    try:
        with sqlite3.connect(DB_PATH_STR) as con:
            return con.execute("PRAGMA data_version").fetchone()[0]
    except Exception as e:
        logger.debug("data_version read failed: %s", e)
        return None


def _backup_dir() -> Path:
    d = Path(BACKUP_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prune_old_backups() -> int:
    cutoff = time.time() - BACKUP_RETENTION_DAYS * 86400
    removed = 0
    for f in _backup_dir().glob("leaf-*.db.gz"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
        except Exception:
            pass
    return removed


def run_backup(force: bool = False) -> dict:
    global _last_data_version

    version = _read_data_version()
    if version is None:
        return {"ok": False, "skipped": False, "reason": "db unavailable"}

    if not force and _last_data_version is not None and version == _last_data_version:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no writes since last backup",
            "data_version": version,
        }

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    target = _backup_dir() / f"leaf-{ts}.db"

    try:
        result = subprocess.run(
            ["sqlite3", DB_PATH_STR, f".backup {target}"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "skipped": False,
                "reason": f"sqlite3 backup failed: {result.stderr.strip()}",
            }

        gz = target.with_suffix(".db.gz")
        with open(target, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        target.unlink(missing_ok=True)

        _last_data_version = version
        pruned = _prune_old_backups()

        return {
            "ok": True,
            "skipped": False,
            "path": str(gz),
            "size_bytes": gz.stat().st_size,
            "data_version": version,
            "pruned": pruned,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "skipped": False, "reason": "sqlite3 backup timed out"}
    except Exception as e:
        return {"ok": False, "skipped": False, "reason": str(e)}


def list_backups() -> list[dict]:
    out = []
    for f in sorted(_backup_dir().glob("leaf-*.db.gz"), reverse=True):
        try:
            st = f.stat()
            out.append({
                "name": f.name,
                "size_bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            })
        except Exception:
            pass
    return out


def last_backup_info() -> dict | None:
    backups = list_backups()
    return backups[0] if backups else None


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

_scheduler = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_scheduled_backup, "interval", seconds=BACKUP_INTERVAL_SECONDS)
    _scheduler.start()
    logger.info("backup scheduler started (every %ss)", BACKUP_INTERVAL_SECONDS)


def _scheduled_backup() -> None:
    result = run_backup()
    if result.get("skipped"):
        logger.debug("backup skipped: %s", result.get("reason"))
    elif result.get("ok"):
        logger.info(
            "backup ok: %s (%d bytes, pruned=%d)",
            result.get("path"),
            result.get("size_bytes", 0),
            result.get("pruned", 0),
        )
    else:
        logger.warning("backup failed: %s", result.get("reason"))
