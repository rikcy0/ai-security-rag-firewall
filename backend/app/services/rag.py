from dataclasses import dataclass

from backend.app.rag.generator import AnswerContext
from backend.app.rag.retriever import RetrievedChunk


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
    max_context_characters: int
) -> list[PreparedAnswerSource]:
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