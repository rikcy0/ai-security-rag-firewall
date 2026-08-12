from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.app.db.database import SessionLocal
from backend.app.db.models import Document, DocumentChunk, User
from backend.app.services import documents as document_service


PASSWORD_HASH = "$argon2id$test-password-hash"


@pytest.fixture
def service_owner_id() -> Iterator[UUID]:
    username = f"service-owner-{uuid4().hex}"

    with SessionLocal() as database_session:
        user = User(
            username=username,
            password_hash=PASSWORD_HASH,
        )
        database_session.add(user)
        database_session.commit()

        owner_id = user.id

    yield owner_id

    with SessionLocal() as database_session:
        database_session.execute(
            delete(User).where(User.id == owner_id)
        )
        database_session.commit()


@pytest.mark.integration
def test_service_persists_document_and_ordered_chunks(service_owner_id: UUID) -> None:
    with SessionLocal() as database_session:
        document = document_service.create_document(
            database_session,
            service_owner_id,
            r"C:\fakepath\security-notes.txt",
            b"abcdefghij",
            max_upload_size_bytes=100,
            chunk_size=4,
            chunk_overlap=1,
        )
        document_id = document.id

    with SessionLocal() as database_session:
        stored_document = database_session.get(
            Document,
            document_id,
        )

        assert stored_document is not None
        assert stored_document.owner_id == service_owner_id
        assert stored_document.filename == "security-notes.txt"
        assert stored_document.content_type == "text/plain"
        assert stored_document.size_bytes == 10
        assert stored_document.content == "abcdefghij"
        assert stored_document.created_at is not None

        statement = (
            select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                    .order_by(DocumentChunk.chunk_index)
        )
        stored_chunks = list(database_session.scalars(statement).all())

        assert [chunk.chunk_index for chunk in stored_chunks] == [0, 1, 2]
        assert [chunk.content for chunk in stored_chunks] == ["abcd", "defg", "ghij"]
        assert all(chunk.document_id == document_id for chunk in stored_chunks)


@pytest.mark.integration
def test_service_rolls_back_document_when_chunk_insert_fails(service_owner_id: UUID, monkeypatch) -> None:
    def invalid_chunk_text(text: str, chunk_size: int, overlap: int,) -> list[str]:
        return ["valid chunk", ""]

    monkeypatch.setattr(
        document_service,
        "chunk_text",
        invalid_chunk_text,
    )

    with SessionLocal() as database_session:
        with pytest.raises(IntegrityError):
            document_service.create_document(
                database_session,
                service_owner_id,
                "rollback-test.txt",
                b"valid document content",
                max_upload_size_bytes=100,
                chunk_size=100,
                chunk_overlap=20,
            )

    with SessionLocal() as database_session:
        stored_document = database_session.scalar(
            select(Document)
                .where(Document.owner_id == service_owner_id)
        )

        stored_chunks = list(
            database_session.scalars(
                select(DocumentChunk)
                    .join(Document, DocumentChunk.document_id == Document.id)
                        .where(Document.owner_id == service_owner_id)
            ).all()
        )

        # PostgreSQL rejects an empty chunk in atomic transaction
        assert stored_document is None
        assert stored_chunks == []