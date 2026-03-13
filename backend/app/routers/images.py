import uuid
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from app.config import IMAGES_DIR, ensure_dirs
from app.auth import require_auth

router = APIRouter(prefix="/api/images", tags=["images"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("")
async def upload_image(file: UploadFile = File(...), _=Depends(require_auth)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "Image too large (max 10MB)")

    ext = mimetypes.guess_extension(file.content_type) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"

    ensure_dirs()
    (IMAGES_DIR / filename).write_bytes(data)

    return {"url": f"/api/images/{filename}", "filename": filename}


@router.get("/{filename}")
def get_image(filename: str):
    if "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = IMAGES_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Image not found")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
