from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from backend.app.db.database import SessionLocal
from backend.app.db.models import Document, DocumentChunk, User
from backend.app.rag.embeddings import EMBEDDING_DIMENSIONS, EmbeddingProvider
from backend.app.rag.retriever import retrieve_chunks_for_owner


PASSWORD_HASH = "$argon2id$retrieval-integration-test"


def make_embedding(first_value: float, second_value: float) -> list[float]:
    return [
        first_value,
        second_value,
        *([0.0] * (EMBEDDING_DIMENSIONS - 2)),
    ]


@dataclass(frozen=True, slots=True)
class RetrievalCorpus:
    owner_id: UUID
    foreign_owner_id: UUID
    empty_owner_id: UUID
    owned_document_id: UUID
    foreign_document_id: UUID
    owned_chunk_ids: tuple[UUID, UUID, UUID]


@pytest.fixture
def retrieval_corpus() -> Iterator[RetrievalCorpus]:
    suffix = uuid4().hex

    with SessionLocal() as database_session:
        owner = User(
            username=f"retrieval-owner-{suffix}",
            password_hash=PASSWORD_HASH,
        )
        foreign_owner = User(
            username=f"retrieval-foreign-{suffix}",
            password_hash=PASSWORD_HASH,
        )
        empty_owner = User(
            username=f"retrieval-empty-{suffix}",
            password_hash=PASSWORD_HASH,
        )

        database_session.add_all(
            [owner, foreign_owner, empty_owner]
        )
        database_session.flush()

        owned_document = Document(
            owner_id=owner.id,
            filename="owned-security-notes.md",
            content_type="text/markdown",
            size_bytes=30,
            content="Owned security guidance text.",
        )
        foreign_document = Document(
            owner_id=foreign_owner.id,
            filename="foreign-security-notes.md",
            content_type="text/markdown",
            size_bytes=32,
            content="Foreign security guidance text.",
        )

        database_session.add_all(
            [owned_document, foreign_document]
        )
        database_session.flush()

        owned_chunks = [
            DocumentChunk(
                document_id=owned_document.id,
                chunk_index=0,
                content="Owned exact match",
                embedding=make_embedding(1.0, 0.0),
            ),
            DocumentChunk(
                document_id=owned_document.id,
                chunk_index=1,
                content="Owned partial match",
                embedding=make_embedding(0.8, 0.6),
            ),
            DocumentChunk(
                document_id=owned_document.id,
                chunk_index=2,
                content="Owned alternate match",
                embedding=make_embedding(0.0, 1.0),
            ),
        ]

        # These foreign chunks are deliberately perfect matches.
        # They must never consume the requesting owner's top_k.
        foreign_chunks = [
            DocumentChunk(
                document_id=foreign_document.id,
                chunk_index=index,
                content=f"Foreign perfect match {index}",
                embedding=make_embedding(1.0, 0.0),
            )
            for index in range(5)
        ]

        database_session.add_all(
            [*owned_chunks, *foreign_chunks]
        )
        database_session.commit()

        corpus = RetrievalCorpus(
            owner_id=owner.id,
            foreign_owner_id=foreign_owner.id,
            empty_owner_id=empty_owner.id,
            owned_document_id=owned_document.id,
            foreign_document_id=foreign_document.id,
            owned_chunk_ids=(
                owned_chunks[0].id,
                owned_chunks[1].id,
                owned_chunks[2].id,
            ),
        )

    try:
        yield corpus
    finally:
        with SessionLocal() as database_session:
            database_session.execute(
                delete(User).where(
                    User.id.in_(
                        [
                            corpus.owner_id,
                            corpus.foreign_owner_id,
                            corpus.empty_owner_id,
                        ]
                    )
                )
            )
            database_session.commit()


@pytest.mark.integration
def test_retrieval_filters_by_owner_before_applying_top_k(retrieval_corpus: RetrievalCorpus) -> None:
    embedding_provider = Mock(spec=EmbeddingProvider)
    embedding_provider.embed_texts.return_value = [
        make_embedding(1.0, 0.0)
    ]

    with SessionLocal() as database_session:
        results = retrieve_chunks_for_owner(
            database_session,
            retrieval_corpus.owner_id,
            "  API key storage  ",
            embedding_provider=embedding_provider,
            top_k=2,
        )

    embedding_provider.embed_texts.assert_called_once_with(
        ["API key storage"]
    )

    assert len(results) == 2

    assert [result.chunk_id for result in results] == [
        retrieval_corpus.owned_chunk_ids[0],
        retrieval_corpus.owned_chunk_ids[1],
    ]
    assert all(
        result.document_id
        == retrieval_corpus.owned_document_id
        for result in results
    )
    assert all(
        result.document_id
        != retrieval_corpus.foreign_document_id
        for result in results
    )

    assert [result.content for result in results] == [
        "Owned exact match",
        "Owned partial match",
    ]
    assert [
        result.similarity for result in results
    ] == pytest.approx([1.0, 0.8])


@pytest.mark.integration
def test_retrieval_orders_owned_chunks_by_cosine_similarity(retrieval_corpus: RetrievalCorpus) -> None:
    embedding_provider = Mock(spec=EmbeddingProvider)
    embedding_provider.embed_texts.return_value = [
        make_embedding(0.0, 1.0)
    ]

    with SessionLocal() as database_session:
        results = retrieve_chunks_for_owner(
            database_session,
            retrieval_corpus.owner_id,
            "alternate security topic",
            embedding_provider=embedding_provider,
            top_k=3,
        )

    assert [result.chunk_id for result in results] == [
        retrieval_corpus.owned_chunk_ids[2],
        retrieval_corpus.owned_chunk_ids[1],
        retrieval_corpus.owned_chunk_ids[0],
    ]
    assert [
        result.similarity for result in results
    ] == pytest.approx([1.0, 0.6, 0.0])


@pytest.mark.integration
def test_retrieval_returns_empty_results_for_owner_without_documents(retrieval_corpus: RetrievalCorpus) -> None:
    embedding_provider = Mock(spec=EmbeddingProvider)
    embedding_provider.embed_texts.return_value = [
        make_embedding(1.0, 0.0)
    ]

    with SessionLocal() as database_session:
        results = retrieve_chunks_for_owner(
            database_session,
            retrieval_corpus.empty_owner_id,
            "security guidance",
            embedding_provider=embedding_provider,
            top_k=5,
        )

    assert results == []

    embedding_provider.embed_texts.assert_called_once_with(
        ["security guidance"]
    )