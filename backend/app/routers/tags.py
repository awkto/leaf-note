from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Tag
from app.schemas import TagCreate, TagOut
from app.auth import require_auth

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db), _=Depends(require_auth)):
    return db.query(Tag).order_by(Tag.name).all()


@router.post("", response_model=TagOut, status_code=201)
def create_tag(body: TagCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    existing = db.query(Tag).filter(Tag.name == body.name.lower()).first()
    if existing:
        raise HTTPException(409, "Tag already exists")
    tag = Tag(name=body.name.lower(), color=body.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.put("/{tag_id}", response_model=TagOut)
def update_tag(tag_id: int, body: TagCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
    tag.name = body.name.lower()
    tag.color = body.color
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
    db.delete(tag)
    db.commit()
