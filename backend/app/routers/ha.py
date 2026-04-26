"""HA status, pairing, replication, and failover endpoints.

Routing layout:
  /api/ha/status            -- open (peer polls this)
  /api/ha/demote            -- HA_TOKEN auth
  /api/ha/replica-push      -- HA_TOKEN auth (snapshot upload)
  /api/ha/register-peer     -- HA_TOKEN auth (back-leg of pairing)
  /api/ha/failover          -- session OR HA_TOKEN auth
  /api/ha/backup, /backups  -- session OR HA_TOKEN auth
  /api/ha/config GET/PUT    -- session OR HA_TOKEN auth
  /api/ha/generate-pairing  -- session OR HA_TOKEN auth
  /api/ha/accept-pairing    -- open if first_run, else session/HA_TOKEN

All HA endpoints bypass the standby write-block middleware.

Ported from awkto/atlas-inventory.
"""
import hmac
import logging
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import backup, ha, settings
from app.auth import is_first_run, validate_bearer
from app.config import DB_PATH

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ha", tags=["ha"])

DB_PATH_STR = str(DB_PATH)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class FailoverRequest(BaseModel):
    force: bool = False


class HAConfigUpdate(BaseModel):
    enabled: bool | None = None
    node_a_base_url: str | None = None
    node_b_base_url: str | None = None
    sync_interval_seconds: int | None = None
    replication_paused: bool | None = None


class GeneratePairingRequest(BaseModel):
    my_base_url: str | None = None


class AcceptPairingRequest(BaseModel):
    pairing_secret: str
    my_base_url: str


class RegisterPeerRequest(BaseModel):
    id: str
    base_url: str


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else None


def _require_ha_token(request: Request) -> None:
    token = ha.ha_token()
    if not token:
        raise HTTPException(500, "ha.token not configured")
    provided = _bearer(request)
    if not provided or not hmac.compare_digest(provided, token):
        raise HTTPException(401, "invalid or missing HA token")


def _require_session_or_ha_token(request: Request) -> None:
    provided = _bearer(request)
    if not provided:
        # If auth isn't enabled at all, treat the request as authorized -- this
        # mirrors leaf's other routers which let unauthenticated callers in
        # when auth_enabled=false.
        if is_first_run():
            return
        raise HTTPException(401, "missing bearer token")
    if validate_bearer(provided):
        return
    token = ha.ha_token()
    if token and hmac.compare_digest(provided, token):
        return
    raise HTTPException(401, "invalid token")


# ---------------------------------------------------------------------------
# Status / config
# ---------------------------------------------------------------------------

@router.get("/status")
def ha_status():
    if not ha.ha_enabled():
        return {"enabled": False, "role": "primary"}

    state = ha.load_state()

    data_version = None
    try:
        with sqlite3.connect(DB_PATH_STR) as con:
            data_version = con.execute("PRAGMA data_version").fetchone()[0]
    except Exception:
        pass

    recently_synced = ha.peer_recently_seen()

    return {
        "enabled": True,
        "role": state.get("role"),
        "self_id": ha.self_id(),
        "peer_id": ha.peer_id(),
        "peer_url": ha.peer_base_url(),
        "peer_reachable": recently_synced,
        "peer_role": None,
        "replication_paused": ha.replication_paused(),
        "is_orphaned": ha.is_orphaned(),
        "last_promoted_at": state.get("last_promoted_at"),
        "last_demoted_at": state.get("last_demoted_at"),
        "sync_interval_seconds": ha.sync_interval_seconds(),
        "replica_meta": ha.replica_meta(),
        "last_backup": backup.last_backup_info(),
        "data_version": data_version,
    }


@router.get("/config")
def get_config(request: Request):
    _require_session_or_ha_token(request)
    return {
        "enabled": ha.ha_enabled(),
        "self_id": ha.self_id(),
        "peer_id": ha.peer_id(),
        "token_set": bool(ha.ha_token()),
        "sync_interval_seconds": ha.sync_interval_seconds(),
        "replication_paused": ha.replication_paused(),
        "node_a": {"base_url": ha.node_base_url("A")},
        "node_b": {"base_url": ha.node_base_url("B")},
    }


