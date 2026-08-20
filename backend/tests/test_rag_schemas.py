from math import inf, nan
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.rag.constants import MAX_RETRIEVAL_QUERY_CHARACTERS
from backend.app.schemas.rag import (
    RAG_INSUFFICIENT_CONTEXT_ANSWER,
    RAGAnswerRequest,
    RAGAnswerResponse,
    RAGSourceResponse,
)


def make_source(source_number: int = 1) -> RAGSourceResponse:
    return RAGSourceResponse(
        source_number=source_number,
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="security-notes.md",
        chunk_index=2,
        similarity=0.91,
    )


def test_rag_answer_request_normalizes_query() -> None:
    request = RAGAnswerRequest(
        query=(
            "  What security control is recommended?\r\n"
            "Please explain.\r  "
        )
    )

    assert request.query == (
        "What security control is recommended?\n"
        "Please explain."
    )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n\t",
        "x" * (MAX_RETRIEVAL_QUERY_CHARACTERS + 1),
    ],
)
def test_rag_answer_request_rejects_invalid_query(query: str) -> None:
    with pytest.raises(ValidationError):
        RAGAnswerRequest(query=query)


def test_rag_answer_request_checks_raw_length_before_trimming() -> None:
    padded_query = (
        " "
        + ("x" * MAX_RETRIEVAL_QUERY_CHARACTERS)
        + " "
    )

    with pytest.raises(ValidationError):
        RAGAnswerRequest(query=padded_query)


def test_rag_answer_request_rejects_client_controlled_fields() -> None:
    with pytest.raises(ValidationError):
        RAGAnswerRequest.model_validate(
            {
                "query": "How should secrets be stored?",
                "top_k": 20,
                "owner_id": str(uuid4()),
                "model": "client-selected-model",
            }
        )


def test_rag_source_exposes_only_approved_metadata() -> None:
    private_owner_id = uuid4()
    private_embedding = [0.1, 0.2, 0.3]
    private_content = "Private retrieved chunk content"

    retrieval_context = SimpleNamespace(
        source_number=1,
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="security-notes.md",
        chunk_index=2,
        similarity=0.91,
        content=private_content,
        owner_id=private_owner_id,
        embedding=private_embedding,
    )

    source = RAGSourceResponse.model_validate(
        retrieval_context
    )
    source_data = source.model_dump()

    assert set(source_data) == {
        "source_number",
        "chunk_id",
        "document_id",
        "filename",
        "chunk_index",
        "similarity",
    }

    assert "content" not in source_data
    assert "owner_id" not in source_data
    assert "embedding" not in source_data
    assert private_content not in repr(source)
    assert str(private_owner_id) not in repr(source)
    assert str(private_embedding) not in repr(source)


@pytest.mark.parametrize(
    "similarity",
    [nan, inf, -inf],
)
def test_rag_source_rejects_nonfinite_similarity(similarity: float) -> None:
    with pytest.raises(ValidationError):
        RAGSourceResponse(
            source_number=1,
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="security-notes.md",
            chunk_index=0,
            similarity=similarity,
        )


def test_answered_response_contains_cited_sources() -> None:
    source = make_source()

    response = RAGAnswerResponse(
        status="answered",
        answer="Secrets should be stored outside source code [1].",
        sources=[source],
    )

    assert response.status == "answered"
    assert response.sources == [source]


def test_answered_response_requires_a_source() -> None:
    with pytest.raises(
        ValidationError,
        match="must contain at least one source",
    ):
        RAGAnswerResponse(
            status="answered",
            answer="Secrets should be stored securely [1].",
            sources=[],
        )


def test_insufficient_context_response_uses_canonical_fallback() -> None:
    response = RAGAnswerResponse(
        status="insufficient_context",
        answer=RAG_INSUFFICIENT_CONTEXT_ANSWER,
        sources=[],
    )

    assert response.sources == []


def test_insufficient_context_rejects_noncanonical_answer() -> None:
    with pytest.raises(
        ValidationError,
        match="canonical fallback answer",
    ):
        RAGAnswerResponse(
            status="insufficient_context",
            answer="I do not know.",
            sources=[],
        )


def test_insufficient_context_rejects_sources() -> None:
    with pytest.raises(
        ValidationError,
        match="must not contain sources",
    ):
        RAGAnswerResponse(
            status="insufficient_context",
            answer=RAG_INSUFFICIENT_CONTEXT_ANSWER,
            sources=[make_source()],
        )


def test_rag_answer_response_rejects_duplicate_source_numbers() -> None:
    with pytest.raises(
        ValidationError,
        match="source numbers must be unique",
    ):
        RAGAnswerResponse(
            status="answered",
            answer="Use both recommended controls [1].",
            sources=[
                make_source(source_number=1),
                make_source(source_number=1),
            ],
        )


def test_rag_source_rejects_extra_mapping_fields() -> None:
    with pytest.raises(ValidationError):
        RAGSourceResponse.model_validate(
            {
                "source_number": 1,
                "chunk_id": uuid4(),
                "document_id": uuid4(),
                "filename": "security-notes.md",
                "chunk_index": 0,
                "similarity": 0.91,
                "content": "Private chunk content",
            }
        )


def test_rag_answer_rejects_blank_answer() -> None:
    with pytest.raises(
        ValidationError,
        match="must not be blank",
    ):
        RAGAnswerResponse(
            status="answered",
            answer="   ",
            sources=[make_source()],
        )


def test_rag_answer_allows_gaps_between_cited_sources() -> None:
    response = RAGAnswerResponse(
        status="answered",
        answer="Use the first control [1] and third control [3].",
        sources=[
            make_source(source_number=1),
            make_source(source_number=3),
        ],
    )

    assert [
        source.source_number
        for source in response.sources
    ] == [1, 3]


def test_rag_answer_rejects_out_of_order_sources() -> None:
    with pytest.raises(
        ValidationError,
        match="must be ordered",
    ):
        RAGAnswerResponse(
            status="answered",
            answer="Use the third control [3] and first control [1].",
            sources=[
                make_source(source_number=3),
                make_source(source_number=1),
            ],
        )
