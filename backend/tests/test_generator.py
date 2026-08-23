import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai import OpenAIError
from pydantic import ValidationError

from backend.app.rag.constants import MAX_RETRIEVAL_QUERY_CHARACTERS
from backend.app.rag.generator import (
    GROUNDING_INSTRUCTIONS,
    AnswerContext,
    AnswerProviderUnavailableError,
    AnswerRefusedError,
    AnswerResponseInvalidError,
    GeneratedAnswer,
    OpenAIAnswerProvider,
    validate_generated_answer,
)

MODEL = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 800

def make_context(source_number: int = 1) -> AnswerContext:
    return AnswerContext(
        source_number=source_number,
        content="Store secrets outside the source code.",
    )

def make_provider_response(
    generated_answer: object = None,
    *,
    status: str = "completed",
    refusal: bool = False,
) -> SimpleNamespace:
    output = []

    if refusal:
        output = [
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        type="refusal",
                        refusal="Refusal details must remain private",
                    )
                ],
            )
        ]

    return SimpleNamespace(
        status=status,
        output=output,
        output_parsed=generated_answer,
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


# core provider tests
def test_openai_answer_provider_sends_minimized_structured_request() -> None:
    client = Mock()

    generated = GeneratedAnswer(
        status="answered",
        answer="Store secrets outside source code [1].",
        cited_source_numbers=[1],
    )

    client.responses.parse.return_value = make_provider_response(generated)

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    result = provider.generate_answer(
        "  How should secrets be stored?  ",
        [make_context(1)],
    )

    assert result == generated

    request = client.responses.parse.call_args.kwargs

    assert request["model"] == MODEL
    assert request["instructions"] == GROUNDING_INSTRUCTIONS
    assert request["text_format"] is GeneratedAnswer
    assert request["reasoning"] == {"effort": "none"}
    assert request["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert request["store"] is False

    assert json.loads(request["input"]) == {
        "query": "How should secrets be stored?",
        "sources": [
            {
                "source_number": 1,
                "content": "Store secrets outside the source code.",
            }
        ],
    }


def test_openai_answer_provider_strips_model_name() -> None:
    client = Mock()

    generated = GeneratedAnswer(
        status="insufficient_context",
        answer="",
        cited_source_numbers=[],
    )

    client.responses.parse.return_value = make_provider_response(
        generated
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=f"  {MODEL}  ",
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    provider.generate_answer(
        "Question",
        [make_context()],
    )

    assert (
        client.responses.parse.call_args.kwargs["model"]
        == MODEL
    )


@pytest.mark.parametrize("model", ["", "   "])
def test_openai_answer_provider_rejects_empty_model(
    model: str,
) -> None:
    with pytest.raises(ValueError, match="model must not be empty"):
        OpenAIAnswerProvider(
            client=Mock(),
            model=model,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )


@pytest.mark.parametrize("max_output_tokens", [0, -1])
def test_openai_answer_provider_rejects_invalid_output_limit(
    max_output_tokens: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="must be at least 16",
    ):
        OpenAIAnswerProvider(
            client=Mock(),
            model=MODEL,
            max_output_tokens=max_output_tokens,
        )


def test_openai_answer_provider_rejects_empty_query() -> None:
    client = Mock()

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(ValueError, match="query must not be empty"):
        provider.generate_answer(
            "   ",
            [make_context()],
        )

    client.responses.parse.assert_not_called()


def test_openai_answer_provider_rejects_oversized_query() -> None:
    client = Mock()

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(ValueError, match="maximum length"):
        provider.generate_answer(
            "x" * (MAX_RETRIEVAL_QUERY_CHARACTERS + 1),
            [make_context()],
        )

    client.responses.parse.assert_not_called()


def test_openai_answer_provider_requires_contexts() -> None:
    client = Mock()

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(ValueError, match="must not be empty"):
        provider.generate_answer("Question", [])

    client.responses.parse.assert_not_called()


def test_openai_answer_provider_rejects_duplicate_context_numbers() -> None:
    client = Mock()

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(ValueError, match="must be unique"):
        provider.generate_answer(
            "Question",
            [
                make_context(1),
                make_context(1),
            ],
        )

    client.responses.parse.assert_not_called()


# external-failure tests
def test_openai_answer_provider_wraps_openai_errors() -> None:
    client = Mock()
    client.responses.parse.side_effect = OpenAIError(
        "private provider details"
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerProviderUnavailableError,
        match="request failed",
    ) as exc_info:
        provider.generate_answer(
            "Question",
            [make_context()],
        )

    assert isinstance(exc_info.value.__cause__, OpenAIError)
    assert "private provider details" not in str(exc_info.value)


def test_openai_answer_provider_rejects_refusal() -> None:
    client = Mock()
    client.responses.parse.return_value = make_provider_response(
        refusal=True
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerRefusedError,
        match="refused",
    ):
        provider.generate_answer(
            "Question",
            [make_context()],
        )


@pytest.mark.parametrize(
    "response_status",
    [
        "queued",
        "in_progress",
        "incomplete",
        "cancelled",
    ],
)
def test_openai_answer_provider_rejects_incomplete_status(response_status: str) -> None:
    client = Mock()
    client.responses.parse.return_value = make_provider_response(
        status=response_status
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerResponseInvalidError,
        match="did not complete",
    ):
        provider.generate_answer(
            "Question",
            [make_context()],
        )


def test_openai_answer_provider_translates_failed_status() -> None:
    client = Mock()
    client.responses.parse.return_value = make_provider_response(
        status="failed"
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerProviderUnavailableError,
        match="response failed",
    ):
        provider.generate_answer(
            "Question",
            [make_context()],
        )


def test_openai_answer_provider_requires_parsed_output() -> None:
    client = Mock()
    client.responses.parse.return_value = make_provider_response()

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerResponseInvalidError,
        match="no structured answer",
    ):
        provider.generate_answer(
            "Question",
            [make_context()],
        )


def test_openai_answer_provider_rejects_invalid_parsed_output() -> None:
    client = Mock()
    client.responses.parse.return_value = make_provider_response(
        {
            "status": "answered",
            "answer": "",
            "cited_source_numbers": [],
        }
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerResponseInvalidError,
        match="invalid structured response",
    ):
        provider.generate_answer(
            "Question",
            [make_context()],
        )


def test_openai_answer_provider_revalidates_citations() -> None:
    client = Mock()

    generated = GeneratedAnswer(
        status="answered",
        answer="Use the unavailable source [2].",
        cited_source_numbers=[2],
    )

    client.responses.parse.return_value = make_provider_response(
        generated
    )

    provider = OpenAIAnswerProvider(
        client=client,
        model=MODEL,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    with pytest.raises(
        AnswerResponseInvalidError,
        match="unavailable source",
    ):
        provider.generate_answer(
            "Question",
            [make_context(1)],
        )


# missing citation test
@pytest.mark.parametrize(
    "invalid_citation",
    ["[0]", "[01]"],
)
def test_validation_rejects_noncanonical_inline_citation(invalid_citation: str) -> None:
    generated = GeneratedAnswer(
        status="answered",
        answer=f"Use the recommended control {invalid_citation}.",
        cited_source_numbers=[1],
    )

    with pytest.raises(
        AnswerResponseInvalidError,
        match="invalid citation format",
    ):
        validate_generated_answer(
            generated,
            [make_context(1)],
        )