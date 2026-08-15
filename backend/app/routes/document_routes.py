from typing import Annotated

from uuid import UUID
from fastapi import (
    APIRouter, Depends, File, HTTPException, UploadFile, status)
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.schemas.documents import DocumentResponse
from backend.app.security.authentication import get_current_user
from backend.app.services.documents import (
    DocumentTooLargeError, InvalidDocumentError, PromptInjectionDetectedError,
    UnsupportedDocumentTypeError, create_document, get_document_for_owner, list_documents_for_owner)


router = APIRouter(
    prefix="/documents",
    tags=["documents"]
)


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED
)
def upload_document(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)]) -> DocumentResponse:

    settings = get_settings()

    filename = file.filename
    try: # 1 extra byte to account for oversized document case
        content_bytes = file.file.read(settings.max_upload_size_bytes + 1)
    finally:
        file.file.close()

    try:
        document = create_document(
            database_session,
            current_user.id,
            filename,
            content_bytes,
            max_upload_size_bytes=settings.max_upload_size_bytes,
            chunk_size=settings.chunk_size_characters,
            chunk_overlap=settings.chunk_overlap_characters,
            prompt_injection_block_threshold=settings.prompt_injection_block_threshold
        )
    except PromptInjectionDetectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)
        ) from exc
    except DocumentTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,   
            detail=str(exc)
        ) from exc
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc)
        ) from exc
    except InvalidDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=list[DocumentResponse]
)
def read_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)]) -> list[DocumentResponse]:

    documents = list_documents_for_owner(database_session, current_user.id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse
)
def read_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)]) -> DocumentResponse:

    document = get_document_for_owner(database_session, current_user.id, document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return DocumentResponse.model_validate(document)