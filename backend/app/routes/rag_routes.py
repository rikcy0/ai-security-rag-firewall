from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.rag.embeddings import EmbeddingGenerationError, EmbeddingProvider
from backend.app.rag.generator import AnswerGenerationError, AnswerProvider, AnswerRefusedError
from backend.app.routes.dependencies import (
    ANSWER_SERVICE_UNAVAILABLE_DETAIL, EMBEDDING_SERVICE_UNAVAILABLE_DETAIL,
    get_answer_provider, get_embedding_provider)
from backend.app.schemas.rag import RAGAnswerRequest, RAGAnswerResponse
from backend.app.security.authentication import get_current_user
from backend.app.services.rag import RAGPromptInjectionDetectedError, answer_query_for_owner
from backend.app.services.security_events import record_prompt_injection_block


RAG_QUERY_REJECTED_DETAIL = "Query rejected by security policy"
RAG_ANSWER_REFUSED_DETAIL = "Unable to answer this query"


router = APIRouter(
    prefix="/rag",
    tags=["rag"]
)


@router.post(
    "/answer",
    response_model=RAGAnswerResponse
)
def answer_rag_query(
    request: RAGAnswerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    database_session: Annotated[Session, Depends(get_db)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    answer_provider: Annotated[AnswerProvider, Depends(get_answer_provider)]
) -> RAGAnswerResponse:
    
    settings = get_settings()

    try:
        return answer_query_for_owner(
            database_session,
            current_user.id,
            request.query,
            embedding_provider=embedding_provider,
            answer_provider=answer_provider,
            top_k=settings.rag_answer_top_k,
            max_context_characters=settings.rag_max_context_characters,
            prompt_injection_block_threshold=settings.prompt_injection_block_threshold
        )
    except RAGPromptInjectionDetectedError as exc:
        record_prompt_injection_block(
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            surface="rag_query",
            result=exc.result
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=RAG_QUERY_REJECTED_DETAIL
        ) from exc
    except AnswerRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=RAG_ANSWER_REFUSED_DETAIL
        ) from exc
    except EmbeddingGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=EMBEDDING_SERVICE_UNAVAILABLE_DETAIL
        ) from exc
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ANSWER_SERVICE_UNAVAILABLE_DETAIL,
        ) from exc