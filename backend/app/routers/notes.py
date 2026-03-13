import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Note, Tag, note_tags
from app.schemas import NoteCreate, NoteUpdate, NoteOut, NoteSummary, NoteOutFull, NoteSummaryFull, QuickNoteCreate
from app.auth import require_auth, require_auth_or_public
from app.routers.folders import resolve_folder_path, ensure_folder_path, build_folder_breadcrumb

router = APIRouter(prefix="/api/notes", tags=["notes"])


def make_excerpt(content: str, length: int = 120) -> str:
    """Strip markdown syntax and return a plain-text excerpt."""
    text = re.sub(r'[#*`~>\[\]!|]', '', content)
    text = re.sub(r'\(https?://[^\)]+\)', '', text)
    text = ' '.join(text.split())
    return text[:length].rstrip() + ('...' if len(text) > length else '')


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


def _note_with_permalink(note: Note, request: Request) -> dict:
    """Add permalink to a note response."""
    out = NoteOut.model_validate(note).model_dump()
    base = str(request.base_url).rstrip('/')
    out['permalink'] = f"{base}/note/{note.id}"
    return out


def _note_summaries(notes: list[Note]) -> list[NoteSummary]:
    return [
        NoteSummary(
            **{k: v for k, v in NoteSummary.model_validate(n).model_dump().items() if k != 'excerpt'},
            excerpt=make_excerpt(n.content or ''),
        )
        for n in notes
    ]


@router.get("")
def list_notes(
    request: Request,
    id: int | None = None,
    folder_id: int | None = None,
    root: bool = False,
    tag: str | None = None,
    pinned: bool | None = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_auth_or_public),
):
    # Single note lookup by ID
    if id is not None:
        note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == id).first()
        if not note:
            raise HTTPException(404, "Note not found")
        from app.config import get_auth_enabled
        if get_auth_enabled() and user is None and not note.is_public:
            raise HTTPException(404, "Note not found")
        return _note_with_permalink(note, request)

    q = db.query(Note).options(joinedload(Note.tags))
    if root:
        q = q.filter(Note.folder_id == None)
    elif folder_id is not None:
        q = q.filter(Note.folder_id == folder_id)
    if tag:
        q = q.join(note_tags).join(Tag).filter(Tag.name == tag.lower())
    if pinned is not None:
        q = q.filter(Note.pinned == pinned)
    q = q.order_by(Note.pinned.desc(), Note.updated_at.desc())
    return _note_summaries(q.offset(offset).limit(limit).all())


