"""HA role state + HTTPS-based snapshot replication + peer client.

Replication transport is plain HTTPS: every N seconds the primary takes an
atomic SQLite .backup, gzips it, and POSTs to the peer's /api/ha/replica-push
endpoint. The peer stores it as /data/leaf.db.replica. On promotion, the
standby moves .replica into place and reopens the engine.

Two endpoints + a timer. No external infra.

Configuration precedence:
  settings table  >  env vars  >  defaults

Local-only state lives in /data/ha.json (role, self_id, last promoted/demoted
times). Everything else is in the settings table and replicates with the DB.

Ported from awkto/atlas-inventory.
"""
import atexit
import base64
import gzip
import json
import logging
import os
import secrets as _secrets
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app import settings
from app.config import (
    DB_PATH,
    HA_ENABLED,
    HA_INITIAL_ROLE,
    HA_PEER_URL,
    HA_SELF_ID,
    HA_STATE_PATH,
    HA_TOKEN,
)

logger = logging.getLogger(__name__)

DB_PATH_STR = str(DB_PATH)
DATA_DIR_STR = os.path.dirname(DB_PATH_STR) or "/data"

REPLICA_DB_PATH = os.path.join(DATA_DIR_STR, "leaf.db.replica")
REPLICA_META_PATH = os.path.join(DATA_DIR_STR, "replica-meta.json")

DEFAULT_SYNC_INTERVAL_SECONDS = 30
MAX_SNAPSHOT_BYTES = int(os.getenv("MAX_SNAPSHOT_BYTES", str(500 * 1024 * 1024)))

_state_lock = threading.Lock()
_meta_lock = threading.Lock()
_scheduler = None

_http_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(verify=False, timeout=15.0)
    return _http_client


# ---------------------------------------------------------------------------
# Local role state (NEVER replicated)
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    return Path(HA_STATE_PATH)


def _default_state() -> dict:
    return {
        "role": HA_INITIAL_ROLE or "primary",
        "self_id": HA_SELF_ID or "A",
        "last_promoted_at": None,
        "last_demoted_at": None,
    }


def load_state() -> dict:
    with _state_lock:
        p = _state_path()
        if not p.exists():
            state = _default_state()
            _save_unlocked(state)
            return state
        try:
            return json.loads(p.read_text())
        except Exception as e:
            logger.warning("ha.json unreadable (%s); seeding default", e)
            state = _default_state()
            _save_unlocked(state)
            return state


def _save_unlocked(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(p)


def update_state(**kwargs) -> dict:
    with _state_lock:
        p = _state_path()
        state = json.loads(p.read_text()) if p.exists() else _default_state()
        state.update(kwargs)
        _save_unlocked(state)
        return state


def current_role() -> str:
    if not ha_enabled():
        return "primary"
    return load_state().get("role", "primary")


def self_id() -> str:
    return (load_state().get("self_id") or HA_SELF_ID or "A").upper()


def peer_id() -> str:
    return "B" if self_id() == "A" else "A"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Effective config (settings > env)
# ---------------------------------------------------------------------------

def _bool_setting(key: str, fallback: bool) -> bool:
    v = settings.get(key)
    if v is None:
        return fallback
    return v.lower() in ("true", "1", "yes", "on")


def ha_enabled() -> bool:
    return _bool_setting("ha.enabled", HA_ENABLED)


def ha_token() -> str:
    return settings.get("ha.token") or HA_TOKEN or ""


def _slot(letter: str) -> str:
    return letter.lower()


def node_base_url(letter: str) -> str:
    v = settings.get(f"ha.node_{_slot(letter)}.base_url")
    if v:
        return v
    if letter.upper() == peer_id():
        return HA_PEER_URL or ""
    return ""


def peer_base_url() -> str:
    return node_base_url(peer_id())


def sync_interval_seconds() -> int:
    v = settings.get("ha.sync_interval_seconds")
    if v:
        try:
            return max(5, int(v))
        except ValueError:
            pass
    return DEFAULT_SYNC_INTERVAL_SECONDS


def replication_paused() -> bool:
    return _bool_setting("ha.replication_paused", False)


def is_orphaned() -> bool:
    if current_role() == "primary":
        return False
    return bool(_read_meta().get("peer_replication_paused"))


def leave_cluster() -> dict:
    """Standby-side reset: drop replica + cluster state, return to first-run."""
    if current_role() == "primary":
        return {"ok": False, "reason": "this node is primary; refusing to reset"}

    from app.database import engine
    try:
        engine.dispose()
    except Exception:
        pass

    Path(REPLICA_DB_PATH).unlink(missing_ok=True)
    Path(REPLICA_META_PATH).unlink(missing_ok=True)

    Path(DB_PATH_STR).unlink(missing_ok=True)
    for s in ("-wal", "-shm"):
        Path(DB_PATH_STR + s).unlink(missing_ok=True)

    Path(HA_STATE_PATH).unlink(missing_ok=True)

    settings.invalidate()
    return {"ok": True, "message": "cluster state reset; refresh the page to begin first-run setup"}


# ---------------------------------------------------------------------------
# Replica metadata
# ---------------------------------------------------------------------------

def _read_meta() -> dict:
    with _meta_lock:
        p = Path(REPLICA_META_PATH)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}


