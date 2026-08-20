import re
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.rag.constants import MAX_RAG_ANSWER_CHARACTERS, MAX_RETRIEVAL_TOP_K


INLINE_CITATION_PATTERN = re.compile(r"\[([0-9]+)\]")
CANONICAL_CITATION_PATTERN = re.compile(r"[1-9][0-9]*")


GeneratedAnswerStatus = Literal["answered", "insufficient_context"]

CitationNumber = Annotated[
    int,
    Field(ge=1, le=MAX_RETRIEVAL_TOP_K),
]


class AnswerGenerationError(RuntimeError):
    """Base exception for answer-generation failures."""


class AnswerProviderUnavailableError(AnswerGenerationError):
    """Raised when the external answer provider is unavailable."""


class AnswerResponseInvalidError(AnswerGenerationError):
    """Raised when the provider returns an unusable response."""


class AnswerRefusedError(AnswerGenerationError):
    """Raised when the model refuses to answer."""


@dataclass(frozen=True, slots=True)
class AnswerContext:
    """
    Minimal retrieved context sent to the answer provider.

    Database IDs, filenames, similarity values, ownership information,
    and embeddings deliberately remain outside this object.
    """

    source_number: int
    content: str

    def __post_init__(self) -> None:
        if not 1 <= self.source_number <= MAX_RETRIEVAL_TOP_K:
            raise ValueError("Answer context source number is outside the allowed range")
        if not self.content.strip():
            raise ValueError("Answer context content must not be empty")


class GeneratedAnswer(BaseModel):
    """
    Structured result returned by an answer provider.

    This is internal provider output, not the public HTTP response.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True
    )

    status: GeneratedAnswerStatus
    answer: str = Field(
        max_length=MAX_RAG_ANSWER_CHARACTERS
    )
    cited_source_numbers: list[CitationNumber] = Field(
        max_length=MAX_RETRIEVAL_TOP_K
    )

    @model_validator(mode="after")
    def validate_status_contract(self) -> "GeneratedAnswer":
        if len(self.cited_source_numbers) != len(set(self.cited_source_numbers)):
            raise ValueError("Generated citation numbers must be unique")
        
        if self.status == "answered":
            if not self.answer:
                raise ValueError("Generated answered result must contain an answer")
            if not self.cited_source_numbers:
                raise ValueError("Generated answered result must contain citations")

        if self.status == "insufficient_context":
            if self.answer:
                raise ValueError("Generated insufficient-context result must have an empty answer")
            if self.cited_source_numbers:
                raise ValueError("Generated insufficient-context result must not contain citations")

        return self


class AnswerProvider(Protocol):
    """Application-facing interface for answer generation"""

    def generate_answer(
        self, 
        query: str, 
        contexts: list[AnswerContext]
    ) -> GeneratedAnswer:
        """Generate a structured answer from supplied contexts."""


def validate_generated_answer(
    generated_answer: GeneratedAnswer,
    contexts: list[AnswerContext]
) -> GeneratedAnswer:
    """Verify model-controlled citations against server-owned contexts."""

    if not contexts:
        raise ValueError("Answer contexts must not be empty")

    context_source_numbers = [context.source_number for context in contexts]
    if len(context_source_numbers) != len(set(context_source_numbers)):
        raise ValueError("Answer context source numbers must be unique")

    allowed_source_numbers = set(context_source_numbers)
    cited_source_numbers = set(generated_answer.cited_source_numbers)
    if not cited_source_numbers.issubset(allowed_source_numbers):
        raise AnswerResponseInvalidError("Generated answer cited an unavailable source")

    # will reject [0] and [01] instead of silently ignoring them
    raw_inline_citations = INLINE_CITATION_PATTERN.findall(generated_answer.answer)
    if any(
        CANONICAL_CITATION_PATTERN.fullmatch(citation) is None
        for citation in raw_inline_citations
    ):
        raise AnswerResponseInvalidError("Generated answer contains an invalid citation format")

    inline_source_numbers = {
        int(match) for match in INLINE_CITATION_PATTERN.findall(generated_answer.answer)
    }
    if inline_source_numbers != cited_source_numbers:
        raise AnswerResponseInvalidError(
            "Generated answer citations do not match the declared citation list"
        )

    return generated_answer