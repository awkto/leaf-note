import uuid
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Image
from app.auth import require_auth

router = APIRouter(prefix="/api/images", tags=["images"])

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
MAX_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "Image too large (max 10MB)")

    ext = mimetypes.guess_extension(file.content_type) or ".png"
    if ext == ".jpe":
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"

    image = Image(
        filename=filename,
        content_type=file.content_type,
        size_bytes=len(data),
        data=data,
    )
    db.add(image)
    db.commit()

    return {"url": f"/api/images/{filename}", "filename": filename}


@router.get("/{filename}")
def get_image(filename: str, db: Session = Depends(get_db)):
    if "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")

    image = db.query(Image).filter(Image.filename == filename).first()
    if not image:
        raise HTTPException(404, "Image not found")

    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
