from math import inf, nan
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.rag.constants import (
    MAX_RETRIEVAL_QUERY_CHARACTERS,
    MAX_RETRIEVAL_TOP_K,
)
from backend.app.schemas.retrieval import (
    RetrievedChunkResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)


def test_semantic_search_normalizes_query_and_defaults_top_k() -> None:
    request = SemanticSearchRequest(
        query="  How should API keys be stored?  "
    )

    assert request.query == "How should API keys be stored?"
    assert request.top_k == 5


def test_semantic_search_accepts_maximum_top_k() -> None:
    request = SemanticSearchRequest(
        query="security controls",
        top_k=MAX_RETRIEVAL_TOP_K
    )

    assert request.top_k == 20


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "\n\t",
        "x" * (MAX_RETRIEVAL_QUERY_CHARACTERS + 1)
    ],
)
def test_semantic_search_rejects_invalid_query(query: str) -> None:
    with pytest.raises(ValidationError):
        SemanticSearchRequest(query=query)


@pytest.mark.parametrize("top_k", [-1, 0, MAX_RETRIEVAL_TOP_K + 1])
def test_semantic_search_rejects_invalid_top_k(top_k: int) -> None:
    with pytest.raises(ValidationError):
        SemanticSearchRequest(
            query="security controls",
            top_k=top_k
        )


def test_semantic_search_rejects_client_supplied_owner() -> None:
    with pytest.raises(ValidationError):
        SemanticSearchRequest.model_validate(
            {
                "query": "security controls",
                "top_k": 5,
                "owner_id": str(uuid4())
            }
        )


def test_retrieval_response_exposes_only_approved_chunk_fields() -> None:
    private_owner_id = uuid4()
    private_embedding = [0.1, 0.2, 0.3]

    retrieval_result = SimpleNamespace(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="security-notes.md",
        chunk_index=2,
        content="Store API keys in environment variables.",
        similarity=0.91,
        owner_id=private_owner_id,
        embedding=private_embedding,
    )

    chunk_response = RetrievedChunkResponse.model_validate(
        retrieval_result
    )
    response = SemanticSearchResponse(
        results=[chunk_response]
    )

    response_data = response.model_dump()
    result_data = response_data["results"][0]

    assert set(response_data) == {"results"}
    assert set(result_data) == {
        "chunk_id",
        "document_id",
        "filename",
        "chunk_index",
        "content",
        "similarity",
    }

    assert "owner_id" not in result_data
    assert "embedding" not in result_data
    assert str(private_owner_id) not in repr(response)
    assert str(private_embedding) not in repr(response)


@pytest.mark.parametrize("similarity", [nan, inf, -inf])
def test_retrieval_response_rejects_nonfinite_similarity(similarity: float) -> None:
    with pytest.raises(ValidationError):
        RetrievedChunkResponse(
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="security-notes.md",
            chunk_index=0,
            content="Security guidance",
            similarity=similarity,
        )
