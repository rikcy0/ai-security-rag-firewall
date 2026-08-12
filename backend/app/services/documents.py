from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, load_only

from backend.app.db.models import Document, DocumentChunk
from backend.app.rag.chunker import chunk_text

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".txt": "text/plain",
    ".md": "text/markdown"
}


class DocumentUploadError(Exception):
    """Base error for document-upload validation failures."""


class InvalidDocumentError(DocumentUploadError):
    """Raised when document metadata or content is invalid."""


class UnsupportedDocumentTypeError(DocumentUploadError):
    """Raised when the filename has an unsupported extension."""


class DocumentTooLargeError(DocumentUploadError):
    """Raised when document bytes exceed the configured limit."""


def normalize_document_filename(filename:str | None) -> tuple[str, str]:
    if filename is None:
        raise InvalidDocumentError("A filename is required")

    safe_filename = filename.replace("\\","/").rsplit("/", maxsplit=1)[-1].strip()

    if not safe_filename:
        raise InvalidDocumentError("A filename is required")
    if "\x00" in safe_filename:
        raise InvalidDocumentError("Filename contains an unsupported null character")
    if len(safe_filename) > 255:
        raise InvalidDocumentError("Filename must not exceed 255 characters")

    extension = Path(safe_filename).suffix.lower()
    try:
        content_type = ALLOWED_DOCUMENT_EXTENSIONS[extension]
    except KeyError as exc:
        raise UnsupportedDocumentTypeError("Only .txt and .md documents are supported") from exc

    return safe_filename, content_type


def decode_document_content(content_bytes: bytes, max_upload_size_bytes: int) -> str:
    if max_upload_size_bytes <= 0:
        raise ValueError("max_upload_size_bytes must be greater than zero")
    if len(content_bytes) > max_upload_size_bytes:
        raise DocumentTooLargeError("Document exceeds the maximum upload size")
    if not content_bytes:
        raise InvalidDocumentError("Document contains no readable text")

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidDocumentError("Document must contain valid UTF-8 text") from exc

    if "\x00" in content:
        raise InvalidDocumentError("Document contains an unsupported null character")
    if not content.strip():
        raise InvalidDocumentError("Document contains no readable text")

    return content


def create_document(
    database_session: Session,
    owner_id: UUID,
    filename: str | None,
    content_bytes: bytes,
    *, # the int parameters after must be passed by name
    max_upload_size_bytes: int,
    chunk_size: int,
    chunk_overlap: int
) -> Document:

    safe_filename, content_type = normalize_document_filename(filename)
    content = decode_document_content(content_bytes, max_upload_size_bytes)
    chunks = chunk_text(content, chunk_size=chunk_size, overlap=chunk_overlap)

    if not chunks: 
        raise InvalidDocumentError("Document contains no readable text")

    document = Document(
        owner_id=owner_id,
        filename=safe_filename,
        content_type=content_type,
        size_bytes=len(content_bytes),
        content=content
    )

    try:
        database_session.add(document)
        # flush inserts the document into the SQL db without commiting the transaction
        # Makes the document UUID available for the chunks
        database_session.flush()
        database_session.refresh(document)

        document_chunks = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk_index,
                content=chunk_content
            )
            for chunk_index, chunk_content in enumerate(chunks)
        ]
        database_session.add_all(document_chunks)
        database_session.commit()
        
    except SQLAlchemyError:
        database_session.rollback()
        raise

    return document
    

def list_documents_for_owner(database_session: Session, owner_id: UUID) -> list[Document]:
    statement = (
        select(Document)
        .options(
            load_only(
                Document.id,
                Document.filename,
                Document.content_type,
                Document.size_bytes,
                Document.created_at
            )
        )
        .where(Document.owner_id == owner_id
        )
        .order_by(
            Document.created_at.desc(),
            Document.id.desc()
        )
    )

    return list(database_session.scalars(statement).all())


# Will return none if: doc does not exist or does but belongs to another user
def get_document_for_owner(
        database_session: Session,
        owner_id: UUID,
        document_id: UUID) -> Document | None:
    statement = (
        select(Document)
        .options(
            load_only(
                Document.id,
                Document.filename,
                Document.content_type,
                Document.size_bytes,
                Document.created_at
            )
        )
        .where(
            Document.id == document_id,
            Document.owner_id == owner_id
        )
    )

    return database_session.scalar(statement)