import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Note, Tag, note_tags
from app.schemas import NoteCreate, NoteUpdate, NoteOut, NoteSummary
from app.auth import require_auth, require_auth_or_public

router = APIRouter(prefix="/api/notes", tags=["notes"])


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def get_or_create_tags(db: Session, tag_names: list[str]) -> list[Tag]:
    tags = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    return tags


@router.get("", response_model=list[NoteSummary])
def list_notes(
    folder_id: int | None = None,
    tag: str | None = None,
    pinned: bool | None = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    q = db.query(Note).options(joinedload(Note.tags))
    if folder_id is not None:
        q = q.filter(Note.folder_id == folder_id)
    if tag:
        q = q.join(note_tags).join(Tag).filter(Tag.name == tag.lower())
    if pinned is not None:
        q = q.filter(Note.pinned == pinned)
    q = q.order_by(Note.pinned.desc(), Note.updated_at.desc())
    return q.offset(offset).limit(limit).all()


@router.post("", response_model=NoteOut, status_code=201)
def create_note(body: NoteCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    note = Note(
        title=body.title,
        slug=slugify(body.title),
        content=body.content,
        folder_id=body.folder_id,
        is_public=body.is_public,
        pinned=body.pinned,
    )
    if body.tags:
        note.tags = get_or_create_tags(db, body.tags)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/by-slug/{slug}", response_model=NoteOut)
def get_note_by_slug(slug: str, db: Session = Depends(get_db), user=Depends(require_auth_or_public)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.slug == slug).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from app.config import get_auth_enabled
    if get_auth_enabled() and user is None and not note.is_public:
        raise HTTPException(404, "Note not found")
    return note


@router.get("/{note_id}", response_model=NoteOut)
def get_note(note_id: int, db: Session = Depends(get_db), user=Depends(require_auth_or_public)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from app.config import get_auth_enabled
    if get_auth_enabled() and user is None and not note.is_public:
        raise HTTPException(404, "Note not found")
    return note


@router.put("/{note_id}", response_model=NoteOut)
def update_note(note_id: int, body: NoteUpdate, db: Session = Depends(get_db), _=Depends(require_auth)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    if body.title is not None:
        note.title = body.title
        note.slug = slugify(body.title)
    if body.content is not None:
        note.content = body.content
    if body.folder_id is not None:
        note.folder_id = body.folder_id
    if body.is_public is not None:
        note.is_public = body.is_public
    if body.pinned is not None:
        note.pinned = body.pinned
    if body.tags is not None:
        note.tags = get_or_create_tags(db, body.tags)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()


@router.get("/public/list", response_model=list[NoteSummary])
def list_public_notes(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Note).options(joinedload(Note.tags)).filter(Note.is_public == True)
    return q.order_by(Note.updated_at.desc()).offset(offset).limit(limit).all()


@router.get("/public/{note_id}", response_model=NoteOut)
def get_public_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from app.config import get_auth_enabled
    if get_auth_enabled() and not note.is_public:
        raise HTTPException(404, "Note not found")
    return note
