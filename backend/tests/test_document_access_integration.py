from collections.abc import Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from sqlalchemy import delete

from backend.app.db.database import SessionLocal
from backend.app.db.models import User
from backend.app.routes import document_routes
from backend.app.main import app
from backend.app.rag.embeddings import EMBEDDING_DIMENSIONS, EmbeddingProvider


TEST_PASSWORD = "integration-test-password"

DOCUMENT_RESPONSE_FIELDS = {
    "id",
    "filename",
    "content_type",
    "size_bytes",
    "created_at"
}


@pytest.fixture
def document_access_usernames() -> Iterator[tuple[str, str]]:
    suffix = uuid4().hex
    first_username = f"document-owner-a-{suffix}"
    second_username = f"document-owner-b-{suffix}"

    yield first_username, second_username

    # Deleting the users also deletes their documents and chunks (cascade)
    with SessionLocal() as database_session:
        database_session.execute(
            delete(User).where(
                User.username.in_(
                    [first_username, second_username]
                )
            )
        )
        database_session.commit()


@pytest.fixture
def document_access_settings(monkeypatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        max_upload_size_bytes=100,
        chunk_size_characters=4,
        chunk_overlap_characters=1,
        prompt_injection_block_threshold=50,
    )

    monkeypatch.setattr(
        document_routes,
        "get_settings",
        lambda: settings
    )

    return settings


@pytest.fixture
def embedding_provider() -> Iterator[Mock]:
    provider = Mock(spec=EmbeddingProvider)

    provider.embed_texts.side_effect = lambda texts: [
        [float(index + 1)] * EMBEDDING_DIMENSIONS
        for index, _ in enumerate(texts)
    ]

    app.dependency_overrides[document_routes.get_embedding_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(document_routes.get_embedding_provider, None)


def register_and_login(client: TestClient, username: str) -> str:
    registration_response = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": TEST_PASSWORD
        }
    )

    assert registration_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        data={
            "username": username,
            "password": TEST_PASSWORD
        }
    )

    assert login_response.status_code == 200

    return login_response.json()["access_token"]


def upload_document(client: TestClient, access_token: str, filename: str, content: bytes) -> dict[str, object]:
    response = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {access_token}"},
        files={
            "file": (
                filename,
                content,
                "text/plain"
            ),
        }
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.integration
def test_each_user_lists_only_their_own_documents(
    client: TestClient,
    document_access_usernames: tuple[str, str],
    document_access_settings: SimpleNamespace,
    embedding_provider: Mock
) -> None:

    first_username, second_username = document_access_usernames

    first_token = register_and_login(client, first_username)
    second_token = register_and_login(client, second_username)

    first_document = upload_document(
        client,
        first_token,
        "first-owner-notes.txt",
        b"abcdefghij"
    )

    second_document = upload_document(
        client,
        second_token,
        "second-owner-notes.txt",
        b"klmnopqrst"
    )

    assert embedding_provider.embed_texts.call_count == 2

    embedding_calls = [
        provider_call.args[0]
        for provider_call in embedding_provider.embed_texts.call_args_list
    ]
    assert embedding_calls == [
        ["abcd", "defg", "ghij"],
        ["klmn", "nopq", "qrst"],
    ]

    first_response = client.get(
        "/documents",
        headers={"Authorization": f"Bearer {first_token}"}
    )

    second_response = client.get(
        "/documents",
        headers={"Authorization": f"Bearer {second_token}"}
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_listing = first_response.json()
    second_listing = second_response.json()

    assert [document["id"] for document in first_listing] == [first_document["id"]]
    assert [document["id"] for document in second_listing] == [second_document["id"]]

    assert first_document["id"] not in {document["id"] for document in second_listing}
    assert second_document["id"] not in {document["id"] for document in first_listing}

    assert set(first_listing[0]) == DOCUMENT_RESPONSE_FIELDS
    assert set(second_listing[0]) == DOCUMENT_RESPONSE_FIELDS


@pytest.mark.integration
def test_user_cannot_retrieve_another_users_document(
    client: TestClient,
    document_access_usernames: tuple[str, str],
    document_access_settings: SimpleNamespace,
    embedding_provider: Mock
) -> None:

    owner_username, other_username = document_access_usernames

    owner_token = register_and_login(client, owner_username)
    other_token = register_and_login(client, other_username)

    document = upload_document(
        client,
        owner_token,
        "private-security-notes.txt",
        b"abcdefghij",
    )

    embedding_provider.embed_texts.assert_called_once_with(["abcd", "defg", "ghij"])

    owner_response = client.get(
        f"/documents/{document['id']}",
        headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert owner_response.status_code == 200

    owner_response_data = owner_response.json()

    assert owner_response_data["id"] == document["id"]
    assert owner_response_data["filename"] == "private-security-notes.txt"
    assert set(owner_response_data) == DOCUMENT_RESPONSE_FIELDS
    assert "content" not in owner_response_data
    assert "owner_id" not in owner_response_data

    other_user_response = client.get(
        f"/documents/{document['id']}",
        headers={"Authorization": f"Bearer {other_token}"}
    )

    assert other_user_response.status_code == 404
    assert other_user_response.json() == {"detail": "Document not found"}
