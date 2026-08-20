from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.rag.constants import (
    MAX_RAG_ANSWER_CHARACTERS,
    MAX_RETRIEVAL_QUERY_CHARACTERS,
    MAX_RETRIEVAL_TOP_K
)


RAG_INSUFFICIENT_CONTEXT_ANSWER = (
    "I could not find information in your documents to answer that question."
)

RAGAnswerStatus = Literal["answered", "insufficient_context"]


class RAGAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=MAX_RETRIEVAL_QUERY_CHARACTERS
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        # check raw input length before trimming so a huge whitespace-padded
        # request cannot bypass request-size boundary
        if len(value) > MAX_RETRIEVAL_QUERY_CHARACTERS:
            raise ValueError("RAG query exceeds the maximum length")

        return value.replace("\r\n", "\n").replace("\r", "\n").strip()


# A single response schema for a source 
class RAGSourceResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        allow_inf_nan=False,
        extra="forbid"
    )

    source_number: int = Field(
        ge=1,
        le=MAX_RETRIEVAL_TOP_K
    )
    chunk_id: UUID
    document_id: UUID
    filename: str = Field(
        min_length=1,
        max_length=255
    )
    chunk_index: int = Field(ge=0)
    similarity: float


# One RAG response schema that has one or more Source responses
class RAGAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RAGAnswerStatus
    answer: str = Field(
        min_length=1,
        max_length=MAX_RAG_ANSWER_CHARACTERS
    )
    sources: list[RAGSourceResponse] = Field(
        max_length=MAX_RETRIEVAL_TOP_K
    )

    @field_validator("answer")
    @classmethod
    def validate_answer_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("RAG answer must not be blank")
        return value
    
    @model_validator(mode="after")
    def validate_answer_contract(self) -> "RAGAnswerResponse":
        if self.status == "answered" and not self.sources:
            raise ValueError("Answered responses must contain at least one source")

        if self.status == "insufficient_context":
            if self.answer != RAG_INSUFFICIENT_CONTEXT_ANSWER:
                raise ValueError("Insufficient-context responses must use the canonical fallback answer")

            if self.sources:
                raise ValueError("Insufficient-context responses must not contain sources")

        source_numbers = [source.source_number for source in self.sources]
        if len(source_numbers) != len(set(source_numbers)):
            raise ValueError("RAG response source numbers must be unique")
        if source_numbers != sorted(source_numbers):
            raise ValueError("RAG response sources must be ordered by source number")

        return self