from pathlib import Path

from backend.app.security.prompt_injection import PromptInjectionCategory
from backend.tests.adversarial.constants import DETECTOR_EVALUATION_THRESHOLD
from backend.tests.adversarial.corpus import AdversarialMode, load_corpora
from backend.tests.adversarial.evaluator import evaluate_cases
from backend.tests.adversarial.metrics import DetectorMetrics, EvaluatedCase, calculate_detector_metrics


CASES_DIRECTORY = Path(__file__).parent / "cases"

CORPUS_PATHS = (
    CASES_DIRECTORY / "malicious_prompts.json",
    CASES_DIRECTORY / "benign_prompts.json",
)


def _format_rate(rate: float | None) -> str:
    if rate is None:
        return "N/A"
    return f"{rate:.2%}"


def _print_metric_summary(title: str, metrics: DetectorMetrics) -> None:
    print()
    print(title)
    print(f"  Total cases: {metrics.total_cases}")
    print(
        "  Malicious blocked: "
        f"{metrics.true_positives}/{metrics.total_malicious}"
    )
    print(
        "  Malicious recall: "
        f"{_format_rate(metrics.malicious_recall)}"
    )
    print(
        "  False-negative rate: "
        f"{_format_rate(metrics.false_negative_rate)}"
    )
    print(
        "  Benign allowed: "
        f"{metrics.true_negatives}/{metrics.total_benign}"
    )
    print(
        "  Benign specificity: "
        f"{_format_rate(metrics.benign_specificity)}"
    )
    print(
        "  False-positive rate: "
        f"{_format_rate(metrics.false_positive_rate)}"
    )


def _print_case_ids(title: str, case_ids: tuple[str, ...]) -> None:
    print()
    print(title)

    if not case_ids:
        print(" None")
        return

    for case_id in case_ids:
        print(f"  - {case_id}")


def _print_category_metrics(evaluations: tuple[EvaluatedCase, ...]) -> None:
    print()
    print("Malicious recall by attack category")

    for category in PromptInjectionCategory:
        category_evaluations = tuple(
            evaluation
            for evaluation in evaluations
            if category in evaluation.case.attack_categories
        )

        metrics = calculate_detector_metrics(category_evaluations)

        print(
            f"  {category.value}: "
            f"{metrics.true_positives}/"
            f"{metrics.total_malicious} blocked, "
            f"recall={_format_rate(metrics.malicious_recall)}"
        )


def _print_tag_metrics(evaluations: tuple[EvaluatedCase, ...]) -> None:
    tags = sorted(
        {
            tag
            for evaluation in evaluations
            for tag in evaluation.case.tags
        }
    )

    print()
    print("Results by tag")

    for tag in tags:
        tag_evaluations = tuple(
            evaluation
            for evaluation in evaluations
            if tag in evaluation.case.tags
        )

        metrics = calculate_detector_metrics(tag_evaluations)

        print(
            f"  {tag}: "
            f"cases={metrics.total_cases}, "
            "malicious_recall="
            f"{_format_rate(metrics.malicious_recall)}, "
            "benign_specificity="
            f"{_format_rate(metrics.benign_specificity)}"
        )


def main() -> None:
    corpus = load_corpora(CORPUS_PATHS)

    evaluations = evaluate_cases(
        corpus.cases,
        block_threshold=DETECTOR_EVALUATION_THRESHOLD
    )

    regression_evaluations = tuple(
        evaluation
        for evaluation in evaluations
        if evaluation.case.mode
        is AdversarialMode.REGRESSION
    )

    exploratory_evaluations = tuple(
        evaluation
        for evaluation in evaluations
        if evaluation.case.mode
        is AdversarialMode.EVALUATION
    )

    overall_metrics = calculate_detector_metrics(evaluations)
    regression_metrics = calculate_detector_metrics(regression_evaluations)
    exploratory_metrics = calculate_detector_metrics(exploratory_evaluations)

    print("Adversarial prompt-injection evaluation")
    print(f"Corpus schema version: {corpus.schema_version}")
    print(
        "Detector threshold: "
        f"{DETECTOR_EVALUATION_THRESHOLD}"
    )

    _print_metric_summary(
        "Overall corpus",
        overall_metrics,
    )
    _print_metric_summary(
        "Regression cases",
        regression_metrics,
    )
    _print_metric_summary(
        "Evaluation cases",
        exploratory_metrics,
    )

    _print_case_ids(
        "Bypassed malicious cases",
        overall_metrics.bypassed_malicious_case_ids,
    )
    _print_case_ids(
        "Blocked benign cases",
        overall_metrics.blocked_benign_case_ids,
    )

    _print_category_metrics(evaluations)
    _print_tag_metrics(evaluations)


if __name__ == "__main__":
    main()