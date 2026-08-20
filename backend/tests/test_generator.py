import pytest
from pydantic import ValidationError

from backend.app.rag.generator import (
    AnswerContext,
    AnswerResponseInvalidError,
    GeneratedAnswer,
    validate_generated_answer
)


def make_context(source_number: int = 1) -> AnswerContext:
    return AnswerContext(
        source_number=source_number,
        content="Store secrets outside the source code.",
    )


def test_answer_context_accepts_minimal_provider_data() -> None:
    context = make_context()

    assert context.source_number == 1
    assert context.content == ("Store secrets outside the source code.")


@pytest.mark.parametrize("source_number", [0, 21])
def test_answer_context_rejects_invalid_source_number(
    source_number: int,
) -> None:
    with pytest.raises(ValueError):
        AnswerContext(
            source_number=source_number,
            content="Security guidance",
        )


def test_answer_context_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="content must not be empty"):
        AnswerContext(
            source_number=1,
            content="   ",
        )


def test_generated_answer_accepts_grounded_answer() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Store secrets outside source code [1].",
        cited_source_numbers=[1],
    )

    assert generated.status == "answered"
    assert generated.cited_source_numbers == [1]


def test_generated_answer_strips_answer_whitespace() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="  Use environment variables [1].  ",
        cited_source_numbers=[1],
    )

    assert generated.answer == "Use environment variables [1]."


def test_generated_answer_accepts_insufficient_context() -> None:
    generated = GeneratedAnswer(
        status="insufficient_context",
        answer="",
        cited_source_numbers=[],
    )

    assert generated.answer == ""
    assert generated.cited_source_numbers == []


def test_answered_result_requires_answer_text() -> None:
    with pytest.raises(ValidationError, match="must contain an answer"):
        GeneratedAnswer(
            status="answered",
            answer="   ",
            cited_source_numbers=[1],
        )


def test_answered_result_requires_citations() -> None:
    with pytest.raises(ValidationError, match="must contain citations"):
        GeneratedAnswer(
            status="answered",
            answer="Use environment variables.",
            cited_source_numbers=[],
        )


def test_insufficient_context_requires_empty_answer() -> None:
    with pytest.raises(ValidationError, match="must have an empty answer"):
        GeneratedAnswer(
            status="insufficient_context",
            answer="I invented an answer.",
            cited_source_numbers=[],
        )


def test_insufficient_context_rejects_citations() -> None:
    with pytest.raises(ValidationError, match="must not contain citations"):
        GeneratedAnswer(
            status="insufficient_context",
            answer="",
            cited_source_numbers=[1],
        )


def test_generated_answer_rejects_duplicate_citations() -> None:
    with pytest.raises(ValidationError, match="citation numbers must be unique"):
        GeneratedAnswer(
            status="answered",
            answer="Use the recommended control [1].",
            cited_source_numbers=[1, 1],
        )


def test_validation_accepts_matching_inline_citations() -> None:
    contexts = [
        make_context(1),
        make_context(2),
    ]
    generated = GeneratedAnswer(
        status="answered",
        answer="Use the first control [1] and the second [2].",
        cited_source_numbers=[1, 2],
    )

    result = validate_generated_answer(
        generated,
        contexts,
    )

    assert result is generated


def test_validation_allows_repeated_inline_citation() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Use the control [1]. It is recommended again [1].",
        cited_source_numbers=[1],
    )

    result = validate_generated_answer(
        generated,
        [make_context(1)],
    )

    assert result is generated


def test_validation_allows_gaps_between_context_numbers() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Use the first [1] and third controls [3].",
        cited_source_numbers=[1, 3],
    )

    result = validate_generated_answer(
        generated,
        [
            make_context(1),
            make_context(3),
        ],
    )

    assert result is generated


def test_validation_rejects_unavailable_source() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Use the second control [2].",
        cited_source_numbers=[2],
    )

    with pytest.raises(AnswerResponseInvalidError, match="unavailable source"):
        validate_generated_answer(
            generated,
            [make_context(1)],
        )


def test_validation_rejects_missing_inline_citation() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Use environment variables.",
        cited_source_numbers=[1],
    )

    with pytest.raises(AnswerResponseInvalidError, match="do not match"):
        validate_generated_answer(
            generated,
            [make_context(1)],
        )


def test_validation_rejects_undeclared_inline_citation() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Use environment variables [1] [2].",
        cited_source_numbers=[1],
    )

    with pytest.raises(AnswerResponseInvalidError, match="do not match"):
        validate_generated_answer(
            generated,
            [
                make_context(1),
                make_context(2),
            ],
        )


def test_validation_rejects_duplicate_context_numbers() -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer="Use environment variables [1].",
        cited_source_numbers=[1],
    )

    with pytest.raises(ValueError, match="source numbers must be unique"):
        validate_generated_answer(
            generated,
            [
                make_context(1),
                make_context(1),
            ],
        )


def test_validation_requires_contexts() -> None:
    generated = GeneratedAnswer(
        status="insufficient_context",
        answer="",
        cited_source_numbers=[],
    )

    with pytest.raises(ValueError, match="must not be empty"):
        validate_generated_answer(
            generated,
            [],
        )