from typing import Annotated

from fastapi import (
    APIRouter, Depends, File, HTTPException, UploadFile, status)
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.schemas.documents import DocumentResponse
from backend.app.security.authentication import get_current_user
from backend.app.services.documents import (
    DocumentTooLargeError, InvalidDocumentError, UnsupportedDocumentTypeError, create_document)


router = APIRouter(
    prefix="/documents",
    tags=["documents"]
)


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)]) -> DocumentResponse:

    settings = get_settings()
    try:
        content_bytes = await file.read(settings.max_upload_size_bytes + 1)
    finally:
        await file.close()

    try:
        document = create_document(
            database_session,
            current_user.id,
            file.filename,
            content_bytes,
            max_upload_size_bytes=settings.max_upload_size_bytes,
            chunk_size=settings.chunk_size_characters,
            chunk_overlap=settings.chunk_overlap_characters
        )
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
    