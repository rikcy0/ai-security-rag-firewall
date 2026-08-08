from datetime import datetime, timezone
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import Document, User
from backend.app.main import app
from backend.app.routes import document_routes
from backend.app.security.authentication import get_current_user
from backend.app.services.documents import (
    DocumentTooLargeError,
    InvalidDocumentError,
    UnsupportedDocumentTypeError)


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
        username="alice",
        password_hash=PASSWORD_HASH,
        is_active=True
    )
    user.id = uuid4()

    app.dependency_overrides[get_current_user] = (lambda: user)
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def document_settings(monkeypatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        max_upload_size_bytes=4,
        chunk_size_characters=4,
        chunk_overlap_characters=1
    )

    monkeypatch.setattr(
        document_routes,
        "get_settings",
        lambda: settings
    )

    return settings


def make_document(owner_id) -> Document:
    document = Document(
        owner_id=owner_id,
        filename="notes.txt",
        content_type="text/plain",
        size_bytes=4,
        content="abcd"
    )
    document.id = uuid4()
    document.created_at = datetime(
        2026,
        1,
        1,
        tzinfo=timezone.utc
    )

    return document


# 
def test_authenticated_user_can_upload_document(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    document_settings: SimpleNamespace,
    monkeypatch) -> None:
    stored_document = make_document(authenticated_user.id)
    document_creator = Mock(return_value=stored_document)

    monkeypatch.setattr(
        document_routes,
        "create_document",
        document_creator
    )

    response = client.post(
        "/documents",
        files={
            "file": (
                "notes.txt",
                b"abcd",
                "text/plain"
            )
        },
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["id"] == str(stored_document.id)
    assert response_data["filename"] == "notes.txt"
    assert response_data["content_type"] == "text/plain"
    assert response_data["size_bytes"] == 4
    assert "created_at" in response_data
    assert "owner_id" not in response_data

    assert "content" not in response_data
    (
        called_session,
        called_owner_id,
        called_filename,
        called_content
    ) = document_creator.call_args.args

    assert called_session is database_session
    assert called_owner_id == authenticated_user.id
    assert called_filename == "notes.txt"
    assert called_content == b"abcd"

    assert document_creator.call_args.kwargs == { 
        "max_upload_size_bytes": 4,
        "chunk_size": 4,
        "chunk_overlap": 1,
    }


# configured limit = 4 bytes so route passes exaclty 4 + 1 = 5 bytes to service
def test_route_reads_only_limit_plus_one_byte(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    document_settings: SimpleNamespace,
    monkeypatch) -> None:
    document_creator = Mock(
        side_effect=DocumentTooLargeError("Document exceeds the maximum upload size")
    )

    monkeypatch.setattr(
        document_routes,
        "create_document",
        document_creator,
    )

    response = client.post(
        "/documents",
        files={
            "file": (
                "large.txt",
                b"123456789",
                "text/plain"
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Document exceeds the maximum upload size"}

    called_content = (document_creator.call_args.args[3])

    assert called_content == b"12345"


# validation-error mapping tests
@pytest.mark.parametrize(
    ("service_error", "expected_status"),
    [
        (UnsupportedDocumentTypeError("Only .txt and .md documents are supported"), 415),
        (InvalidDocumentError("Document contains no readable text"), 400)
    ],
)
def test_document_errors_are_mapped_to_http_responses(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    document_settings: SimpleNamespace,
    service_error: Exception,
    expected_status: int,
    monkeypatch) -> None:
    monkeypatch.setattr(
        document_routes,
        "create_document",
        Mock(side_effect=service_error),
    )

    response = client.post(
        "/documents",
        files={
            "file": (
                "document.txt",
                b"content",
                "text/plain",
            )
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": str(service_error)
    }


# missing file test
def test_upload_requires_file(
    client: TestClient,
    database_session: Mock,
    authenticated_user: User,
    document_settings: SimpleNamespace,
    monkeypatch) -> None:
    document_creator = Mock()

    monkeypatch.setattr(
        document_routes,
        "create_document",
        document_creator,
    )

    response = client.post("/documents")

    assert response.status_code == 422
    document_creator.assert_not_called()


def test_upload_requires_authentication(
    client: TestClient,
    database_session: Mock,
    document_settings: SimpleNamespace,
    monkeypatch) -> None:
    document_creator = Mock()

    monkeypatch.setattr(
        document_routes,
        "create_document",
        document_creator
    )

    response = client.post(
        "/documents",
        files={
            "file": (
                "document.txt",
                b"content",
                "text/plain"
            )
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"
    document_creator.assert_not_called()