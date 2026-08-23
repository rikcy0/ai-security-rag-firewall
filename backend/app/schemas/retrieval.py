from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.app.rag.constants import (
    DEFAULT_RETRIEVAL_TOP_K,
    MAX_RETRIEVAL_QUERY_CHARACTERS,
    MAX_RETRIEVAL_TOP_K
)


# Describes the JSON body clients must send to semantic-search endpoint
class SemanticSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid") # deny extra request fields

    query: str = Field(
        min_length=1,
        max_length=MAX_RETRIEVAL_QUERY_CHARACTERS
    )
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        ge=1,
        le=MAX_RETRIEVAL_TOP_K
    )

    @field_validator("query", mode="before") # run before normal pydantic validation
    @classmethod
    def normalize_query(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


# Describes one retrieved result sent to the client
class RetrievedChunkResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        allow_inf_nan=False
    )

    chunk_id: UUID
    document_id: UUID
    filename: str = Field(
        min_length=1,
        max_length=255
    )
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    similarity: float 


class SemanticSearchResponse(BaseModel):
    results: list[RetrievedChunkResponse]


# Note:
# similarity = 1.0 - cosine_distance
#       higher similarity means more similar
#       smaller cosine_distance means more similar
# 1.0 similarity means vector points in the same direction
# 0.0 means they are orthogonal
# negative values mean they point in opposing directions