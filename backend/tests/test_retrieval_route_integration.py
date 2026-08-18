from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.app.db.database import SessionLocal
from backend.app.db.models import User
from backend.app.main import app
from backend.app.rag.embeddings import EMBEDDING_DIMENSIONS, EmbeddingProvider
from backend.app.routes import dependencies as route_dependencies
from backend.app.routes import document_routes


TEST_PASSWORD = "retrieval-integration-password"
OWNED_CONTENT = "Owned guidance about API key storage."
FOREIGN_CONTENT = "Foreign guidance about API key storage."
QUERY = "How should API keys be stored?"


def make_embedding(
    first_value: float,
    second_value: float,
) -> list[float]:
    return [
        first_value,
        second_value,
        *([0.0] * (EMBEDDING_DIMENSIONS - 2)),
    ]


@pytest.fixture
def retrieval_usernames() -> Iterator[tuple[str, str]]:
    suffix = uuid4().hex
    owner_username = f"retrieval-a-{suffix}"
    foreign_username = f"retrieval-b-{suffix}"

    yield owner_username, foreign_username

    with SessionLocal() as database_session:
        database_session.execute(
            delete(User).where(
                User.username.in_(
                    [owner_username, foreign_username]
                )
            )
        )
        database_session.commit()


@pytest.fixture
def retrieval_document_settings(monkeypatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        max_upload_size_bytes=1_000,
        chunk_size_characters=100,
        chunk_overlap_characters=20,
        prompt_injection_block_threshold=50
    )

    monkeypatch.setattr(
        document_routes,
        "get_settings",
        lambda: settings,
    )

    return settings


@pytest.fixture
def scripted_embedding_provider() -> Iterator[Mock]:
    provider = Mock(spec=EmbeddingProvider)

    def embed_texts(texts: list[str]) -> list[list[float]]:
        if texts == [OWNED_CONTENT]:
            return [make_embedding(0.8, 0.6)]

        if texts == [FOREIGN_CONTENT]:
            return [make_embedding(1.0, 0.0)]

        if texts == [QUERY]:
            return [make_embedding(1.0, 0.0)]

        raise AssertionError(
            f"Unexpected embedding input: {texts!r}"
        )

    provider.embed_texts.side_effect = embed_texts

    app.dependency_overrides[
        route_dependencies.get_embedding_provider
    ] = lambda: provider

    yield provider

    app.dependency_overrides.pop(
        route_dependencies.get_embedding_provider,
        None,
    )


def register_and_login(client: TestClient, username: str) -> str:
    registration_response = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": TEST_PASSWORD,
        },
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": TEST_PASSWORD,
        },
    )

    assert login_response.status_code == 200

    return login_response.json()["access_token"]


def upload_document(
    client: TestClient,
    access_token: str,
    filename: str,
    content: str,
) -> dict[str, object]:
    response = client.post(
        "/documents",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        files={
            "file": (
                filename,
                content.encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.integration
def test_authenticated_semantic_search_returns_only_owned_chunks(
    client: TestClient,
    retrieval_usernames: tuple[str, str],
    retrieval_document_settings: SimpleNamespace,
    scripted_embedding_provider: Mock,
) -> None:
    owner_username, foreign_username = retrieval_usernames

    owner_token = register_and_login(
        client,
        owner_username,
    )
    foreign_token = register_and_login(
        client,
        foreign_username,
    )

    owned_document = upload_document(
        client,
        owner_token,
        "owned-security-notes.txt",
        OWNED_CONTENT,
    )
    foreign_document = upload_document(
        client,
        foreign_token,
        "foreign-security-notes.txt",
        FOREIGN_CONTENT,
    )

    owner_search_response = client.post(
        "/retrieval/search",
        headers={
            "Authorization": f"Bearer {owner_token}"
        },
        json={
            "query": f"  {QUERY}  ",
            "top_k": 1,
        },
    )

    assert owner_search_response.status_code == 200

    owner_results = owner_search_response.json()["results"]

    assert len(owner_results) == 1

    owner_result = owner_results[0]

    assert owner_result["document_id"] == owned_document["id"]
    assert owner_result["document_id"] != foreign_document["id"]
    assert owner_result["filename"] == (
        "owned-security-notes.txt"
    )
    assert owner_result["chunk_index"] == 0
    assert owner_result["content"] == OWNED_CONTENT
    assert owner_result["similarity"] == pytest.approx(0.8)

    assert "owner_id" not in owner_result
    assert "embedding" not in owner_result

    foreign_search_response = client.post(
        "/retrieval/search",
        headers={
            "Authorization": f"Bearer {foreign_token}"
        },
        json={
            "query": QUERY,
            "top_k": 1,
        },
    )

    assert foreign_search_response.status_code == 200

    foreign_results = (
        foreign_search_response.json()["results"]
    )

    assert len(foreign_results) == 1
    assert (
        foreign_results[0]["document_id"]
        == foreign_document["id"]
    )
    assert (
        foreign_results[0]["document_id"]
        != owned_document["id"]
    )
    assert foreign_results[0]["similarity"] == pytest.approx(
        1.0
    )

    assert scripted_embedding_provider.embed_texts.call_count == 4