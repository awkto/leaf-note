import io
import re
import zipfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Note, Folder, Tag
from app.schemas import ImportResult
from app.auth import require_auth

router = APIRouter(prefix="/api", tags=["import/export"])


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_folder_path(db: Session, folder_id: int | None) -> str:
    if not folder_id:
        return ""
    parts = []
    fid = folder_id
    while fid:
        folder = db.get(Folder, fid)
        if not folder:
            break
        parts.insert(0, folder.slug)
        fid = folder.parent_id
    return "/".join(parts)


def build_frontmatter(note: Note) -> str:
    lines = ["---"]
    lines.append(f"title: \"{note.title}\"")
    if note.tags:
        tag_names = ", ".join(t.name for t in note.tags)
        lines.append(f"tags: [{tag_names}]")
    if note.is_public:
        lines.append("public: true")
    if note.pinned:
        lines.append("pinned: true")
    lines.append(f"created: {note.created_at.isoformat()}")
    lines.append(f"updated: {note.updated_at.isoformat()}")
    lines.append("---\n")
    return "\n".join(lines)


@router.get("/export/markdown")
def export_all_markdown(db: Session = Depends(get_db), _=Depends(require_auth)):
    notes = db.query(Note).options(joinedload(Note.tags)).all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for note in notes:
            path = build_folder_path(db, note.folder_id)
            filename = f"{note.slug}.md"
            if path:
                filename = f"{path}/{filename}"
            content = build_frontmatter(note) + note.content
            zf.writestr(filename, content)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=leaf-notes-export.zip"},
    )


@router.get("/export/note/{note_id}")
def export_single_note(note_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")
    content = build_frontmatter(note) + note.content
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={note.slug}.md"},
    )


def parse_frontmatter(text: str) -> tuple[dict, str]:
    meta = {}
    content = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"')
                    if key == "tags":
                        val = [t.strip() for t in val.strip("[]").split(",") if t.strip()]
                    elif key in ("public", "pinned"):
                        val = val.lower() == "true"
                    meta[key] = val
            content = parts[2].strip()
    return meta, content


@router.put("/import/note/{note_id}")
async def import_replace_note(
    note_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    note = db.query(Note).options(joinedload(Note.tags)).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "Note not found")

    raw = await file.read()
    text = raw.decode("utf-8")
    meta, body = parse_frontmatter(text)

    if "title" in meta:
        note.title = meta["title"]
        note.slug = slugify(meta["title"])
    note.content = body
    if "public" in meta:
        note.is_public = meta["public"]
    if "pinned" in meta:
        note.pinned = meta["pinned"]
    if "tags" in meta and isinstance(meta["tags"], list):
        tags = []
        for tname in meta["tags"]:
            tag = db.query(Tag).filter(Tag.name == tname.lower()).first()
            if not tag:
                tag = Tag(name=tname.lower())
                db.add(tag)
                db.flush()
            tags.append(tag)
        note.tags = tags

    db.commit()
    db.refresh(note)
    return {"id": note.id, "title": note.title, "updated": True}


@router.post("/import/markdown", response_model=ImportResult)
async def import_markdown(
    files: list[UploadFile] = File(...),
    folder_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    imported = 0
    skipped = 0
    errors = []

    for upload in files:
        try:
            raw = await upload.read()
            text = raw.decode("utf-8")

            if upload.filename and upload.filename.endswith(".zip"):
                zf = zipfile.ZipFile(io.BytesIO(raw))
                for name in zf.namelist():
                    if name.endswith(".md"):
                        md_text = zf.read(name).decode("utf-8")
                        meta, body = parse_frontmatter(md_text)
                        title = meta.get("title", name.rsplit("/", 1)[-1].replace(".md", "").replace("-", " ").title())
                        note = Note(
                            title=title,
                            slug=slugify(title),
                            content=body,
                            folder_id=folder_id,
                            is_public=meta.get("public", False),
                            pinned=meta.get("pinned", False),
                        )
                        if "tags" in meta and isinstance(meta["tags"], list):
                            tags = []
                            for tname in meta["tags"]:
                                tag = db.query(Tag).filter(Tag.name == tname.lower()).first()
                                if not tag:
                                    tag = Tag(name=tname.lower())
                                    db.add(tag)
                                    db.flush()
                                tags.append(tag)
                            note.tags = tags
                        db.add(note)
                        imported += 1
                continue

            meta, body = parse_frontmatter(text)
            title = meta.get("title")
            if not title and upload.filename:
                title = upload.filename.replace(".md", "").replace("-", " ").title()
            if not title:
                title = "Untitled"

            note = Note(
                title=title,
                slug=slugify(title),
                content=body,
                folder_id=folder_id,
                is_public=meta.get("public", False),
                pinned=meta.get("pinned", False),
            )
            if "tags" in meta and isinstance(meta["tags"], list):
                tags = []
                for tname in meta["tags"]:
                    tag = db.query(Tag).filter(Tag.name == tname.lower()).first()
                    if not tag:
                        tag = Tag(name=tname.lower())
                        db.add(tag)
                        db.flush()
                    tags.append(tag)
                note.tags = tags
            db.add(note)
            imported += 1
        except Exception as e:
            errors.append(f"{upload.filename}: {str(e)}")

    db.commit()
    return ImportResult(imported=imported, skipped=skipped, errors=errors)
