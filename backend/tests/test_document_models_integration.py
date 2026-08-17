from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError

from backend.app.db.database import SessionLocal
from backend.app.db.models import Document, DocumentChunk, User
from backend.app.rag.embeddings import EMBEDDING_DIMENSIONS


PASSWORD_HASH = "$argon2id$test-password-hash"
DOCUMENT_CONTENT = "Security controls protect retrieved document content."


def make_embedding(value: float = 0.1) -> list[float]:
    return [value] * EMBEDDING_DIMENSIONS


@pytest.fixture
def document_owner_id() -> Iterator[UUID]:
    username = f"document-owner-{uuid4().hex}"

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


def make_document(
    owner_id: UUID, 
    *, 
    content: str = DOCUMENT_CONTENT, 
    size_bytes: int | None = None
    ) -> Document:
    if size_bytes is None:
        size_bytes = len(content.encode("utf-8"))

    return Document(
        owner_id=owner_id,
        filename="security-notes.txt",
        content_type="text/plain",
        size_bytes=size_bytes,
        content=content,
    )


def create_document_with_chunks(owner_id: UUID) -> tuple[UUID, list[UUID]]:
    with SessionLocal() as database_session:
        document = make_document(owner_id)
        database_session.add(document)
        database_session.flush()

        chunks = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="Security controls protect retrieved",
                embedding=make_embedding(0.1),
            ),
            DocumentChunk(
                document_id=document.id,
                chunk_index=1,
                content="retrieved document content.",
                embedding=make_embedding(0.2),
            ),
        ]

        database_session.add_all(chunks)
        database_session.commit()

        return document.id, [chunk.id for chunk in chunks]


@pytest.mark.integration
def test_document_requires_existing_owner() -> None:
    document = make_document(uuid4())

    with SessionLocal() as database_session:
        database_session.add(document)

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_postgresql_rejects_nonpositive_document_size(document_owner_id: UUID) -> None:
    document = make_document(
        document_owner_id,
        size_bytes=0
    )

    with SessionLocal() as database_session:
        database_session.add(document)

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_postgresql_rejects_empty_document_content(document_owner_id: UUID) -> None:
    document = make_document(
        document_owner_id,
        content="",
        size_bytes=1,
    )

    with SessionLocal() as database_session:
        database_session.add(document)

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_postgresql_rejects_duplicate_chunk_indexes(document_owner_id: UUID) -> None:
    with SessionLocal() as database_session:
        document = make_document(document_owner_id)
        database_session.add(document)
        database_session.flush()

        database_session.add_all(
            [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="first chunk",
                    embedding=make_embedding(0.1),
                ),
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="duplicate chunk index",
                    embedding=make_embedding(0.2),
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_postgresql_rejects_negative_chunk_index(document_owner_id: UUID) -> None:
    with SessionLocal() as database_session:
        document = make_document(document_owner_id)
        database_session.add(document)
        database_session.flush()

        database_session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=-1,
                content="invalid chunk",
                embedding=make_embedding(),
            )
        )

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_postgresql_rejects_empty_chunk_content(document_owner_id: UUID) -> None:
    with SessionLocal() as database_session:
        document = make_document(document_owner_id)
        database_session.add(document)
        database_session.flush()

        database_session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="",
                embedding=make_embedding(),
            )
        )

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_deleting_document_cascades_to_chunks(document_owner_id: UUID) -> None:
    document_id, chunk_ids = create_document_with_chunks(document_owner_id)

    with SessionLocal() as database_session:
        document = database_session.get(Document, document_id)

        assert document is not None

        database_session.delete(document)
        database_session.commit()

    with SessionLocal() as database_session:
        assert database_session.get(Document, document_id) is None

        for chunk_id in chunk_ids:
            assert database_session.get(DocumentChunk, chunk_id) is None

        # make sure owner of the document is not deleted
        assert database_session.get(User, document_owner_id) is not None


@pytest.mark.integration
def test_chunk_embeddings_are_persisted(document_owner_id: UUID) -> None:
    _, chunk_ids = create_document_with_chunks(document_owner_id)

    with SessionLocal() as database_session:
        stored_chunks = [
            database_session.get(DocumentChunk, chunk_id)
            for chunk_id in chunk_ids
        ]

        assert all(chunk is not None for chunk in stored_chunks)

        embeddings = [
            chunk.embedding
            for chunk in stored_chunks
            if chunk is not None
        ]

        assert all(
            len(embedding) == EMBEDDING_DIMENSIONS
            for embedding in embeddings
        )
        assert [
            embedding[0]
            for embedding in embeddings
        ] == pytest.approx([0.1, 0.2])


@pytest.mark.integration
def test_postgresql_rejects_missing_chunk_embedding(document_owner_id: UUID) -> None:
    with SessionLocal() as database_session:
        document = make_document(document_owner_id)
        database_session.add(document)
        database_session.flush()

        database_session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="chunk without an embedding",
            )
        )

        with pytest.raises(IntegrityError):
            database_session.commit()

        database_session.rollback()


@pytest.mark.integration
def test_document_chunk_hnsw_cosine_index_exists() -> None:
    with SessionLocal() as database_session:
        index_definition = database_session.scalar(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'document_chunks'
                  AND indexname = 'ix_document_chunks_embedding_hnsw'
                """
            )
        )

    assert index_definition is not None
    assert "USING hnsw" in index_definition
    assert "embedding vector_cosine_ops" in index_definition


@pytest.mark.integration
def test_deleting_user_cascades_to_documents_and_chunks(document_owner_id: UUID) -> None:
    document_id, chunk_ids = create_document_with_chunks(document_owner_id)

    with SessionLocal() as database_session:
        user = database_session.get(User, document_owner_id)

        assert user is not None

        database_session.delete(user)
        database_session.commit()

    with SessionLocal() as database_session:
        assert database_session.get(User, document_owner_id) is None
        assert database_session.get(Document, document_id) is None

        for chunk_id in chunk_ids:
            assert database_session.get(DocumentChunk, chunk_id) is None