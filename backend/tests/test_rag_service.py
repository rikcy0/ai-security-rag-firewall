from uuid import uuid4

import pytest

from backend.app.rag.retriever import RetrievedChunk
from backend.app.services.rag import prepare_answer_sources


def make_retrieved_chunk(
    content: str,
    *,
    chunk_index: int = 0,
    filename: str = "security-notes.md",
    similarity: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename=filename,
        chunk_index=chunk_index,
        content=content,
        similarity=similarity,
    )


def test_prepare_answer_sources_preserves_retrieval_order() -> None:
    first_chunk = make_retrieved_chunk(
        "First security control",
        chunk_index=0,
        similarity=0.95,
    )
    second_chunk = make_retrieved_chunk(
        "Second security control",
        chunk_index=1,
        similarity=0.85,
    )

    prepared = prepare_answer_sources(
        [first_chunk, second_chunk],
        max_context_characters=100,
    )

    assert [
        source.answer_context.source_number
        for source in prepared
    ] == [1, 2]

    assert [
        source.answer_context.content
        for source in prepared
    ] == [
        "First security control",
        "Second security control",
    ]

    assert prepared[0].retrieved_chunk is first_chunk
    assert prepared[1].retrieved_chunk is second_chunk


def test_prepare_answer_sources_enforces_total_context_budget() -> None:
    first_chunk = make_retrieved_chunk(
        "a" * 6,
        chunk_index=0,
    )
    second_chunk = make_retrieved_chunk(
        "b" * 6,
        chunk_index=1,
    )

    prepared = prepare_answer_sources(
        [first_chunk, second_chunk],
        max_context_characters=10,
    )

    assert len(prepared) == 1
    assert prepared[0].retrieved_chunk is first_chunk


def test_prepare_answer_sources_does_not_split_chunks() -> None:
    oversized_chunk = make_retrieved_chunk(
        "a" * 11,
        chunk_index=0,
    )

    prepared = prepare_answer_sources(
        [oversized_chunk],
        max_context_characters=10,
    )

    assert prepared == []


def test_prepare_answer_sources_can_skip_oversized_chunk() -> None:
    smaller_content = "Supported evidence"

    oversized_chunk = make_retrieved_chunk(
        "a" * (len(smaller_content) + 1),
        chunk_index=0,
    )
    smaller_chunk = make_retrieved_chunk(
        smaller_content,
        chunk_index=1,
    )

    prepared = prepare_answer_sources(
        [oversized_chunk, smaller_chunk],
        max_context_characters=len(smaller_content),
    )

    assert len(prepared) == 1
    assert prepared[0].retrieved_chunk is smaller_chunk
    assert prepared[0].answer_context.source_number == 1


def test_prepare_answer_sources_accepts_exact_budget() -> None:
    chunk = make_retrieved_chunk("exact")

    prepared = prepare_answer_sources(
        [chunk],
        max_context_characters=len("exact"),
    )

    assert len(prepared) == 1
    assert prepared[0].answer_context.content == "exact"


def test_prepare_answer_sources_returns_empty_list_for_no_chunks() -> None:
    assert prepare_answer_sources(
        [],
        max_context_characters=100,
    ) == []


def test_prepare_answer_sources_skips_blank_chunk_content() -> None:
    blank_chunk = make_retrieved_chunk("   ")
    valid_chunk = make_retrieved_chunk(
        "Valid evidence",
        chunk_index=1,
    )

    prepared = prepare_answer_sources(
        [blank_chunk, valid_chunk],
        max_context_characters=100,
    )

    assert len(prepared) == 1
    assert prepared[0].retrieved_chunk is valid_chunk
    assert prepared[0].answer_context.source_number == 1


@pytest.mark.parametrize(
    "max_context_characters",
    [0, -1],
)
def test_prepare_answer_sources_rejects_invalid_budget(
    max_context_characters: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="must be greater than zero",
    ):
        prepare_answer_sources(
            [],
            max_context_characters=max_context_characters,
        )