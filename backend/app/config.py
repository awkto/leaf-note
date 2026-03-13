import os
import yaml
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
CONFIG_FILE = DATA_DIR / "config.yaml"
DB_PATH = DATA_DIR / "leaf.db"
NOTES_DIR = DATA_DIR / "notes"
IMAGES_DIR = DATA_DIR / "images"

APP_VERSION = os.environ.get("APP_VERSION", "dev")


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
