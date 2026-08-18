import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, func, true)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import VECTOR

from backend.app.db.database import Base
from backend.app.rag.embeddings import EMBEDDING_DIMENSIONS


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'admin')",
            name="ck_users_role"
        ),
    ) # tells the db only two role values are valid

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.USER.value,
        server_default=UserRole.USER.value
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "size_bytes > 0",
            name="ck_documents_size_bytes_positive"
        ),
        CheckConstraint(
            "char_length(content) > 0",
            name="ck_documents_content_not_empty",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", 
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_id_chunk_index"
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_document_chunks_chunk_index_nonnegative"
        ),
        CheckConstraint(
            "char_length(content) > 0",
            name="ck_document_chunks_content_not_empty"
        ),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "documents.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(EMBEDDING_DIMENSIONS),
        nullable=False
    )