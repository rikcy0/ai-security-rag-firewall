from collections.abc import Iterator

from fastapi import HTTPException, status
from openai import OpenAI

from backend.app.config import get_settings
from backend.app.rag.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from backend.app.rag.generator import AnswerProvider, OpenAIAnswerProvider

EMBEDDING_SERVICE_UNAVAILABLE_DETAIL = "Embedding service is unavailable"
ANSWER_SERVICE_UNAVAILABLE_DETAIL = "Answer service is unavailable"


def get_embedding_provider() -> Iterator[EmbeddingProvider]:
    settings = get_settings()

    if settings.openai_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBEDDING_SERVICE_UNAVAILABLE_DETAIL
        )

    client = OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries
    )

    try:
        yield OpenAIEmbeddingProvider(
            client=client,
            model=settings.embedding_model
        )
    finally:
        client.close()


def get_answer_provider() -> Iterator[AnswerProvider]:
    settings = get_settings()

    if settings.openai_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ANSWER_SERVICE_UNAVAILABLE_DETAIL
        )

    client = OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries
    )

    try:
        yield OpenAIAnswerProvider(
            client=client,
            model=settings.generation_model,
            max_output_tokens=settings.rag_max_output_tokens
        )
    finally:
        client.close()