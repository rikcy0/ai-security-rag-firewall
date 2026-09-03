import json
import re
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from typing import Iterable, Literal, Self

from pydantic import (
    BaseModel, ConfigDict, Field, ValidationError,
    field_validator, model_validator)

from backend.app.security.prompt_injection import PromptInjectionCategory, PromptInjectionDecision


CORPUS_SCHEMA_VERSION = 1

_CASE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class AdversarialLabel(str, Enum):
    MALICIOUS = "malicious"
    BENIGN = "benign"


# regression: protects behavior the firewall already guarantees (will fail CI)
# evaluation: measure uncertain ehavior or known limitations 
class AdversarialMode(str, Enum):
    REGRESSION = "regression"
    EVALUATION = "evaluation"


class CorpusLoadError(ValueError):
    """Raised when an adversarial corpus file is invalid."""


# represents one attack or beign input
class AdversarialCase(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    id: str = Field(
        min_length=1,
        max_length=100,
        pattern=_CASE_ID_PATTERN,
    )
    text: str = Field(min_length=1)
    label: AdversarialLabel
    mode: AdversarialMode
    attack_categories: tuple[PromptInjectionCategory, ...] = ()
    expected_decision: PromptInjectionDecision | None = None
    required_detected_categories: tuple[PromptInjectionCategory, ...] = ()
    tags: tuple[str, ...] = Field(min_length=1)
    notes: str = Field(default="", max_length=500)

    @field_validator("text")
    @classmethod
    def validate_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Adversarial case text must not be blank")

        # Do not strip or otherwise normalize this value. Whitespace and
        # invisible Unicode characters may be part of the attack technique.
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Adversarial case tags must be unique")

        for tag in value:
            if tag != tag.strip() or not _TAG_PATTERN.fullmatch(tag):
                raise ValueError(
                    "Adversarial case tags must contain only lowercase "
                    "letters, numbers, underscores, and hyphens"
                )

        return value

    @model_validator(mode="after")
    def validate_case_semantics(self) -> Self:
        if len(self.attack_categories) != len(set(self.attack_categories)):
            raise ValueError("Attack categories must be unique")

        if len(self.required_detected_categories) != len(set(self.required_detected_categories)):
            raise ValueError("Required detected categories must be unique")

        attack_categories = set(self.attack_categories)
        required_categories = set(self.required_detected_categories)

        if self.label is AdversarialLabel.MALICIOUS:
            if not attack_categories:
                raise ValueError("Malicious cases must declare attack categories")
        elif attack_categories:
            raise ValueError("Benign cases must not declare attack categories")

        if not required_categories.issubset(attack_categories):
            raise ValueError("Required detected categories must be a subset of attack categories")

        if self.mode is AdversarialMode.EVALUATION:
            if self.expected_decision is not None:
                raise ValueError("Evaluation cases must not require a decision")

            if required_categories:
                raise ValueError("Evaluation cases must not require detected categories")

            return self

        expected_decision = (
            PromptInjectionDecision.BLOCK
            if self.label is AdversarialLabel.MALICIOUS
            else PromptInjectionDecision.ALLOW
        )

        if self.expected_decision is None:
            raise ValueError(
                "Regression cases must declare an expected decision"
            )

        if self.expected_decision is not expected_decision:
            raise ValueError("Regression decision contradicts the case label")

        if (self.label is AdversarialLabel.MALICIOUS and not required_categories):
            raise ValueError("Malicious regression cases must require at least one detected category")

        return self


# represents one entire JSON file
class AdversarialCorpus(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    schema_version: Literal[1]
    cases: tuple[AdversarialCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> Self:
        case_ids = [case.id for case in self.cases]

        if len(case_ids) != len(set(case_ids)):
            raise ValueError(
                "Adversarial case IDs must be unique"
            )

        return self


def _format_validation_error(corpus_path: Path, validation_error: ValidationError) -> str:
    first_error = validation_error.errors(
        include_url=False,
        include_input=False,
    )[0]

    location = ".".join(
        str(part)
        for part in first_error["loc"]
    ) or "<root>"

    return (
        f"Invalid adversarial corpus file {corpus_path}: "
        f"{location}: {first_error['msg']}"
    )


def load_corpus(path: str | Path) -> AdversarialCorpus:
    corpus_path = Path(path)

    try:
        serialized_corpus = corpus_path.read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError) as exc:
        raise CorpusLoadError(
            f"Could not read adversarial corpus file: {corpus_path}"
        ) from exc

    try:
        corpus_data = json.loads(serialized_corpus)
    except JSONDecodeError as exc:
        raise CorpusLoadError(
            "Invalid JSON in adversarial corpus file "
            f"{corpus_path} at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc

    try:
        return AdversarialCorpus.model_validate(corpus_data)
    except ValidationError as exc:
        raise CorpusLoadError(
            _format_validation_error(corpus_path, exc)
        ) from exc


def load_corpora(paths: Iterable[str | Path]) -> AdversarialCorpus:
    corpora = tuple(load_corpus(path) for path in paths)

    if not corpora:
        raise CorpusLoadError("At least one adversarial corpus file is required")

    combined_cases = tuple(
        case
        for corpus in corpora
        for case in corpus.cases
    )

    case_ids: set[str] = set()

    for case in combined_cases:
        if case.id in case_ids:
            raise CorpusLoadError(
                f"Duplicate adversarial case ID: {case.id}"
            )

        case_ids.add(case.id)

    return AdversarialCorpus(
        schema_version=CORPUS_SCHEMA_VERSION, cases=combined_cases)