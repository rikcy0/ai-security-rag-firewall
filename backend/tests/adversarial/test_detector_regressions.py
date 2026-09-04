from pathlib import Path

import pytest

from backend.app.security.prompt_injection import PromptInjectionCategory, PromptInjectionDecision, analyze_prompt_injection
from backend.tests.adversarial.constants import DETECTOR_EVALUATION_THRESHOLD
from backend.tests.adversarial.corpus import (
    AdversarialCase,
    AdversarialLabel,
    AdversarialMode,
    load_corpus,
    load_corpora,
)


CASES_DIRECTORY = Path(__file__).parent / "cases"

MALICIOUS_CORPUS = load_corpus(CASES_DIRECTORY / "malicious_prompts.json")

BENIGN_CORPUS = load_corpus(CASES_DIRECTORY / "benign_prompts.json")

ADVERSARIAL_CORPUS = load_corpora(
    [
        CASES_DIRECTORY / "malicious_prompts.json",
        CASES_DIRECTORY / "benign_prompts.json",
    ]
)

REGRESSION_CASES = tuple(
    case
    for case in ADVERSARIAL_CORPUS.cases
    if case.mode is AdversarialMode.REGRESSION
)

EVALUATION_CASES = tuple(
    case
    for case in ADVERSARIAL_CORPUS.cases
    if case.mode is AdversarialMode.EVALUATION
)


def test_malicious_corpus_contains_only_malicious_cases() -> None:
    assert all(
        case.label is AdversarialLabel.MALICIOUS
        for case in MALICIOUS_CORPUS.cases
    )


def test_benign_corpus_contains_only_benign_cases() -> None:
    assert all(
        case.label is AdversarialLabel.BENIGN
        for case in BENIGN_CORPUS.cases
    )


def test_malicious_corpus_covers_every_detector_category() -> None:
    represented_categories = {
        category
        for case in MALICIOUS_CORPUS.cases
        for category in case.attack_categories
    }

    assert represented_categories == set(PromptInjectionCategory)


def test_combined_corpus_contains_both_modes() -> None:
    assert REGRESSION_CASES
    assert EVALUATION_CASES


def test_evaluation_cases_have_no_required_outcome() -> None:
    assert all(
        case.expected_decision is None
        and not case.required_detected_categories
        for case in EVALUATION_CASES
    )


@pytest.mark.parametrize(
    "case",
    REGRESSION_CASES,
    ids=lambda case: case.id,
)
def test_detector_regression_case(case: AdversarialCase) -> None:
    result = analyze_prompt_injection(
        case.text,
        block_threshold=DETECTOR_EVALUATION_THRESHOLD,
    )

    assert case.expected_decision is not None
    assert result.decision is case.expected_decision

    if case.expected_decision is PromptInjectionDecision.BLOCK:
        assert result.risk_score >= DETECTOR_EVALUATION_THRESHOLD
    else:
        assert result.risk_score < DETECTOR_EVALUATION_THRESHOLD

    assert set(case.required_detected_categories).issubset(result.matched_categories)