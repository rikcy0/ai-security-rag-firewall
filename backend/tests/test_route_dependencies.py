from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from backend.app.rag.embeddings import EmbeddingProvider
from backend.app.routes import dependencies as route_dependencies
from backend.app.rag.generator import AnswerProvider


def test_embedding_provider_dependency_rejects_missing_api_key(monkeypatch) -> None:
    settings = SimpleNamespace(
        openai_api_key=None,
        embedding_model="text-embedding-3-small",
        openai_timeout_seconds=30.0,
        openai_max_retries=1
    )

    monkeypatch.setattr(
        route_dependencies,
        "get_settings",
        lambda: settings,
    )

    provider_dependency = (route_dependencies.get_embedding_provider())

    with pytest.raises(HTTPException) as exc_info:
        next(provider_dependency)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == ("Embedding service is unavailable")


def test_embedding_provider_dependency_creates_and_closes_client(monkeypatch) -> None:
    settings = SimpleNamespace(
        openai_api_key=SecretStr("fake-test-api-key"),
        embedding_model="text-embedding-3-small",
        openai_timeout_seconds=30.0,
        openai_max_retries=1,
    )

    openai_client = Mock()
    embedding_provider = Mock(spec=EmbeddingProvider)

    openai_client_factory = Mock(return_value=openai_client)
    embedding_provider_factory = Mock(return_value=embedding_provider)

    monkeypatch.setattr(
        route_dependencies,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        route_dependencies,
        "OpenAI",
        openai_client_factory,
    )
    monkeypatch.setattr(
        route_dependencies,
        "OpenAIEmbeddingProvider",
        embedding_provider_factory,
    )

    provider_dependency = (route_dependencies.get_embedding_provider())
    returned_provider = next(provider_dependency)

    assert returned_provider is embedding_provider

    openai_client_factory.assert_called_once_with(
        api_key="fake-test-api-key",
        timeout=30.0,
        max_retries=1
    )
    embedding_provider_factory.assert_called_once_with(
        client=openai_client,
        model="text-embedding-3-small",
    )

    openai_client.close.assert_not_called()
    provider_dependency.close()
    openai_client.close.assert_called_once_with()


def test_answer_provider_dependency_rejects_missing_api_key(monkeypatch) -> None:
    settings = SimpleNamespace(
        openai_api_key=None,
        generation_model="gpt-5.6-luna",
        rag_max_output_tokens=800,
        openai_timeout_seconds=30.0,
        openai_max_retries=1,
    )

    monkeypatch.setattr(
        route_dependencies,
        "get_settings",
        lambda: settings,
    )

    provider_dependency = (route_dependencies.get_answer_provider())
    with pytest.raises(HTTPException) as exc_info:
        next(provider_dependency)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == ("Answer service is unavailable")


def test_answer_provider_dependency_creates_and_closes_client(monkeypatch) -> None:
    settings = SimpleNamespace(
        openai_api_key=SecretStr("fake-test-api-key"),
        generation_model="gpt-5.6-luna",
        rag_max_output_tokens=800,
        openai_timeout_seconds=30.0,
        openai_max_retries=1,
    )

    openai_client = Mock()
    answer_provider = Mock(spec=AnswerProvider)

    openai_client_factory = Mock(
        return_value=openai_client
    )
    answer_provider_factory = Mock(
        return_value=answer_provider
    )

    monkeypatch.setattr(
        route_dependencies,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        route_dependencies,
        "OpenAI",
        openai_client_factory,
    )
    monkeypatch.setattr(
        route_dependencies,
        "OpenAIAnswerProvider",
        answer_provider_factory,
    )

    provider_dependency = (route_dependencies.get_answer_provider())
    returned_provider = next(provider_dependency)

    assert returned_provider is answer_provider

    openai_client_factory.assert_called_once_with(
        api_key="fake-test-api-key",
        timeout=30.0,
        max_retries=1,
    )
    answer_provider_factory.assert_called_once_with(
        client=openai_client,
        model="gpt-5.6-luna",
        max_output_tokens=800,
    )

    openai_client.close.assert_not_called()
    provider_dependency.close()
    openai_client.close.assert_called_once_with()