@router.put("/config")
def update_config(body: HAConfigUpdate, request: Request):
    _require_session_or_ha_token(request)
    changed = []
    if body.enabled is not None:
        settings.set("ha.enabled", "true" if body.enabled else "false")
        changed.append("enabled")
    if body.node_a_base_url is not None:
        settings.set("ha.node_a.base_url", body.node_a_base_url)
        changed.append("node_a.base_url")
    if body.node_b_base_url is not None:
        settings.set("ha.node_b.base_url", body.node_b_base_url)
        changed.append("node_b.base_url")
    if body.sync_interval_seconds is not None:
        settings.set("ha.sync_interval_seconds", str(max(5, body.sync_interval_seconds)))
        changed.append("sync_interval_seconds")
    if body.replication_paused is not None:
        settings.set("ha.replication_paused", "true" if body.replication_paused else "false")
        changed.append("replication_paused")
    return {"ok": True, "changed": changed}


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

@router.post("/generate-pairing")
def generate_pairing(body: GeneratePairingRequest, request: Request):
    _require_session_or_ha_token(request)
    if ha.load_state().get("role") != "primary":
        raise HTTPException(400, "only the primary can generate a pairing secret")
    return ha.generate_pairing_secret(my_base_url=body.my_base_url or "")


@router.post("/accept-pairing")
def accept_pairing(body: AcceptPairingRequest, request: Request):
    if not is_first_run():
        _require_session_or_ha_token(request)
    result = ha.accept_pairing_secret(body.pairing_secret, body.my_base_url)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "pairing failed"))
    return result


@router.post("/register-peer")
def register_peer(body: RegisterPeerRequest, request: Request):
    _require_ha_token(request)
    result = ha.register_incoming_peer(body.id, body.base_url)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "register failed"))
    return result


# ---------------------------------------------------------------------------
# Replication
# ---------------------------------------------------------------------------

@router.post("/replica-push")
async def replica_push(request: Request):
    _require_ha_token(request)

    sender_id = request.headers.get("X-HA-Sender-Id", "")
    data_version = request.headers.get("X-HA-Data-Version", "")

    body = await request.body()
    if not body:
        raise HTTPException(400, "empty body")

    result = ha.receive_replica(body, sender_id=sender_id, data_version=data_version)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "replica push failed"))
    return result


@router.post("/sync-now")
def sync_now(request: Request):
    _require_session_or_ha_token(request)
    return ha.push_snapshot_to_peer(force=True)


# ---------------------------------------------------------------------------
# Failover / demote
# ---------------------------------------------------------------------------

@router.post("/failover")
def failover(body: FailoverRequest, request: Request):
    _require_session_or_ha_token(request)

    if not ha.ha_enabled():
        raise HTTPException(400, "HA is not enabled")

    state = ha.load_state()
    if state.get("role") == "primary":
        raise HTTPException(400, "already primary")

    peer = ha.peer_status()
    if peer and peer.get("role") == "primary" and not body.force:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "peer is still primary",
                "hint": "set force=true only if you are certain the peer is unreachable",
                "peer": {"role": peer.get("role"), "url": ha.peer_base_url()},
            },
        )

    promoted = ha.promote_to_primary()
    demoted, demote_msg = ha.demote_peer()

    return {
        "ok": True,
        "new_role": "primary",
        "promoted": promoted.get("ok"),
        "promote_msg": promoted.get("reason", "ok"),
        "peer_demoted": demoted,
        "demote_msg": demote_msg,
    }


@router.post("/demote")
def demote(request: Request):
    _require_ha_token(request)
    if not ha.ha_enabled():
        raise HTTPException(400, "HA is not enabled")
    ha.update_state(role="standby", last_demoted_at=ha.now_iso())
    return {"ok": True, "new_role": "standby"}


@router.post("/leave-cluster")
def leave_cluster(request: Request):
    _require_session_or_ha_token(request)
    result = ha.leave_cluster()
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "leave-cluster failed"))
    return result


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

@router.post("/backup")
def trigger_backup(request: Request, force: bool = False):
    _require_session_or_ha_token(request)
    return backup.run_backup(force=force)


@router.get("/backups")
def list_backups(request: Request):
    _require_session_or_ha_token(request)
    return backup.list_backups()
