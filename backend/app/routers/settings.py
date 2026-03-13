from fastapi import APIRouter, Depends, HTTPException
from app.config import load_config, save_config, get_auth_enabled, APP_VERSION
from app.schemas import SettingsOut, SetupRequest, LoginRequest, LoginResponse
from app.auth import require_auth, hash_password, verify_password, create_token, generate_api_key

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
def get_settings(_=Depends(require_auth)):
    cfg = load_config()
    return SettingsOut(
        auth_enabled=cfg.get("auth_enabled", False),
        api_key=cfg.get("api_key"),
        version=APP_VERSION,
        default_view=cfg.get("default_view", "source"),
    )


@router.post("/auth/setup")
def setup_admin(body: SetupRequest):
    cfg = load_config()
    if cfg.get("admin_password_hash"):
        raise HTTPException(400, "Admin already configured. Use login instead.")
    cfg["auth_enabled"] = True
    cfg["admin_password_hash"] = hash_password(body.admin_password)
    cfg["api_key"] = generate_api_key() if not cfg.get("api_key") else cfg["api_key"]
    save_config(cfg)
    token = create_token()
    return LoginResponse(token=token)


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if not get_auth_enabled():
        return LoginResponse(token="")
    cfg = load_config()
    pw_hash = cfg.get("admin_password_hash", "")
    if not verify_password(body.password, pw_hash):
        raise HTTPException(401, "Invalid password")
    return LoginResponse(token=create_token())


@router.post("/auth/regenerate-api-key")
def regenerate_api_key(_=Depends(require_auth)):
    if not get_auth_enabled():
        raise HTTPException(400, "Auth is not enabled")
    key = generate_api_key()
    return {"api_key": key}


@router.put("/settings/default-view")
def set_default_view(body: dict, _=Depends(require_auth)):
    view = body.get("default_view", "source")
    if view not in ("source", "preview"):
        raise HTTPException(400, "default_view must be 'source' or 'preview'")
    cfg = load_config()
    cfg["default_view"] = view
    save_config(cfg)
    return {"default_view": view}


@router.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}
