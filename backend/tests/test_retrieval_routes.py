from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.main import app
from backend.app.rag.embeddings import (
    EmbeddingGenerationError,
    EmbeddingProvider,
)
from backend.app.rag.retriever import RetrievedChunk
from backend.app.routes import (
    dependencies as route_dependencies,
)
from backend.app.routes import retrieval_routes
from backend.app.security.authentication import get_current_user


PASSWORD_HASH = "$argon2id$test-password-hash"


@pytest.fixture
def database_session() -> Iterator[Mock]:
    session = Mock(spec=Session)
    app.dependency_overrides[get_db] = lambda: session

    yield session

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def authenticated_user() -> Iterator[User]:
    user = User(
        username="retrieval-user",
        password_hash=PASSWORD_HASH,
        is_active=True,
    )
    user.id = uuid4()

    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def embedding_provider() -> Iterator[Mock]:
    provider = Mock(spec=EmbeddingProvider)

    app.dependency_overrides[
        route_dependencies.get_embedding_provider
    ] = lambda: provider

    yield provider

    app.dependency_overrides.pop(
        route_dependencies.get_embedding_provider,
        None,
    )


def make_retrieved_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="security-notes.md",
        chunk_index=2,
        content="Store API keys in environment variables.",
        similarity=0.91,
    )


def test_authenticated_user_can_search_owned_chunks(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    embedding_provider: Mock,
    monkeypatch
) -> None:
    retrieved_chunk = make_retrieved_chunk()
    retriever = Mock(return_value=[retrieved_chunk])

    monkeypatch.setattr(
        retrieval_routes,
        "retrieve_chunks_for_owner",
        retriever,
    )

    response = client.post(
        "/retrieval/search",
        json={
            "query": "  How should API keys be stored?  ",
            "top_k": 2,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "chunk_id": str(retrieved_chunk.chunk_id),
                "document_id": str(
                    retrieved_chunk.document_id
                ),
                "filename": "security-notes.md",
                "chunk_index": 2,
                "content": (
                    "Store API keys in environment variables."
                ),
                "similarity": 0.91,
            }
        ]
    }

    assert retriever.call_args.args == (
        database_session,
        authenticated_user.id,
        "How should API keys be stored?",
    )
    assert retriever.call_args.kwargs == {
        "embedding_provider": embedding_provider,
        "top_k": 2,
    }

    response_result = response.json()["results"][0]

    assert "owner_id" not in response_result
    assert "embedding" not in response_result


def test_search_returns_empty_result_envelope(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    embedding_provider: Mock,
    monkeypatch
) -> None:
    retriever = Mock(return_value=[])

    monkeypatch.setattr(
        retrieval_routes,
        "retrieve_chunks_for_owner",
        retriever,
    )

    response = client.post(
        "/retrieval/search",
        json={"query": "security guidance"},
    )

    assert response.status_code == 200
    assert response.json() == {"results": []}

    assert retriever.call_args.kwargs["top_k"] == 5


@pytest.mark.parametrize(
    "request_body",
    [
        {"query": "   "},
        {
            "query": "security guidance",
            "top_k": 21,
        },
        {
            "query": "security guidance",
            "owner_id": str(uuid4()),
        },
    ],
)
def test_search_rejects_invalid_request_before_retrieval(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    embedding_provider: Mock,
    request_body: dict[str, object],
    monkeypatch
) -> None:
    retriever = Mock()

    monkeypatch.setattr(
        retrieval_routes,
        "retrieve_chunks_for_owner",
        retriever,
    )

    response = client.post(
        "/retrieval/search",
        json=request_body,
    )

    assert response.status_code == 422
    retriever.assert_not_called()


def test_search_requires_authentication(
    client: TestClient,
    database_session: Mock,
    embedding_provider: Mock,
    monkeypatch
) -> None:
    retriever = Mock()

    monkeypatch.setattr(
        retrieval_routes,
        "retrieve_chunks_for_owner",
        retriever,
    )

    response = client.post(
        "/retrieval/search",
        json={"query": "security guidance"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Could not validate credentials"
    }
    assert response.headers["www-authenticate"] == "Bearer"

    retriever.assert_not_called()


def test_embedding_failure_returns_generic_service_unavailable(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    embedding_provider: Mock,
    monkeypatch,
) -> None:
    internal_error = (
        "OpenAI rejected the query with private provider details"
    )
    retriever = Mock(
        side_effect=EmbeddingGenerationError(internal_error)
    )

    monkeypatch.setattr(
        retrieval_routes,
        "retrieve_chunks_for_owner",
        retriever,
    )

    response = client.post(
        "/retrieval/search",
        json={"query": "security guidance"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Embedding service is unavailable"
    }
    assert internal_error not in response.text


def test_search_rejects_missing_embedding_configuration(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    monkeypatch
) -> None:
    settings = SimpleNamespace(
        openai_api_key=None,
        embedding_model="text-embedding-3-small",
    )
    retriever = Mock()

    monkeypatch.setattr(
        route_dependencies,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        retrieval_routes,
        "retrieve_chunks_for_owner",
        retriever,
    )

    response = client.post(
        "/retrieval/search",
        json={"query": "security guidance"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Embedding service is unavailable"
    }

    retriever.assert_not_called()