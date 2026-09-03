from collections.abc import Iterable

from backend.app.security.prompt_injection import analyze_prompt_injection
from backend.tests.adversarial.corpus import AdversarialCase
from backend.tests.adversarial.metrics import EvaluatedCase


def evaluate_cases(
    cases: Iterable[AdversarialCase],
    *,
    block_threshold: int
) -> tuple[EvaluatedCase, ...]:
    
    if not 1 <= block_threshold <= 100:
        raise ValueError("block_threshold must be between 1 and 100")

    return tuple(
        EvaluatedCase(
            case=case,
            result=analyze_prompt_injection(
                case.text, block_threshold=block_threshold
            )
        )
        for case in cases
    )