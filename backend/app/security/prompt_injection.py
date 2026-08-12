from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

class PromptInjectionDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


class PromptInjectionCategory(str, Enum):
    INSTRUCTION_OVERRIDE = "instruction_override"
    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"
    ROLE_MANIPULATION = "role_manipulation"
    SECURITY_BYPASS = "security_bypass"
    DATA_EXFILTRATION = "data_exfiltration" 


@dataclass(frozen=True, slots=True)
class PromptInjectionResult:
    decision: PromptInjectionDecision
    risk_score: int
    matched_categories: tuple[PromptInjectionCategory, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DetectionRule:
    category: PromptInjectionCategory
    reason: str
    weight: int
    patterns: tuple[re.Pattern[str], ...]


_DETECTION_RULES = (
    _DetectionRule(
        category=PromptInjectionCategory.INSTRUCTION_OVERRIDE,
        reason="instruction override attempt",
        weight=70,
        patterns=(
            re.compile(
                r"\b(?:ignore|disregard|forget)\b"
                r".{0,80}"
                r"\b(?:previous|prior|above|system|developer)\b"
                r".{0,40}"
                r"\b(?:instructions?|rules?|prompt)\b"
            ),
            re.compile(
                r"\bfollow\b"
                r".{0,40}"
                r"\b(?:these|my|new)\b"
                r".{0,30}"
                r"\binstructions?\b"
                r".{0,30}"
                r"\binstead\b"
            )
        )
    ),
    _DetectionRule(
        category=PromptInjectionCategory.SYSTEM_PROMPT_EXTRACTION,
        reason="system prompt extraction attempt",
        weight=70,
        patterns=(
            re.compile(
                r"\b(?:reveal|show|print|repeat|output|display|provide|tell)\b"
                r".{0,80}"
                r"\b(?:system prompt|developer message|hidden instructions?|"
                r"initial instructions?)\b"
            ),
            re.compile(
                r"\bwhat (?:is|are|were)\b"
                r".{0,50}"
                r"\b(?:system prompt|developer instructions?|"
                r"hidden instructions?)\b"
            )
        )
    ),
    _DetectionRule(
        category=PromptInjectionCategory.ROLE_MANIPULATION,
        reason="unauthorized role manipulation attempt",
        weight=60,
        patterns=(
            re.compile(
                r"\byou are now\b"
                r".{0,50}"
                r"\b(?:developer mode|unrestricted mode|dan)\b"
            ),
            re.compile(
                r"\bact as (?:if|though)\b"
                r".{0,60}"
                r"\b(?:no restrictions?|no rules?|unrestricted)\b"
            )
        )
    ),
    _DetectionRule(
        category=PromptInjectionCategory.SECURITY_BYPASS,
        reason="security control bypass attempt",
        weight=60,
        patterns=(
            re.compile(
                r"\b(?:bypass|disable|evade|remove|override)\b"
                r".{0,60}"
                r"\b(?:safety|security|guardrails?|filters?|"
                r"restrictions?|polic(?:y|ies))\b"
            ),
        )
    ),
    _DetectionRule(
        category=PromptInjectionCategory.DATA_EXFILTRATION,
        reason="sensitive data extraction attempt",
        weight=70,
        patterns=(
            re.compile(
                r"\b(?:reveal|show|print|output|send|expose|leak)\b"
                r".{0,80}"
                r"\b(?:api keys?|passwords?|secrets?|credentials?|"
                r"private data|other users?'? data)\b"
            ),
        )
    )
)


def _normalize_text_variants(text: str) -> tuple[str, ...]:
    normalized_text = unicodedata.normalize("NFKC", text).casefold()

    format_characters_removed = "".join(
        character
        for character in normalized_text
        if unicodedata.category(character) != "Cf"
    )

    format_characters_as_spaces = "".join(
        (
            " "
            if unicodedata.category(character) == "Cf"
            else character
        )
        for character in normalized_text
    )

    removed_variant = " ".join(format_characters_removed.split())

    boundary_variant = " ".join(format_characters_as_spaces.split())

    if removed_variant == boundary_variant:
        return (removed_variant,)

    return (removed_variant, boundary_variant)


def normalize_text_for_detection(text: str) -> str:
    """
    Return the primary normalized representation of untrusted text.

    Detection additionally considers a boundary-preserving representation
    for invisible Unicode format characters.
    """

    return _normalize_text_variants(text)[0]


def analyze_prompt_injection(text: str, *, block_threshold: int) -> PromptInjectionResult:
    """
    Analyze untrusted text using deterministic security rules.

    Risk scores represent project-defined rule severity, not probabilities.
    With the current default policy, every defined rule is strong enough to
    block individually. Multiple categories increase the score up to 100.
    """

    if not 1 <= block_threshold <= 100:
        raise ValueError("block_threshold must be between 1 and 100")

    normalized_variants = _normalize_text_variants(text)
    matched_rules = tuple(
        rule for rule in _DETECTION_RULES if any(
            pattern.search(normalized_text) 
            for normalized_text in normalized_variants
            for pattern in rule.patterns
        )
    )

    risk_score = min(sum(rule.weight for rule in matched_rules), 100)

    decision = (
        PromptInjectionDecision.BLOCK 
        if risk_score >= block_threshold 
        else PromptInjectionDecision.ALLOW
    )

    return PromptInjectionResult(
        decision=decision,
        risk_score=risk_score,
        matched_categories=tuple(rule.category for rule in matched_rules),
        reasons=tuple(rule.reason for rule in matched_rules)
    )

