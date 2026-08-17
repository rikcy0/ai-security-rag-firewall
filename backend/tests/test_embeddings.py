from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai import OpenAIError

from backend.app.rag.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingGenerationError,
    OpenAIEmbeddingProvider
)


MODEL = "text-embedding-3-small"


def make_vector(
    value: float,
    *,
    dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return [value] * dimensions


def make_response(values: list[float]) -> SimpleNamespace:
    return SimpleNamespace(
        data=[
            SimpleNamespace(
                index=index,
                embedding=make_vector(value),
            )
            for index, value in enumerate(values)
        ]
    )


def test_embedding_provider_sends_expected_request() -> None:
    client = Mock()
    client.embeddings.create.return_value = make_response([0.1, 0.2])

    provider = OpenAIEmbeddingProvider(client, MODEL)

    embeddings = provider.embed_texts(["first chunk", "second chunk"])

    assert embeddings == [make_vector(0.1), make_vector(0.2)]

    client.embeddings.create.assert_called_once_with(
        model=MODEL,
        input=["first chunk", "second chunk"],
        dimensions=EMBEDDING_DIMENSIONS,
        encoding_format="float",
    )


def test_embedding_provider_restores_response_order() -> None:
    client = Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=1,
                embedding=make_vector(0.2),
            ),
            SimpleNamespace(
                index=0,
                embedding=make_vector(0.1),
            ),
        ]
    )

    provider = OpenAIEmbeddingProvider(client, MODEL)

    embeddings = provider.embed_texts(["first chunk", "second chunk"])

    assert embeddings == [make_vector(0.1), make_vector(0.2)]


def test_embedding_provider_splits_inputs_into_batches() -> None:
    client = Mock()
    client.embeddings.create.side_effect = [
        make_response([0.1, 0.2]),
        make_response([0.3]),
    ]

    provider = OpenAIEmbeddingProvider(client, MODEL, batch_size=2,
    )

    embeddings = provider.embed_texts(
        ["first", "second", "third"]
    )

    assert [vector[0] for vector in embeddings] == [0.1, 0.2, 0.3]

    assert [
        call.kwargs["input"] for call in client.embeddings.create.call_args_list
    ] == [
        ["first", "second"],
        ["third"],
    ]


def test_embedding_provider_returns_empty_list_without_request() -> None:
    client = Mock()
    provider = OpenAIEmbeddingProvider(client, MODEL)

    assert provider.embed_texts([]) == []
    client.embeddings.create.assert_not_called()


def test_embedding_provider_rejects_empty_input_text() -> None:
    client = Mock()
    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(
        ValueError,
        match="Embedding inputs must not be empty",
    ):
        provider.embed_texts(["valid chunk", "   "])

    client.embeddings.create.assert_not_called()


def test_embedding_provider_rejects_missing_result() -> None:
    client = Mock()
    client.embeddings.create.return_value = make_response([0.1])

    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(
        EmbeddingGenerationError,
        match="unexpected result count",
    ):
        provider.embed_texts(["first", "second"])


def test_embedding_provider_rejects_wrong_vector_dimension() -> None:
    client = Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=[0.1],
            )
        ]
    )

    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(
        EmbeddingGenerationError,
        match="unexpected vector dimension",
    ):
        provider.embed_texts(["chunk"])


def test_embedding_provider_rejects_nonfinite_values() -> None:
    client = Mock()
    vector = make_vector(0.1)
    vector[0] = float("nan")

    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=vector,
            )
        ]
    )

    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(
        EmbeddingGenerationError,
        match="non-finite",
    ):
        provider.embed_texts(["chunk"])


def test_embedding_provider_wraps_openai_errors() -> None:
    client = Mock()
    client.embeddings.create.side_effect = OpenAIError(
        "provider unavailable"
    )

    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(
        EmbeddingGenerationError,
        match="Embedding provider request failed",
    ) as exc_info:
        provider.embed_texts(["chunk"])

    assert isinstance(exc_info.value.__cause__, OpenAIError)


def test_embedding_provider_strips_model_name() -> None:
    client = Mock()
    client.embeddings.create.return_value = make_response([0.1])

    provider = OpenAIEmbeddingProvider(
        client,
        f"  {MODEL}  ",
    )

    provider.embed_texts(["chunk"])

    assert (client.embeddings.create.call_args.kwargs["model"] == MODEL)


def test_embedding_provider_rejects_invalid_vector_value() -> None:
    client = Mock()

    invalid_vector: list[object] = [0.1 for _ in range(EMBEDDING_DIMENSIONS)]
    invalid_vector[0] = "not-a-number"

    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=invalid_vector,
            )
        ]
    )

    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(EmbeddingGenerationError, match="invalid vector value"):
        provider.embed_texts(["chunk"])


def test_embedding_provider_rejects_zero_vector() -> None:
    client = Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(
                index=0,
                embedding=make_vector(0.0),
            )
        ]
    )

    provider = OpenAIEmbeddingProvider(client, MODEL)

    with pytest.raises(EmbeddingGenerationError, match="zero vector"):
        provider.embed_texts(["chunk"])