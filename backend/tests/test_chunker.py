import pytest

from backend.app.rag.chunker import chunk_text


def test_short_text_creates_one_chunk() -> None:
    chunks = chunk_text(
        "  security document  ",
        chunk_size=100,
        overlap=20
    )

    assert chunks == ["security document"]


def test_whitespace_only_text_creates_no_chunks() -> None:
    chunks = chunk_text(
        "  \n\t  ",
        chunk_size=100,
        overlap=20
    )

    assert chunks == []


def test_text_is_divided_into_overlapping_windows() -> None:
    chunks = chunk_text(
        "abcdefghij",
        chunk_size=4,
        overlap=1
    )

    assert chunks == ["abcd", "defg", "ghij"]
    assert chunks[0][-1:] == chunks[1][:1]
    assert chunks[1][-1:] == chunks[2][:1]


def test_chunks_can_reconstruct_normalized_text() -> None:
    original_text = "abcdefghij"
    overlap = 1

    chunks = chunk_text(
        original_text,
        chunk_size=4,
        overlap=overlap
    )

    reconstructed_text = chunks[0] + "".join(
        chunk[overlap:]
        for chunk in chunks[1:]
    )

    assert reconstructed_text == original_text


def test_zero_overlap_creates_nonoverlapping_windows() -> None:
    chunks = chunk_text(
        "abcdefghij",
        chunk_size=4,
        overlap=0
    )

    assert chunks == ["abcd", "efgh", "ij"]


def test_line_endings_are_normalized() -> None:
    chunks = chunk_text(
        "first\r\nsecond\rthird",
        chunk_size=100,
        overlap=20
    )

    assert chunks == ["first\nsecond\nthird"]


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_nonpositive_chunk_size_is_rejected(chunk_size: int) -> None:
    with pytest.raises(ValueError, match="chunk_size must be greater than zero"):
        chunk_text("document", chunk_size=chunk_size, overlap=0)


def test_negative_overlap_is_rejected() -> None:
    with pytest.raises(ValueError, match="overlap cannot be negative"):
        chunk_text("document", chunk_size=100, overlap=-1)


@pytest.mark.parametrize("overlap", [100, 101])
def test_overlap_must_be_smaller_than_chunk_size(overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap must be smaller than chunk_size"):
        chunk_text("document", chunk_size=100, overlap=overlap)