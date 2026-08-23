from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from backend.app.rag.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingGenerationError,
    EmbeddingProvider
)
from backend.app.rag.constants import (
    MAX_RETRIEVAL_QUERY_CHARACTERS,
    MAX_RETRIEVAL_TOP_K,
)
from backend.app.rag.retriever import (
    RetrievedChunk,
    retrieve_chunks_for_owner
)


def make_embedding(value: float = 1.0) -> list[float]:
    return [value] * EMBEDDING_DIMENSIONS


def test_retriever_embeds_query_and_builds_owner_scoped_query() -> None:
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)

    owner_id = uuid4()
    chunk_id = uuid4()
    document_id = uuid4()
    query_embedding = make_embedding()

    embedding_provider.embed_texts.return_value = [
        query_embedding
    ]

    database_result = Mock()
    database_result.all.return_value = [
        SimpleNamespace(
            chunk_id=chunk_id,
            document_id=document_id,
            filename="security-notes.md",
            chunk_index=2,
            content="Store API keys in environment variables.",
            similarity=0.91,
        )
    ]

    database_session.execute.side_effect = [Mock(), database_result]

    results = retrieve_chunks_for_owner(
        database_session,
        owner_id,
        "  How should API keys be stored?  ",
        embedding_provider=embedding_provider,
        top_k=2,
    )

    embedding_provider.embed_texts.assert_called_once_with(
        ["How should API keys be stored?"]
    )

    assert results == [
        RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            filename="security-notes.md",
            chunk_index=2,
            content="Store API keys in environment variables.",
            similarity=0.91,
        )
    ]

    assert database_session.execute.call_count == 2

    setting_statement = (database_session.execute.call_args_list[0].args[0])

    assert str(setting_statement) == ("SET LOCAL hnsw.iterative_scan = 'strict_order'")

    retrieval_statement = (database_session.execute.call_args_list[1].args[0])
    compiled_statement = retrieval_statement.compile(dialect=postgresql.dialect())

    compiled_sql = " ".join(str(compiled_statement).split())
    compiled_values = list(compiled_statement.params.values())

    assert "JOIN documents" in compiled_sql
    assert "documents.owner_id =" in compiled_sql
    assert "ORDER BY document_chunks.embedding <=>" in compiled_sql
    assert "LIMIT" in compiled_sql
    assert owner_id in compiled_values
    assert 2 in compiled_values
    assert "AS similarity" in compiled_sql

    database_session.commit.assert_not_called()


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n\t",
        "x" * (MAX_RETRIEVAL_QUERY_CHARACTERS + 1),
    ],
)
def test_retriever_rejects_invalid_query_before_external_calls(query: str) -> None:
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)

    with pytest.raises(ValueError):
        retrieve_chunks_for_owner(
            database_session,
            uuid4(),
            query,
            embedding_provider=embedding_provider,
            top_k=5,
        )

    embedding_provider.embed_texts.assert_not_called()
    database_session.execute.assert_not_called()


@pytest.mark.parametrize(
    "top_k",
    [-1, 0, MAX_RETRIEVAL_TOP_K + 1],
)
def test_retriever_rejects_invalid_top_k_before_external_calls(top_k: int) -> None:
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)

    with pytest.raises(
        ValueError, 
        match=f"Retrieval top_k must be between 1 and {MAX_RETRIEVAL_TOP_K}"):
        retrieve_chunks_for_owner(
            database_session,
            uuid4(),
            "security controls",
            embedding_provider=embedding_provider,
            top_k=top_k,
        )

    embedding_provider.embed_texts.assert_not_called()
    database_session.execute.assert_not_called()


@pytest.mark.parametrize(
    "returned_embeddings",
    [
        [],
        [make_embedding(), make_embedding()],
    ],
)
def test_retriever_rejects_unexpected_embedding_count(
    returned_embeddings: list[list[float]],
) -> None:
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)
    embedding_provider.embed_texts.return_value = (
        returned_embeddings
    )

    with pytest.raises(
        EmbeddingGenerationError,
        match="unexpected result count",
    ):
        retrieve_chunks_for_owner(
            database_session,
            uuid4(),
            "security controls",
            embedding_provider=embedding_provider,
            top_k=5,
        )

    database_session.execute.assert_not_called()


def test_retriever_propagates_embedding_failure_without_database_query() -> None:
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)
    provider_error = EmbeddingGenerationError(
        "Internal provider failure"
    )

    embedding_provider.embed_texts.side_effect = provider_error

    with pytest.raises(
        EmbeddingGenerationError,
        match="Internal provider failure",
    ):
        retrieve_chunks_for_owner(
            database_session,
            uuid4(),
            "security controls",
            embedding_provider=embedding_provider,
            top_k=5,
        )

    database_session.execute.assert_not_called()


def test_retriever_returns_empty_list_for_empty_owned_corpus() -> None:
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)
    embedding_provider.embed_texts.return_value = [
        make_embedding()
    ]

    database_result = Mock()
    database_result.all.return_value = []

    database_session.execute.side_effect = [Mock(), database_result]

    results = retrieve_chunks_for_owner(
        database_session,
        uuid4(),
        "security controls",
        embedding_provider=embedding_provider,
        top_k=5,
    )

    assert results == [] # there are no documents uploaded by owner
    database_session.commit.assert_not_called()
