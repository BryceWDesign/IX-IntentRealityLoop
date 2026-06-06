"""Core doctrine for IX-IntentRealityLoop.

The doctrine is intentionally executable. These rules are not branding text;
they are boundaries that later runtime, evidence, replay, and handoff layers can
reference without relying on README claims.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class DoctrineSeverity(StrEnum):
    """Severity level for a doctrine rule."""

    PRINCIPLE = "principle"
    INVARIANT = "invariant"
    PROHIBITION = "prohibition"


@dataclass(frozen=True, slots=True)
class DoctrineRule:
    """A doctrine rule that can be cited by runtime decisions and evidence."""

    code: str
    statement: str
    severity: DoctrineSeverity
    rationale: str


DOCTRINE_RULES: Final[tuple[DoctrineRule, ...]] = (
    DoctrineRule(
        code="thought_not_action",
        statement="Thought is not action.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "A generated plan, interpretation, or internal preference cannot be "
            "treated as execution, authorization, or completion."
        ),
    ),
    DoctrineRule(
        code="intent_not_permission",
        statement="Intent is not permission.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "An inferred, decoded, predicted, or user-supplied intent must pass "
            "explicit permission, safety, and authority checks before action."
        ),
    ),
    DoctrineRule(
        code="interpretation_not_truth",
        statement="Interpretation is not truth.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "The system must preserve uncertainty when translating a request into "
            "a likely goal, especially when literal and interpreted readings differ."
        ),
    ),
    DoctrineRule(
        code="completion_not_output",
        statement="Completion is not output.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "A task is not complete merely because the system produced an answer. "
            "Completion requires outcome assessment, authority preservation, and "
            "evidence capture."
        ),
    ),
    DoctrineRule(
        code="surpass_first_pass_not_user_authority",
        statement="Surpass the first-pass solution, never the user's authority.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "Bounded self-surpass pressure may improve quality only inside the "
            "user's constraints, truth boundaries, safety gates, and evidence limits."
        ),
    ),
    DoctrineRule(
        code="reality_gets_vote",
        statement="Reality gets a vote.",
        severity=DoctrineSeverity.PRINCIPLE,
        rationale=(
            "Predicted outcomes must be compared with feedback, and contradictions "
            "must downgrade confidence or trigger quarantine rather than being hidden."
        ),
    ),
    DoctrineRule(
        code="evidence_before_claim",
        statement="Evidence comes before capability claims.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "Runtime results must be traceable to replayable records before they are "
            "used as support for readiness, transfer, or capability claims."
        ),
    ),
    DoctrineRule(
        code="human_authority_persists",
        statement="Human authority persists.",
        severity=DoctrineSeverity.INVARIANT,
        rationale=(
            "The system may recommend, defer, refuse, or escalate, but it must not "
            "grant itself final approval authority."
        ),
    ),
    DoctrineRule(
        code="no_agi_overclaim",
        statement="No AGI overclaim.",
        severity=DoctrineSeverity.PROHIBITION,
        rationale=(
            "IX-IntentRealityLoop is an evaluation runtime for agency grounding. It "
            "must not represent itself as AGI, certified AGI, independently validated "
            "AGI, consciousness, or production-ready autonomy."
        ),
    ),
)

REQUIRED_RULE_CODES: Final[frozenset[str]] = frozenset(
    rule.code for rule in DOCTRINE_RULES
)

PROHIBITED_CLAIM_FRAGMENTS: Final[tuple[str, ...]] = (
    "certified agi",
    "independently validated agi",
    "proven agi",
    "true agi achieved",
    "conscious ai",
    "self-authorizing autonomy",
    "production-ready autonomy",
    "approved for live physical actuation",
    "robotics-certified",
    "bci-certified",
    "medical-certified",
)


def doctrine_catalog() -> tuple[DoctrineRule, ...]:
    """Return the immutable doctrine catalog."""

    return DOCTRINE_RULES


def doctrine_index() -> Mapping[str, DoctrineRule]:
    """Return doctrine rules keyed by rule code."""

    return MappingProxyType({rule.code: rule for rule in DOCTRINE_RULES})


def missing_required_rules(rule_codes: set[str]) -> frozenset[str]:
    """Return required doctrine codes not present in a supplied rule-code set."""

    return REQUIRED_RULE_CODES.difference(rule_codes)


def find_prohibited_claims(text: str) -> tuple[str, ...]:
    """Find prohibited capability-claim fragments in text.

    Matching is intentionally case-insensitive and fragment-based because this
    function is meant to catch obvious overclaims in evidence summaries, handoff
    packets, and public-facing text.
    """

    lowered_text = text.lower()
    return tuple(
        fragment for fragment in PROHIBITED_CLAIM_FRAGMENTS if fragment in lowered_text
    )


def assert_no_prohibited_claims(text: str) -> None:
    """Raise ValueError when text contains prohibited capability claims."""

    prohibited_claims = find_prohibited_claims(text)
    if prohibited_claims:
        joined_claims = ", ".join(prohibited_claims)
        raise ValueError(f"prohibited capability claim(s): {joined_claims}")
