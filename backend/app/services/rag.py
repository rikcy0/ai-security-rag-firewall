from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.rag.constants import MAX_RETRIEVAL_QUERY_CHARACTERS
from backend.app.rag.embeddings import EmbeddingProvider
from backend.app.rag.generator import AnswerContext, AnswerProvider, validate_generated_answer
from backend.app.rag.retriever import RetrievedChunk, retrieve_chunks_for_owner
from backend.app.schemas.rag import RAG_INSUFFICIENT_CONTEXT_ANSWER, RAGAnswerResponse, RAGSourceResponse
from backend.app.security.prompt_injection import PromptInjectionDecision, PromptInjectionResult, analyze_prompt_injection


class RAGPromptInjectionDetectedError(Exception):
    """Raised when a RAG query violates prompt-injection policy."""

    def __init__(self, result: PromptInjectionResult) -> None:
        self.result = result

        super().__init__("Query rejected by prompt-injection policy")


@dataclass(frozen=True, slots=True)
class PreparedAnswerSource:
    """
    Connect model-visible context to server-owned retrieval metadata.

    Only answer_context is sent to the generation provider.
    retrieved_chunk remains under server control for response metadata.
    """

    answer_context: AnswerContext
    retrieved_chunk: RetrievedChunk


def prepare_answer_sources(
    retrieved_chunks: list[RetrievedChunk],
    *,
    max_context_characters: int) -> list[PreparedAnswerSource]:
    """
    Select whole retrieved chunks within the answer-time context budget.

    Source numbers are assigned only after the final context selection.
    """

    if max_context_characters <= 0:
        raise ValueError("Maximum context characters must be greater than zero")

    prepared_sources: list[PreparedAnswerSource] = []
    used_characters = 0

    for retrieved_chunk in retrieved_chunks:
        if not retrieved_chunk.content.strip():
            continue

        chunk_characters = len(retrieved_chunk.content)
        remaining_characters = (max_context_characters - used_characters)

        if chunk_characters > remaining_characters:
            continue

        source_number = len(prepared_sources) + 1

        prepared_sources.append(
            PreparedAnswerSource(
                answer_context=AnswerContext(
                    source_number=source_number,
                    content=retrieved_chunk.content
                ),
                retrieved_chunk=retrieved_chunk
            )
        )

        used_characters += chunk_characters

    return prepared_sources


# ensures both no-retrieval and model-declared insufficiency produces same public response
def _build_insufficient_context_response() -> RAGAnswerResponse:
    return RAGAnswerResponse(
        status="insufficient_context",
        answer=RAG_INSUFFICIENT_CONTEXT_ANSWER,
        sources=[]
    )


def answer_query_for_owner(
    database_session: Session,
    owner_id: UUID,
    query: str,
    *,
    embedding_provider: EmbeddingProvider,
    answer_provider: AnswerProvider,
    top_k: int,
    max_context_characters: int,
    prompt_injection_block_threshold: int) -> RAGAnswerResponse:
    """
    Run the guarded owner-scoped retrieval and answer workflow.
    """

    if len(query) > MAX_RETRIEVAL_QUERY_CHARACTERS:
        raise ValueError("RAG query exceeds the maximum length")

    normalized_query = query.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_query:
        raise ValueError("RAG query must not be empty")

    injection_result = analyze_prompt_injection(
        normalized_query,
        block_threshold=prompt_injection_block_threshold
    )
    if injection_result.decision is PromptInjectionDecision.BLOCK:
        raise RAGPromptInjectionDetectedError(injection_result)

    retrieved_chunks = retrieve_chunks_for_owner(
        database_session,
        owner_id,
        normalized_query,
        embedding_provider=embedding_provider,
        top_k=top_k
    )

    # cleanly end the read transaction used by the retriever 
    # before making the answer-provider call
    # also prevents database transaction from remaining open during external network call
    # Thus answer_query_for_owner() expects a session with no pending writes needed to be preserved
    database_session.rollback()

    prepared_sources = prepare_answer_sources(
        retrieved_chunks,
        max_context_characters=max_context_characters
    )
    if not prepared_sources:
        return _build_insufficient_context_response()

    answer_contexts = [ps.answer_context for ps in prepared_sources]

    generated_answer = answer_provider.generate_answer(
        normalized_query,
        answer_contexts
    )
    # Enforce citation rules regardless of the provider implementation
    generated_answer = validate_generated_answer(
        generated_answer,
        answer_contexts,
    )
    if generated_answer.status == "insufficient_context":
        return _build_insufficient_context_response()

    # construct mapping (Ex: 1: chunk A, 2: chunk B, 3: chunk D, etc.)
    source_by_number = {
        ps.answer_context.source_number: ps.retrieved_chunk for ps in prepared_sources
    }
    cited_sources = [
        RAGSourceResponse(
            source_number=src_num,
            chunk_id=source_by_number[src_num].chunk_id,
            document_id=source_by_number[src_num].document_id,
            filename=source_by_number[src_num].filename,
            chunk_index=source_by_number[src_num].chunk_index,
            similarity=source_by_number[src_num].similarity
        )
        for src_num in sorted(generated_answer.cited_source_numbers)
    ]

    return RAGAnswerResponse(
        status="answered",
        answer=generated_answer.answer,
        sources=cited_sources
    )

    