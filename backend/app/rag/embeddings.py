from math import isfinite
from typing import Protocol

from openai import OpenAI, OpenAIError


EMBEDDING_DIMENSIONS = 1_536
DEFAULT_EMBEDDING_BATCH_SIZE = 100


# OpenAI is a trusted provider but is still crossing an external boundary
class EmbeddingGenerationError(RuntimeError):
    """Raised when an embedding provider cannot return valid vectors."""


# Protocol used for structural subtyping: specify a set of methods or attirbutes an object must have
# Ex: An embedding provider will have the embed_texts()
# Ex: OpenAIEmbeddingProvider does not inhert but has matching methods
class EmbeddingProvider(Protocol):
    """Application-facing interface for embedding texts."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector for each input string."""


class OpenAIEmbeddingProvider:
    """Generate text embeddings through the synchronous OpenAI client."""

    def __init__(
        self,
        client: OpenAI, # provider receives the client
        model: str, # ex: "text-embedding-3-small"
        *,
        dimensions: int = EMBEDDING_DIMENSIONS,
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE
        ) -> None:

        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("Embedding model must not be empty")
        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be greater than zero")
        if batch_size <= 0:
            raise ValueError("Embedding batch size must be greater than zero")

        self._client = client
        self._model = normalized_model
        self._dimensions = dimensions
        self._batch_size = batch_size

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if any(not text.strip() for text in texts):
            raise ValueError("Embedding inputs must not be empty")

        embeddings: list[list[float]] = []
        for batch_start in range(0, len(texts), self._batch_size):
            batch = texts[batch_start:batch_start + self._batch_size]

            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                    dimensions=self._dimensions,
                    encoding_format="float"
                )
            except OpenAIError as exc:
                raise EmbeddingGenerationError(
                    "Embedding provider request failed"
                ) from exc

            # use input's index in the batch as sorting key
            ordered_data = sorted(response.data, key=lambda item: item.index)

            returned_indexes = [item.index for item in ordered_data]
            expected_indexes = list(range(len(batch)))
            if returned_indexes != expected_indexes:
                raise EmbeddingGenerationError(
                    "Embedding provider returned an unexpected result count"
                )

            for item in ordered_data:
                try:    # convert every value in the embedding into a float
                    vector = [float(value) for value in item.embedding]
                except (TypeError, ValueError, OverflowError) as exc:
                    raise EmbeddingGenerationError(
                        "Embedding provider returned an invalid vector value"
                    ) from exc
                if len(vector) != self._dimensions:
                    raise EmbeddingGenerationError(
                        "Embedding provider returned an unexpected vector dimension"
                    )
                if not all(isfinite(value) for value in vector):
                    raise EmbeddingGenerationError(
                        "Embedding provider returned a non-finite vector value"
                    )
                if not any(value != 0.0 for value in vector):
                    raise EmbeddingGenerationError(
                        "Embedding provider returned a zero vector"
                    )

                embeddings.append(vector)

        return embeddings