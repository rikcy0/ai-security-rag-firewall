from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.models import Document
from backend.app.services.documents import (
    DocumentTooLargeError, InvalidDocumentError, UnsupportedDocumentTypeError, create_document)


OWNER_ID = uuid4()


@pytest.fixture
def database_session() -> Mock:
    session = Mock(spec=Session)

    def assign_document_id() -> None:
        document = session.add.call_args.args[0]
        document.id = uuid4()

    session.flush.side_effect = assign_document_id

    return session


def test_create_document_persists_document_and_chunks(database_session: Mock) -> None:
    document = create_document(
        database_session,
        OWNER_ID,
        r"C:\fakepath\security.TXT",
        b"abcdefghij",
        max_upload_size_bytes=100,
        chunk_size=4,
        chunk_overlap=1
    )

    assert isinstance(document, Document)
    assert document.owner_id == OWNER_ID
    assert document.filename == "security.TXT"
    assert document.content_type == "text/plain"
    assert document.size_bytes == 10
    assert document.content == "abcdefghij"

    database_session.add.assert_called_once_with(document)
    database_session.flush.assert_called_once()

    persisted_chunks = (database_session.add_all.call_args.args[0])

    assert [chunk.chunk_index for chunk in persisted_chunks] == [0, 1, 2]
    assert [chunk.content for chunk in persisted_chunks] == ["abcd", "defg", "ghij"]
    assert all(chunk.document_id == document.id for chunk in persisted_chunks)

    database_session.commit.assert_called_once()
    database_session.rollback.assert_not_called()
    database_session.refresh.assert_called_once_with(document)


def test_markdown_extension_uses_canonical_content_type(database_session: Mock) -> None:
    document = create_document(
        database_session,
        OWNER_ID,
        "notes.md",
        b"# Security Notes",
        max_upload_size_bytes=100,
        chunk_size=100,
        chunk_overlap=20
    )

    assert document.filename == "notes.md"
    assert document.content_type == "text/markdown"


@pytest.mark.parametrize(
    "filename",
    [
        None,
        "",
        "folder/"
    ]
)
def test_missing_filename_is_rejected(database_session: Mock, filename: str | None) -> None:
    with pytest.raises(InvalidDocumentError, match="A filename is required"):
        create_document(
            database_session,
            OWNER_ID,
            filename,
            b"document content",
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()
    database_session.commit.assert_not_called()


def test_oversized_filename_is_rejected(database_session: Mock) -> None:
    filename = f"{'a' * 252}.txt"

    with pytest.raises(InvalidDocumentError, match="Filename must not exceed 255 characters"):
        create_document(
            database_session,
            OWNER_ID,
            filename,
            b"document content",
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()


def test_unsupported_extension_is_rejected(database_session: Mock) -> None:
    with pytest.raises(UnsupportedDocumentTypeError, match=r"Only \.txt and \.md documents are supported"):
        create_document(
            database_session,
            OWNER_ID,
            "document.pdf",
            b"pretend PDF content",
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()


def test_oversized_document_is_rejected(database_session: Mock) -> None:
    with pytest.raises(DocumentTooLargeError, match="Document exceeds the maximum upload size"):
        create_document(
            database_session,
            OWNER_ID,
            "large.txt",
            b"12345",
            max_upload_size_bytes=4,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()


@pytest.mark.parametrize(
    "content_bytes",
    [
        b"",
        b"  \n\t  "
    ]
)
def test_document_without_readable_text_is_rejected(database_session: Mock, content_bytes: bytes) -> None:
    with pytest.raises(InvalidDocumentError, match="Document contains no readable text"):
        create_document(
            database_session,
            OWNER_ID,
            "empty.txt",
            content_bytes,
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()


def test_invalid_utf8_is_rejected(database_session: Mock) -> None:
    with pytest.raises(InvalidDocumentError, match="Document must contain valid UTF-8 text"):
        create_document(
            database_session,
            OWNER_ID,
            "binary.txt",
            b"\xff\xfe\x00\x01",
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()


def test_null_character_is_rejected(database_session: Mock) -> None:
    with pytest.raises(InvalidDocumentError, match="unsupported null character"):
        create_document(
            database_session,
            OWNER_ID,
            "document.txt",
            b"before\x00after",
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.add.assert_not_called()


def test_database_failure_rolls_back_transaction(database_session: Mock) -> None:
    database_session.commit.side_effect = SQLAlchemyError("database failure")

    with pytest.raises(SQLAlchemyError):
        create_document(
            database_session,
            OWNER_ID,
            "document.txt",
            b"document content",
            max_upload_size_bytes=100,
            chunk_size=100,
            chunk_overlap=20
        )

    database_session.rollback.assert_called_once()
    