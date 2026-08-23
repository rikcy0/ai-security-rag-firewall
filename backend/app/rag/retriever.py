from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models import Document, DocumentChunk
from backend.app.rag.embeddings import EmbeddingGenerationError, EmbeddingProvider
from backend.app.rag.constants import MAX_RETRIEVAL_QUERY_CHARACTERS, MAX_RETRIEVAL_TOP_K


# instances are immutable after construction
@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    similarity: float


def retrieve_chunks_for_owner(
    database_session: Session,
    owner_id: UUID,
    query: str,
    *,
    embedding_provider: EmbeddingProvider,
    top_k: int
) -> list[RetrievedChunk]:
    
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Retrieval query must not be empty")
    if len(normalized_query) > MAX_RETRIEVAL_QUERY_CHARACTERS:
        raise ValueError("Retrieval query exceeds the maximum length")

    if not 1 <= top_k <= MAX_RETRIEVAL_TOP_K:
        raise ValueError(f"Retrieval top_k must be between 1 and {MAX_RETRIEVAL_TOP_K}")

    # embed the query string (should have one item in the resulting list)
    embeddings = embedding_provider.embed_texts([normalized_query])
    if len(embeddings) != 1:
        raise EmbeddingGenerationError("Embedding provider returned an unexpected result count")

    query_embedding = embeddings[0]
    cosine_distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    cosine_similarity = (1.0 - cosine_distance).label("similarity") # new SQL column name 

    statement = (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id,
            Document.filename,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            cosine_similarity
        ).join(
            Document, Document.id == DocumentChunk.document_id,
        ).where(
            Document.owner_id == owner_id
        ).order_by(
            cosine_distance
        ).limit(top_k)
    )
    database_session.execute(   # only affects the current transaction
        text("SET LOCAL hnsw.iterative_scan = 'strict_order'")
    )

    rows = database_session.execute(statement).all()

    return [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            filename=row.filename,
            chunk_index=row.chunk_index,
            content=row.content,
            similarity=float(row.similarity)
        )
        for row in rows
    ]