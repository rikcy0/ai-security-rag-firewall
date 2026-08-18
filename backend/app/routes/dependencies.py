from collections.abc import Iterator

from fastapi import HTTPException, status
from openai import OpenAI

from backend.app.config import get_settings
from backend.app.rag.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider


EMBEDDING_SERVICE_UNAVAILABLE_DETAIL = "Embedding service is unavailable"


def get_embedding_provider() -> Iterator[EmbeddingProvider]:
    settings = get_settings()

    if settings.openai_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBEDDING_SERVICE_UNAVAILABLE_DETAIL
        )

    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    try:
        yield OpenAIEmbeddingProvider(
            client=client,
            model=settings.embedding_model
        )
    finally:
        client.close()