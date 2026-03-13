from datetime import datetime
from pydantic import BaseModel


class TagBase(BaseModel):
    name: str
    color: str = "#6366f1"

class TagCreate(TagBase):
    pass

class TagOut(TagBase):
    id: int
    model_config = {"from_attributes": True}


class FolderBase(BaseModel):
    name: str
    parent_id: int | None = None

class FolderCreate(FolderBase):
    pass

class FolderUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None

class FolderOut(FolderBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class FolderTree(FolderOut):
    children: list["FolderTree"] = []
    note_count: int = 0


class NoteBase(BaseModel):
    title: str
    content: str = ""
    folder_id: int | None = None
    is_public: bool = False
    pinned: bool = False

class NoteCreate(NoteBase):
    tags: list[str] = []

class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    folder_id: int | None = None
    is_public: bool | None = None
    pinned: bool | None = None
    tags: list[str] | None = None

class NoteOut(NoteBase):
    id: int
    slug: str
    tags: list[TagOut] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class NoteSummary(BaseModel):
    id: int
    title: str
    slug: str
    folder_id: int | None
    is_public: bool
    pinned: bool
    tags: list[TagOut] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    notes: list[NoteSummary]
    total: int


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = []


class SettingsOut(BaseModel):
    auth_enabled: bool
    api_key: str | None = None
    version: str


class SetupRequest(BaseModel):
    admin_password: str


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
