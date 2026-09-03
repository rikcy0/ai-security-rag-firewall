from dataclasses import dataclass
from typing import Iterable

from backend.app.security.prompt_injection import PromptInjectionDecision, PromptInjectionResult
from backend.tests.adversarial.corpus import AdversarialCase, AdversarialLabel


@dataclass(frozen=True, slots=True)
class EvaluatedCase:
    case: AdversarialCase
    result: PromptInjectionResult


@dataclass(frozen=True, slots=True)
class DetectorMetrics:
    total_cases: int
    total_malicious: int
    total_benign: int

    true_positives: int
    false_negatives: int
    true_negatives: int
    false_positives: int

    malicious_recall: float | None
    false_negative_rate: float | None
    benign_specificity: float | None
    false_positive_rate: float | None

    bypassed_malicious_case_ids: tuple[str, ...]
    blocked_benign_case_ids: tuple[str, ...]


def _calculate_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None

    return numerator / denominator


def calculate_detector_metrics(evaluations: Iterable[EvaluatedCase]) -> DetectorMetrics:
    evaluated_cases = tuple(evaluations)

    case_ids = [
        evaluation.case.id
        for evaluation in evaluated_cases
    ]

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Detector evaluations must have unique case IDs")

    true_positives = tuple(
        evaluation
        for evaluation in evaluated_cases
        if (
            evaluation.case.label is AdversarialLabel.MALICIOUS
            and 
            evaluation.result.decision is PromptInjectionDecision.BLOCK
        )
    )

    false_negatives = tuple(
        evaluation
        for evaluation in evaluated_cases
        if (
            evaluation.case.label is AdversarialLabel.MALICIOUS
            and 
            evaluation.result.decision is PromptInjectionDecision.ALLOW
        )
    )

    true_negatives = tuple(
        evaluation
        for evaluation in evaluated_cases
        if (
            evaluation.case.label is AdversarialLabel.BENIGN
            and 
            evaluation.result.decision is PromptInjectionDecision.ALLOW
        )
    )

    false_positives = tuple(
        evaluation
        for evaluation in evaluated_cases
        if (
            evaluation.case.label is AdversarialLabel.BENIGN
            and 
            evaluation.result.decision is PromptInjectionDecision.BLOCK
        )
    )

    total_malicious = (len(true_positives) + len(false_negatives))
    total_benign = (len(true_negatives) + len(false_positives))

    return DetectorMetrics(
        total_cases=len(evaluated_cases),
        total_malicious=total_malicious,
        total_benign=total_benign,
        true_positives=len(true_positives),
        false_negatives=len(false_negatives),
        true_negatives=len(true_negatives),
        false_positives=len(false_positives),
        malicious_recall=_calculate_rate(
            len(true_positives),
            total_malicious,
        ),
        false_negative_rate=_calculate_rate(
            len(false_negatives),
            total_malicious,
        ),
        benign_specificity=_calculate_rate(
            len(true_negatives),
            total_benign,
        ),
        false_positive_rate=_calculate_rate(
            len(false_positives),
            total_benign,
        ),
        bypassed_malicious_case_ids=tuple(
            evaluation.case.id
            for evaluation in false_negatives
        ),
        blocked_benign_case_ids=tuple(
            evaluation.case.id
            for evaluation in false_positives
        ),
    )