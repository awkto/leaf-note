import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Folder, Note
from app.schemas import FolderCreate, FolderUpdate, FolderOut, FolderTree
from app.auth import require_auth

router = APIRouter(prefix="/api/folders", tags=["folders"])


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_tree(folders: list[Folder], parent_id: int | None = None) -> list[FolderTree]:
    result = []
    for f in folders:
        if f.parent_id == parent_id:
            children = build_tree(folders, f.id)
            result.append(FolderTree(
                id=f.id, name=f.name, slug=f.slug,
                parent_id=f.parent_id,
                default_view=f.default_view,
                created_at=f.created_at, updated_at=f.updated_at,
                children=children,
                note_count=len(f.notes),
            ))
    return result


def resolve_folder_path(db: Session, path: str) -> Folder | None:
    """Resolve a slash-separated folder path like 'infrastructure/docker' to a Folder."""
    parts = [p.strip() for p in path.strip("/").split("/") if p.strip()]
    parent_id = None
    folder = None
    for part in parts:
        slug = slugify(part)
        folder = db.query(Folder).filter(
            Folder.slug == slug, Folder.parent_id == parent_id
        ).first()
        if not folder:
            # Try matching by name (case-insensitive)
            folder = db.query(Folder).filter(
                Folder.name.ilike(part), Folder.parent_id == parent_id
            ).first()
        if not folder:
            return None
        parent_id = folder.id
    return folder


def ensure_folder_path(db: Session, path: str) -> Folder:
    """Resolve or create the full folder path, returning the deepest folder."""
    parts = [p.strip() for p in path.strip("/").split("/") if p.strip()]
    parent_id = None
    folder = None
    for part in parts:
        slug = slugify(part)
        folder = db.query(Folder).filter(
            Folder.slug == slug, Folder.parent_id == parent_id
        ).first()
        if not folder:
            folder = db.query(Folder).filter(
                Folder.name.ilike(part), Folder.parent_id == parent_id
            ).first()
        if not folder:
            folder = Folder(name=part, slug=slug, parent_id=parent_id)
            db.add(folder)
            db.flush()
        parent_id = folder.id
    return folder


def build_folder_breadcrumb(db: Session, folder_id: int | None) -> str:
    """Build a slash-separated path from folder_id up to root."""
    if not folder_id:
        return ""
    parts = []
    fid = folder_id
    while fid:
        f = db.get(Folder, fid)
        if not f:
            break
        parts.insert(0, f.name)
        fid = f.parent_id
    return "/".join(parts)


@router.get("/by-path/{path:path}", response_model=FolderOut)
def get_folder_by_path(path: str, db: Session = Depends(get_db), _=Depends(require_auth)):
    """Look up a folder by path like /api/folders/by-path/infrastructure/docker"""
    folder = resolve_folder_path(db, path)
    if not folder:
        raise HTTPException(404, f"Folder not found: {path}")
    return folder


@router.get("", response_model=list[FolderOut])
def list_folders(parent_id: int | None = None, db: Session = Depends(get_db), _=Depends(require_auth)):
    q = db.query(Folder)
    if parent_id is not None:
        q = q.filter(Folder.parent_id == parent_id)
    return q.order_by(Folder.name).all()


@router.get("/tree", response_model=list[FolderTree])
def folder_tree(db: Session = Depends(get_db), _=Depends(require_auth)):
    folders = db.query(Folder).all()
    return build_tree(folders)


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(body: FolderCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    if body.parent_id:
        parent = db.get(Folder, body.parent_id)
        if not parent:
            raise HTTPException(404, "Parent folder not found")
    folder = Folder(name=body.name, slug=slugify(body.name), parent_id=body.parent_id, default_view=body.default_view)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.get("/{folder_id}", response_model=FolderOut)
def get_folder(folder_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(404, "Folder not found")
    return folder


@router.put("/{folder_id}", response_model=FolderOut)
def update_folder(folder_id: int, body: FolderUpdate, db: Session = Depends(get_db), _=Depends(require_auth)):
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(404, "Folder not found")
    if body.name is not None:
        folder.name = body.name
        folder.slug = slugify(body.name)
    if body.parent_id is not None:
        folder.parent_id = body.parent_id
    if body.default_view is not None:
        folder.default_view = body.default_view if body.default_view != "" else None
    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(404, "Folder not found")
    db.delete(folder)
    db.commit()