@router.post("", response_model=NoteOut, status_code=201)
def create_note(request: Request, body: NoteCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    note = Note(
        title=body.title,
        slug=slugify(body.title),
        content=body.content,
        folder_id=body.folder_id,
        is_public=body.is_public,
        pinned=body.pinned,
        default_view=body.default_view,
    )
    if body.tags:
        note.tags = get_or_create_tags(db, body.tags)
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_with_permalink(note, request)


@router.post("/quick", response_model=NoteOutFull, status_code=201, tags=["llm"])
def quick_create_note(body: QuickNoteCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    """LLM-friendly endpoint: create or update a note with auto folder creation.

    - Set `folder` to a path like "infrastructure/docker" and folders are created automatically.
    - Set `upsert: true` to update an existing note with the same title in the same folder.
    """
    folder_id = None
    folder_path = None
    if body.folder:
        folder = ensure_folder_path(db, body.folder)
        folder_id = folder.id
        folder_path = body.folder

    slug = slugify(body.title)

    if body.upsert:
        existing = db.query(Note).options(joinedload(Note.tags)).filter(
            Note.slug == slug, Note.folder_id == folder_id
        ).first()
        if existing:
            existing.content = body.content
            existing.is_public = body.is_public
            existing.pinned = body.pinned
            if body.tags:
                existing.tags = get_or_create_tags(db, body.tags)
            db.commit()
            db.refresh(existing)
            return NoteOutFull(
                **{k: v for k, v in NoteOut.model_validate(existing).model_dump().items()},
                folder_path=build_folder_breadcrumb(db, existing.folder_id),
            )

    note = Note(
        title=body.title,
        slug=slug,
        content=body.content,
        folder_id=folder_id,
        is_public=body.is_public,
        pinned=body.pinned,
    )
    if body.tags:
        note.tags = get_or_create_tags(db, body.tags)
    db.add(note)
    db.commit()
    db.refresh(note)
    return NoteOutFull(
        **{k: v for k, v in NoteOut.model_validate(note).model_dump().items()},
        folder_path=folder_path or "",
    )


@router.get("/full", response_model=list[NoteSummaryFull], tags=["llm"])
def list_notes_full(
    folder: str | None = None,
    tag: str | None = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """LLM-friendly: list notes with folder paths included. Filter by folder path or tag."""
    q = db.query(Note).options(joinedload(Note.tags))
    if folder:
        f = resolve_folder_path(db, folder)
        if not f:
            return []
        q = q.filter(Note.folder_id == f.id)
    if tag:
        q = q.join(note_tags).join(Tag).filter(Tag.name == tag.lower())
    q = q.order_by(Note.pinned.desc(), Note.updated_at.desc())
    notes = q.offset(offset).limit(limit).all()
    return [
        NoteSummaryFull(
            **{k: v for k, v in NoteSummary.model_validate(n).model_dump().items()},
            folder_path=build_folder_breadcrumb(db, n.folder_id),
        )
        for n in notes
    ]


@router.get("/by-slug/{slug}", response_model=NoteOut)
def get_note_by_slug(request: Request, slug: str, db: Session = Depends(get_db), user=Depends(require_auth_or_public)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.slug == slug).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from app.config import get_auth_enabled
    if get_auth_enabled() and user is None and not note.is_public:
        raise HTTPException(404, "Note not found")
    return _note_with_permalink(note, request)


@router.get("/{note_id:int}", response_model=NoteOut)
def get_note(request: Request, note_id: int, db: Session = Depends(get_db), user=Depends(require_auth_or_public)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from app.config import get_auth_enabled
    if get_auth_enabled() and user is None and not note.is_public:
        raise HTTPException(404, "Note not found")
    return _note_with_permalink(note, request)


@router.put("/{note_id:int}", response_model=NoteOut)
def update_note(request: Request, note_id: int, body: NoteUpdate, db: Session = Depends(get_db), _=Depends(require_auth)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    if body.title is not None:
        note.title = body.title
        note.slug = slugify(body.title)
    if body.content is not None:
        note.content = body.content
    if 'folder_id' in body.model_fields_set:
        note.folder_id = body.folder_id
    if body.is_public is not None:
        note.is_public = body.is_public
    if body.pinned is not None:
        note.pinned = body.pinned
    if body.tags is not None:
        note.tags = get_or_create_tags(db, body.tags)
    if body.default_view is not None:
        note.default_view = body.default_view if body.default_view != "" else None
    db.commit()
    db.refresh(note)
    return _note_with_permalink(note, request)


@router.delete("/{note_id:int}", status_code=204)
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
    return _note_summaries(q.order_by(Note.updated_at.desc()).offset(offset).limit(limit).all())


@router.get("/public/{note_id:int}", response_model=NoteOut)
def get_public_note(request: Request, note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    from app.config import get_auth_enabled
    if get_auth_enabled() and not note.is_public:
        raise HTTPException(404, "Note not found")
    return _note_with_permalink(note, request)


@router.get("/{path:path}")
def browse_by_path(request: Request, path: str, db: Session = Depends(get_db), user=Depends(require_auth_or_public)):
    """Path-based browsing: /api/notes/folder/subfolder lists notes, /api/notes/folder/subfolder/note-slug returns a note."""
    path = path.strip("/")
    if not path:
        raise HTTPException(404, "Not found")

    # Try full path as a folder → list notes in it
    folder = resolve_folder_path(db, path)
    if folder:
        notes = db.query(Note).options(joinedload(Note.tags)).filter(
            Note.folder_id == folder.id
        ).order_by(Note.pinned.desc(), Note.updated_at.desc()).all()
        return _note_summaries(notes)

    # Try all-but-last as folder + last segment as note slug
    parts = path.rsplit("/", 1)
    if len(parts) == 2:
        folder_path, note_slug = parts
        folder = resolve_folder_path(db, folder_path)
        if folder:
            note = db.query(Note).options(joinedload(Note.tags)).filter(
                Note.slug == note_slug, Note.folder_id == folder.id
            ).first()
            if note:
                from app.config import get_auth_enabled
                if get_auth_enabled() and user is None and not note.is_public:
                    raise HTTPException(404, "Not found")
                return _note_with_permalink(note, request)

    # Single segment: try as root-level note slug (no folder)
    if "/" not in path:
        note = db.query(Note).options(joinedload(Note.tags)).filter(
            Note.slug == path, Note.folder_id == None
        ).first()
        if note:
            from app.config import get_auth_enabled
            if get_auth_enabled() and user is None and not note.is_public:
                raise HTTPException(404, "Not found")
            return _note_with_permalink(note, request)

    raise HTTPException(404, "Not found")
