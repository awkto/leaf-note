from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.database import Base

note_tags = Table(
    "note_tags",
    Base.metadata,
    Column("note_id", Integer, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True)
    default_view = Column(String(10), nullable=True)  # "source", "preview", or null (inherit)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    parent = relationship("Folder", remote_side="Folder.id", back_populates="children")
    children = relationship("Folder", back_populates="parent", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="folder", cascade="all, delete-orphan")


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    slug = Column(String(500), nullable=False)
    content = Column(Text, default="")
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False)
    pinned = Column(Boolean, default=False)
    default_view = Column(String(10), nullable=True)  # "source", "preview", or null (inherit)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    folder = relationship("Folder", back_populates="notes")
    tags = relationship("Tag", secondary=note_tags, back_populates="notes")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default="#6366f1")

    notes = relationship("Note", secondary=note_tags, back_populates="tags")
