import os
import yaml
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
CONFIG_FILE = DATA_DIR / "config.yaml"
DB_PATH = DATA_DIR / "leaf.db"
NOTES_DIR = DATA_DIR / "notes"
IMAGES_DIR = DATA_DIR / "images"

APP_VERSION = os.environ.get("APP_VERSION", "dev")

# ---------------------------------------------------------------------------
# HA / replication
# ---------------------------------------------------------------------------

HA_ENABLED = os.getenv("HA_ENABLED", "").lower() in ("true", "1", "yes")
HA_SELF_ID = os.getenv("HA_SELF_ID", "A")
HA_INITIAL_ROLE = os.getenv("HA_INITIAL_ROLE", "primary")
HA_PEER_URL = os.getenv("HA_PEER_URL", "")
HA_TOKEN = os.getenv("HA_TOKEN", "")
HA_STATE_PATH = os.getenv("HA_STATE_PATH", str(DATA_DIR / "ha.json"))

# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

BACKUP_DIR = os.getenv("BACKUP_DIR", str(DATA_DIR / "backups"))
BACKUP_INTERVAL_SECONDS = int(os.getenv("BACKUP_INTERVAL_SECONDS", "900"))
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "14"))

# ---------------------------------------------------------------------------
# Settings encryption
# ---------------------------------------------------------------------------

# Key-encryption-key for Fernet-wrapping secrets in the settings table.
# If unset, a key is auto-generated at first boot and persisted to
# SETTINGS_KEK_PATH. For HA, the KEK travels in the pairing bundle so both
# nodes can decrypt secrets that replicate via the DB.
SETTINGS_KEK = os.getenv("SETTINGS_KEK", "")
SETTINGS_KEK_PATH = os.getenv("SETTINGS_KEK_PATH", str(DATA_DIR / "settings-kek"))


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(cfg: dict):
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)


def get_auth_enabled() -> bool:
    cfg = load_config()
    return cfg.get("auth_enabled", False)


def get_admin_password_hash() -> str | None:
    cfg = load_config()
    return cfg.get("admin_password_hash")


def get_api_key() -> str | None:
    cfg = load_config()
    return cfg.get("api_key")