def _write_meta(updates: dict) -> None:
    with _meta_lock:
        p = Path(REPLICA_META_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if p.exists():
            try:
                existing = json.loads(p.read_text())
            except Exception:
                pass
        existing.update(updates)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, indent=2))
        tmp.replace(p)


def replica_meta() -> dict:
    return _read_meta()


# ---------------------------------------------------------------------------
# Snapshot generation (primary side)
# ---------------------------------------------------------------------------

def _read_data_version() -> int | None:
    if not os.path.exists(DB_PATH_STR):
        return None
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH_STR) as con:
            return con.execute("PRAGMA data_version").fetchone()[0]
    except Exception as e:
        logger.debug("data_version read failed: %s", e)
        return None


def _build_snapshot() -> tuple[bytes, int] | None:
    snap_path = "/tmp/leaf-replica-snap.db"
    Path(snap_path).unlink(missing_ok=True)
    try:
        result = subprocess.run(
            ["sqlite3", DB_PATH_STR, f".backup {snap_path}"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.warning("snapshot .backup failed: %s", result.stderr.strip())
            return None
        raw = Path(snap_path).read_bytes()
        compressed = gzip.compress(raw, compresslevel=6)
        return compressed, len(raw)
    finally:
        Path(snap_path).unlink(missing_ok=True)


def push_snapshot_to_peer(force: bool = False) -> dict:
    if not ha_enabled():
        return {"ok": False, "reason": "HA disabled"}
    if current_role() != "primary":
        return {"ok": False, "reason": "not primary"}
    base = peer_base_url()
    if not base:
        return {"ok": False, "reason": "peer base URL not set"}
    token = ha_token()
    if not token:
        return {"ok": False, "reason": "ha.token not set"}

    version = _read_data_version()
    if version is None:
        return {"ok": False, "reason": "db unavailable"}

    last_pushed = _read_meta().get("last_pushed_data_version")
    if not force and last_pushed is not None and version == last_pushed:
        return {"ok": True, "skipped": True, "reason": "no changes since last push", "data_version": version}

    snap = _build_snapshot()
    if snap is None:
        return {"ok": False, "reason": "snapshot build failed"}
    compressed, raw_size = snap

    if len(compressed) > MAX_SNAPSHOT_BYTES:
        return {"ok": False, "reason": f"snapshot too large ({len(compressed)} > {MAX_SNAPSHOT_BYTES} bytes); raise MAX_SNAPSHOT_BYTES"}

    try:
        r = _http().post(
            f"{base.rstrip('/')}/api/ha/replica-push",
            content=compressed,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "X-HA-Sender-Id": self_id(),
                "X-HA-Data-Version": str(version),
            },
            timeout=300.0,
        )
    except Exception as e:
        return {"ok": False, "reason": f"peer unreachable: {e}"}

    if r.status_code != 200:
        return {"ok": False, "reason": f"peer returned {r.status_code}: {r.text[:200]}"}

    _write_meta({
        "last_pushed_data_version": version,
        "last_pushed_at": now_iso(),
        "last_pushed_size_bytes": len(compressed),
        "last_pushed_raw_bytes": raw_size,
    })
    return {
        "ok": True,
        "skipped": False,
        "data_version": version,
        "size_bytes": len(compressed),
        "raw_bytes": raw_size,
    }


# ---------------------------------------------------------------------------
# Snapshot reception (standby side)
# ---------------------------------------------------------------------------

def receive_replica(compressed_data: bytes, sender_id: str, data_version: str) -> dict:
    if current_role() == "primary":
        return {"ok": False, "reason": "this node is primary; refusing to overwrite live DB"}
    if len(compressed_data) > MAX_SNAPSHOT_BYTES:
        return {"ok": False, "reason": f"snapshot too large ({len(compressed_data)} bytes)"}

    tmp_path = REPLICA_DB_PATH + ".incoming"
    Path(tmp_path).unlink(missing_ok=True)
    try:
        decompressed = gzip.decompress(compressed_data)
    except Exception as e:
        return {"ok": False, "reason": f"gzip decode failed: {e}"}

    try:
        Path(tmp_path).write_bytes(decompressed)
        os.replace(tmp_path, REPLICA_DB_PATH)
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        return {"ok": False, "reason": f"write failed: {e}"}

    _write_meta({
        "last_received_data_version": data_version,
        "last_received_at": now_iso(),
        "last_received_size_bytes": len(compressed_data),
        "last_received_raw_bytes": len(decompressed),
        "sender_id": sender_id,
    })
    return {"ok": True, "raw_bytes": len(decompressed), "data_version": data_version}


# ---------------------------------------------------------------------------
# Promotion (standby -> primary)
# ---------------------------------------------------------------------------

def promote_to_primary() -> dict:
    """Move the replica DB into place, drop the engine pool, become primary."""
    if not Path(REPLICA_DB_PATH).exists():
        logger.warning("no replica DB found; promoting with local DB as-is")
    else:
        from app.database import engine
        engine.dispose()
        os.replace(REPLICA_DB_PATH, DB_PATH_STR)
        for suffix in ("-wal", "-shm"):
            Path(DB_PATH_STR + suffix).unlink(missing_ok=True)
        settings.invalidate()

    update_state(role="primary", last_promoted_at=now_iso())
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sync scheduler
# ---------------------------------------------------------------------------

def start_sync_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler = BackgroundScheduler(daemon=True)
    interval = sync_interval_seconds()
    _scheduler.add_job(_sync_tick, "interval", seconds=interval, id="ha_sync")
    _scheduler.start()
    logger.info("HA sync scheduler started (every %ds)", interval)


def _sync_tick() -> None:
    if not ha_enabled():
        return
    if not peer_base_url() or not ha_token():
        return

    role = current_role()

    if role == "primary":
        if replication_paused():
            if peer_status() is not None:
                _write_meta({"last_seen_peer_at": now_iso()})
            return

        result = push_snapshot_to_peer()
        if result.get("ok"):
            if not result.get("skipped"):
                logger.info(
                    "ha sync: pushed %d bytes (raw=%d, data_version=%s)",
                    result.get("size_bytes", 0), result.get("raw_bytes", 0), result.get("data_version"),
                )
            else:
                if peer_status() is not None:
                    _write_meta({"last_seen_peer_at": now_iso()})
        else:
            logger.warning("ha sync failed: %s", result.get("reason"))
    else:
        peer = peer_status()
        if peer is not None:
            _write_meta({
                "last_seen_peer_at": now_iso(),
                "peer_replication_paused": bool(peer.get("replication_paused")),
            })


# ---------------------------------------------------------------------------
# Peer HTTP client
# ---------------------------------------------------------------------------

def peer_status() -> dict | None:
    """GET /api/ha/status on the peer. Used by sync tick + failover only.

    NEVER call from a request path -- per-request httpx leaks FDs fast.
    """
    base = peer_base_url()
    if not base:
        return None
    try:
        r = _http().get(f"{base.rstrip('/')}/api/ha/status")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug("peer_status unreachable: %s", e)
    return None


def peer_recently_seen() -> bool:
    meta = _read_meta()
    role = current_role()
    candidates = [meta.get("last_seen_peer_at")]
    if role == "primary":
        candidates.append(meta.get("last_pushed_at"))
    else:
        candidates.append(meta.get("last_received_at"))
    timestamps = [c for c in candidates if c]
    if not timestamps:
        return False
    try:
        latest = max(datetime.fromisoformat(t) for t in timestamps)
    except Exception:
        return False
    age = (datetime.now(timezone.utc) - latest).total_seconds()
    return age < 3 * sync_interval_seconds()


def demote_peer() -> tuple[bool, str]:
    base = peer_base_url()
    if not base:
        return False, "peer base URL not set"
    token = ha_token()
    if not token:
        return False, "ha.token not set"
    try:
        r = _http().post(
            f"{base.rstrip('/')}/api/ha/demote",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        if r.status_code == 200:
            return True, "peer demoted"
        return False, f"peer returned {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"peer unreachable: {e}"


def call_peer_register(my_id: str, my_base_url: str) -> tuple[bool, str]:
    base = peer_base_url()
    token = ha_token()
    if not base or not token:
        return False, "peer not configured"
    try:
        r = _http().post(
            f"{base.rstrip('/')}/api/ha/register-peer",
            headers={"Authorization": f"Bearer {token}"},
            json={"id": my_id, "base_url": my_base_url},
            timeout=10.0,
        )
        if r.status_code == 200:
            return True, "registered"
        return False, f"{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Pairing v3 -- minimal: base URL + token + KEK
# ---------------------------------------------------------------------------

def generate_pairing_secret(my_base_url: str = "") -> dict:
    settings.set("ha.enabled", "true")

    token = ha_token()
    if not token:
        token = _secrets.token_urlsafe(32)
        settings.set("ha.token", token, encrypted=True)

    me = self_id()
    base_url = my_base_url or node_base_url(me)
    if base_url:
        settings.set(f"ha.node_{_slot(me)}.base_url", base_url)

    from app.settings import _resolve_kek
    payload = {
        "v": 3,
        "primary_self_id": me,
        "primary_base_url": base_url,
        "ha_token": token,
        "kek": base64.urlsafe_b64encode(_resolve_kek()).decode(),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return {"pairing_secret": encoded}


def accept_pairing_secret(encoded: str, my_base_url: str) -> dict:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    except Exception as e:
        return {"ok": False, "reason": f"invalid pairing secret: {e}"}

    if decoded.get("v") != 3:
        return {"ok": False, "reason": "pairing version mismatch (need v3)"}

    primary_id = (decoded.get("primary_self_id") or "").upper()
    if primary_id not in ("A", "B"):
        return {"ok": False, "reason": "missing primary_self_id"}
    my_id = "B" if primary_id == "A" else "A"

    kek_b64 = decoded.get("kek")
    if kek_b64:
        new_kek = base64.urlsafe_b64decode(kek_b64.encode())
        _swap_kek(new_kek)

    settings.set(f"ha.node_{_slot(primary_id)}.base_url", decoded.get("primary_base_url", ""))
    settings.set("ha.token", decoded["ha_token"], encrypted=True)
    settings.set(f"ha.node_{_slot(my_id)}.base_url", my_base_url)

    update_state(self_id=my_id, role="standby")
    settings.set("ha.enabled", "true")

    registered, register_msg = call_peer_register(my_id, my_base_url)

    peer = peer_status()
    return {
        "ok": True,
        "self_id": my_id,
        "registered_with_peer": registered,
        "register_msg": register_msg,
        "peer_reachable": peer is not None,
        "peer_role": peer.get("role") if peer else None,
    }


def register_incoming_peer(peer_id_letter: str, base_url: str) -> dict:
    pid = peer_id_letter.upper()
    if pid not in ("A", "B"):
        return {"ok": False, "reason": "invalid peer id"}
    if pid == self_id():
        return {"ok": False, "reason": "peer claims our self_id"}
    settings.set(f"ha.node_{_slot(pid)}.base_url", base_url)
    settings.set("ha.enabled", "true")
    return {"ok": True}


def _swap_kek(new_kek: bytes) -> None:
    """Re-encrypt all encrypted rows with new KEK, then install it."""
    from app.config import SETTINGS_KEK_PATH
    from cryptography.fernet import Fernet, InvalidToken
    from sqlalchemy import text
    from app.database import SessionLocal
    import app.settings as _s

    old_fernet = _s._get_fernet()
    new_fernet = Fernet(new_kek)

    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT key, value FROM settings WHERE encrypted=1")).fetchall()
        re_encrypted = []
        for key, encrypted_value in rows:
            try:
                plain = old_fernet.decrypt(encrypted_value.encode()).decode()
            except InvalidToken:
                logger.warning("could not decrypt %s during KEK swap; skipping", key)
                continue
            re_encrypted.append((key, new_fernet.encrypt(plain.encode()).decode()))
        for key, new_value in re_encrypted:
            db.execute(
                text("UPDATE settings SET value=:v, updated_at=CURRENT_TIMESTAMP WHERE key=:k"),
                {"k": key, "v": new_value},
            )
        db.commit()
    finally:
        db.close()

    Path(SETTINGS_KEK_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(SETTINGS_KEK_PATH).write_bytes(new_kek)
    try:
        os.chmod(SETTINGS_KEK_PATH, 0o600)
    except OSError:
        pass

    _s._fernet = None
    settings.invalidate()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def reconfigure(changed_key: str = "") -> None:
    logger.info("ha.reconfigure (%s)", changed_key or "startup")


def on_startup() -> None:
    settings.on_change("ha.", reconfigure)
    start_sync_scheduler()
    if ha_enabled():
        logger.info("HA enabled; self_id=%s role=%s", self_id(), current_role())
    else:
        logger.info("HA disabled")


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None


atexit.register(shutdown)
