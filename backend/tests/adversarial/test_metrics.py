from dataclasses import FrozenInstanceError

import pytest

from backend.app.security.prompt_injection import (
    PromptInjectionCategory,
    PromptInjectionDecision,
    PromptInjectionResult,
)
from backend.tests.adversarial.corpus import (
    AdversarialCase,
    AdversarialLabel,
)
from backend.tests.adversarial.metrics import (
    DetectorMetrics,
    EvaluatedCase,
    calculate_detector_metrics,
)


def make_evaluation(
    case_id: str,
    *,
    label: AdversarialLabel,
    decision: PromptInjectionDecision,
) -> EvaluatedCase:
    is_malicious = (
        label is AdversarialLabel.MALICIOUS
    )
    is_blocked = (
        decision is PromptInjectionDecision.BLOCK
    )

    case = AdversarialCase(
        id=case_id,
        text=f"Evaluation text for {case_id}",
        label=label,
        mode="evaluation",
        attack_categories=(
            [PromptInjectionCategory.INSTRUCTION_OVERRIDE]
            if is_malicious
            else []
        ),
        expected_decision=None,
        required_detected_categories=[],
        tags=["metrics-test"],
    )

    result = PromptInjectionResult(
        decision=decision,
        risk_score=70 if is_blocked else 0,
        matched_categories=(
            (PromptInjectionCategory.INSTRUCTION_OVERRIDE,)
            if is_blocked
            else ()
        ),
        reasons=(
            ("instruction override attempt",)
            if is_blocked
            else ()
        ),
    )

    return EvaluatedCase(
        case=case,
        result=result,
    )


def test_metrics_calculate_all_four_outcomes() -> None:
    metrics = calculate_detector_metrics(
        [
            make_evaluation(
                "malicious-blocked",
                label=AdversarialLabel.MALICIOUS,
                decision=PromptInjectionDecision.BLOCK,
            ),
            make_evaluation(
                "malicious-allowed",
                label=AdversarialLabel.MALICIOUS,
                decision=PromptInjectionDecision.ALLOW,
            ),
            make_evaluation(
                "benign-allowed",
                label=AdversarialLabel.BENIGN,
                decision=PromptInjectionDecision.ALLOW,
            ),
            make_evaluation(
                "benign-blocked",
                label=AdversarialLabel.BENIGN,
                decision=PromptInjectionDecision.BLOCK,
            ),
        ]
    )

    assert metrics.total_cases == 4
    assert metrics.total_malicious == 2
    assert metrics.total_benign == 2

    assert metrics.true_positives == 1
    assert metrics.false_negatives == 1
    assert metrics.true_negatives == 1
    assert metrics.false_positives == 1

    assert metrics.malicious_recall == pytest.approx(0.5)
    assert metrics.false_negative_rate == pytest.approx(0.5)
    assert metrics.benign_specificity == pytest.approx(0.5)
    assert metrics.false_positive_rate == pytest.approx(0.5)

    assert metrics.bypassed_malicious_case_ids == (
        "malicious-allowed",
    )
    assert metrics.blocked_benign_case_ids == (
        "benign-blocked",
    )


def test_empty_evaluation_has_unavailable_rates() -> None:
    metrics = calculate_detector_metrics([])

    assert metrics.total_cases == 0
    assert metrics.total_malicious == 0
    assert metrics.total_benign == 0
    assert metrics.malicious_recall is None
    assert metrics.false_negative_rate is None
    assert metrics.benign_specificity is None
    assert metrics.false_positive_rate is None
    assert metrics.bypassed_malicious_case_ids == ()
    assert metrics.blocked_benign_case_ids == ()


def test_malicious_only_evaluation_has_no_benign_rates() -> None:
    metrics = calculate_detector_metrics(
        [
            make_evaluation(
                "malicious-blocked",
                label=AdversarialLabel.MALICIOUS,
                decision=PromptInjectionDecision.BLOCK,
            )
        ]
    )

    assert metrics.malicious_recall == pytest.approx(1.0)
    assert metrics.false_negative_rate == pytest.approx(0.0)
    assert metrics.benign_specificity is None
    assert metrics.false_positive_rate is None


def test_benign_only_evaluation_has_no_malicious_rates() -> None:
    metrics = calculate_detector_metrics(
        [
            make_evaluation(
                "benign-allowed",
                label=AdversarialLabel.BENIGN,
                decision=PromptInjectionDecision.ALLOW,
            )
        ]
    )

    assert metrics.malicious_recall is None
    assert metrics.false_negative_rate is None
    assert metrics.benign_specificity == pytest.approx(1.0)
    assert metrics.false_positive_rate == pytest.approx(0.0)


def test_metrics_reject_duplicate_case_ids() -> None:
    evaluation = make_evaluation(
        "duplicate-case",
        label=AdversarialLabel.MALICIOUS,
        decision=PromptInjectionDecision.BLOCK,
    )

    with pytest.raises(
        ValueError,
        match="unique case IDs",
    ):
        calculate_detector_metrics(
            [evaluation, evaluation]
        )


def test_metrics_are_immutable() -> None:
    metrics = calculate_detector_metrics([])

    with pytest.raises(FrozenInstanceError):
        metrics.total_cases = 10