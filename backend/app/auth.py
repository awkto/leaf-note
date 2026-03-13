import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import get_auth_enabled, get_admin_password_hash, get_api_key, load_config, save_config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

JWT_SECRET = None
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72


def _get_jwt_secret() -> str:
    global JWT_SECRET
    if JWT_SECRET:
        return JWT_SECRET
    cfg = load_config()
    if "jwt_secret" not in cfg:
        cfg["jwt_secret"] = secrets.token_hex(32)
        save_config(cfg)
    JWT_SECRET = cfg["jwt_secret"]
    return JWT_SECRET


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(subject: str = "admin") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": subject, "exp": expire}, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def generate_api_key() -> str:
    key = f"leaf_{secrets.token_hex(24)}"
    cfg = load_config()
    cfg["api_key"] = key
    save_config(cfg)
    return key


def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if not get_auth_enabled():
        return None

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    api_key = get_api_key()
    if api_key and token == api_key:
        return "api_key"

    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload.get("sub", "admin")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_auth_or_public(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """For endpoints that may serve public content - doesn't raise, returns None if unauthed."""
    if not get_auth_enabled():
        return None

    if credentials is None:
        return None

    token = credentials.credentials
    api_key = get_api_key()
    if api_key and token == api_key:
        return "api_key"

    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload.get("sub", "admin")
    except JWTError:
        return None
