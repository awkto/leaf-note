from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from app.database import get_db
from app.models import Note, Tag, note_tags
from app.schemas import SearchResult, NoteSummary
from app.auth import require_auth

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResult)
def search_notes(
    q: str = Query(..., min_length=1),
    tag: str | None = None,
    folder_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    query = db.query(Note).options(joinedload(Note.tags))
    pattern = f"%{q}%"
    query = query.filter(or_(
        Note.title.ilike(pattern),
        Note.content.ilike(pattern),
    ))
    if tag:
        query = query.join(note_tags).join(Tag).filter(Tag.name == tag.lower())
    if folder_id is not None:
        query = query.filter(Note.folder_id == folder_id)

    total = query.count()
    notes = query.order_by(Note.updated_at.desc()).offset(offset).limit(limit).all()
    return SearchResult(notes=notes, total=total)
