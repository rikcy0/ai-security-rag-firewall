from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.rag.embeddings import EmbeddingGenerationError, EmbeddingProvider
from backend.app.rag.retriever import retrieve_chunks_for_owner
from backend.app.routes.dependencies import EMBEDDING_SERVICE_UNAVAILABLE_DETAIL, get_embedding_provider
from backend.app.schemas.retrieval import (
    RetrievedChunkResponse, SemanticSearchRequest, SemanticSearchResponse,
)
from backend.app.security.authentication import get_current_user


router = APIRouter(
    prefix="/retrieval",
    tags=["retrieval"]
)


@router.post(
    "/search",
    response_model=SemanticSearchResponse
)
def search_owned_chunks(
    request: SemanticSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)]
) -> SemanticSearchResponse:
    try:
        results = retrieve_chunks_for_owner(
            database_session,
            current_user.id,
            request.query,
            embedding_provider=embedding_provider,
            top_k=request.top_k
        )
    except EmbeddingGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBEDDING_SERVICE_UNAVAILABLE_DETAIL
        ) from exc

    return SemanticSearchResponse(
        results=[
            RetrievedChunkResponse.model_validate(result) for result in results
        ]
    )