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
from backend.app.rag.generator import AnswerContext, AnswerProvider, GeneratedAnswer
from backend.app.routes import dependencies as route_dependencies
from backend.app.routes import document_routes, rag_routes


TEST_PASSWORD = "rag-integration-password"

OWNED_CONTENT = (
    "Owned guidance about storing API keys."
)
FOREIGN_CONTENT = (
    "Foreign guidance about storing API keys."
)
QUERY = "How should API keys be stored?"


# vectors deliberately make foreign doc more similar to query
def make_embedding(first_value: float, second_value: float) -> list[float]:
    return [
        first_value,
        second_value,
        *([0.0] * (EMBEDDING_DIMENSIONS - 2)),
    ]

@pytest.fixture
def rag_usernames() -> Iterator[tuple[str, str]]:
    suffix = uuid4().hex

    owner_username = f"rag-owner-{suffix}"
    foreign_username = f"rag-foreign-{suffix}"

    yield owner_username, foreign_username

    # User deletion cascades to documents and chunks.
    with SessionLocal() as database_session:
        database_session.execute(
            delete(User).where(
                User.username.in_(
                    [
                        owner_username,
                        foreign_username,
                    ]
                )
            )
        )
        database_session.commit()

@pytest.fixture
def rag_integration_settings(monkeypatch) -> None:
    document_settings = SimpleNamespace(
        max_upload_size_bytes=1_000,
        chunk_size_characters=100,
        chunk_overlap_characters=20,
        prompt_injection_block_threshold=50,
    )

    answer_settings = SimpleNamespace(
        rag_answer_top_k=5,
        rag_max_context_characters=20_000,
        prompt_injection_block_threshold=50,
    )

    monkeypatch.setattr(
        document_routes,
        "get_settings",
        lambda: document_settings,
    )
    monkeypatch.setattr(
        rag_routes,
        "get_settings",
        lambda: answer_settings,
    )

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

@pytest.fixture
def scripted_answer_provider() -> Iterator[Mock]:
    provider = Mock(spec=AnswerProvider)

    provider.generate_answer.return_value = GeneratedAnswer(
        status="answered",
        answer="Store API keys according to the retrieved guidance [1].",
        cited_source_numbers=[1],
    )

    app.dependency_overrides[
        route_dependencies.get_answer_provider
    ] = lambda: provider

    yield provider

    app.dependency_overrides.pop(
        route_dependencies.get_answer_provider,
        None,
    )

# helper methods
def register_and_login(
    client: TestClient,
    username: str,
) -> str:
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


# integration tests
@pytest.mark.integration
def test_rag_answer_uses_only_authenticated_owners_chunks(
    client: TestClient,
    rag_usernames: tuple[str, str],
    rag_integration_settings: None,
    scripted_embedding_provider: Mock,
    scripted_answer_provider: Mock,
) -> None:
    owner_username, foreign_username = rag_usernames

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

    response = client.post(
        "/rag/answer",
        headers={
            "Authorization": f"Bearer {owner_token}"
        },
        json={
            "query": f"  {QUERY}  ",
        },
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["status"] == "answered"
    assert response_data["answer"] == (
        "Store API keys according to the "
        "retrieved guidance [1]."
    )

    assert len(response_data["sources"]) == 1

    source = response_data["sources"][0]

    assert source["source_number"] == 1
    assert source["document_id"] == owned_document["id"]
    assert source["document_id"] != foreign_document["id"]
    assert source["filename"] == "owned-security-notes.txt"
    assert source["chunk_index"] == 0
    assert source["similarity"] == pytest.approx(0.8)

    assert "content" not in source
    assert "owner_id" not in source
    assert "embedding" not in source

    scripted_answer_provider.generate_answer.assert_called_once_with(
        QUERY,
        [
            AnswerContext(
                source_number=1,
                content=OWNED_CONTENT,
            )
        ],
    )

    embedding_calls = [
        provider_call.args[0]
        for provider_call
        in scripted_embedding_provider.embed_texts.call_args_list
    ]

    assert embedding_calls == [
        [OWNED_CONTENT],
        [FOREIGN_CONTENT],
        [QUERY],
    ]