from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend.app.rag.embeddings import EmbeddingProvider
from backend.app.rag.generator import (
    AnswerContext,
    AnswerProvider,
    AnswerResponseInvalidError,
    GeneratedAnswer,
)
from backend.app.rag.retriever import RetrievedChunk
from backend.app.services import rag as rag_service


QUERY = "How should API keys be stored?"
CONTENT = "Store API keys in environment variables."


@pytest.fixture
def answer_boundary(monkeypatch):
    database_session = Mock(spec=Session)
    embedding_provider = Mock(spec=EmbeddingProvider)
    answer_provider = Mock(spec=AnswerProvider)

    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="security-notes.md",
        chunk_index=0,
        content=CONTENT,
        similarity=0.9,
    )

    monkeypatch.setattr(
        rag_service,
        "retrieve_chunks_for_owner",
        Mock(return_value=[chunk]),
    )

    def run_answer(generated_answer: GeneratedAnswer):
        answer_provider.generate_answer.return_value = generated_answer

        return rag_service.answer_query_for_owner(
            database_session,
            uuid4(),
            QUERY,
            embedding_provider=embedding_provider,
            answer_provider=answer_provider,
            top_k=5,
            max_context_characters=1_000,
            prompt_injection_block_threshold=50,
        )

    return run_answer, answer_provider, chunk


@pytest.mark.parametrize(
    ("answer", "citations"),
    [
        pytest.param(
            "Store keys securely [2].",
            [2],
            id="unavailable-source",
        ),
        pytest.param(
            "Store keys securely [2].",
            [1],
            id="inline-declared-mismatch",
        ),
        pytest.param(
            "Store keys securely.",
            [1],
            id="missing-inline-citation",
        ),
        pytest.param(
            "Store keys securely [0].",
            [1],
            id="zero-citation",
        ),
        pytest.param(
            "Store keys securely [01].",
            [1],
            id="leading-zero-citation",
        ),
    ],
)
def test_service_rejects_invalid_provider_citations(
    answer_boundary,
    answer: str,
    citations: list[int]
) -> None:
    run_answer, answer_provider, _ = answer_boundary

    generated_answer = GeneratedAnswer(
        status="answered",
        answer=answer,
        cited_source_numbers=citations,
    )

    with pytest.raises(AnswerResponseInvalidError):
        run_answer(generated_answer)

    answer_provider.generate_answer.assert_called_once_with(
        QUERY,
        [AnswerContext(source_number=1, content=CONTENT)],
    )


def test_service_accepts_valid_provider_citations(answer_boundary) -> None:
    run_answer, answer_provider, chunk = answer_boundary

    response = run_answer(
        GeneratedAnswer(
            status="answered",
            answer="Store API keys in environment variables [1].",
            cited_source_numbers=[1],
        )
    )

    assert response.status == "answered"
    assert response.answer == (
        "Store API keys in environment variables [1]."
    )
    assert len(response.sources) == 1

    source = response.sources[0]
    assert source.source_number == 1
    assert source.chunk_id == chunk.chunk_id
    assert source.document_id == chunk.document_id
    assert source.filename == chunk.filename
    assert source.chunk_index == chunk.chunk_index
    assert source.similarity == chunk.similarity

    answer_provider.generate_answer.assert_called_once_with(
        QUERY,
        [AnswerContext(source_number=1, content=CONTENT)],
    )