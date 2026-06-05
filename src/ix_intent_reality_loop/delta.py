"""Prediction-vs-outcome delta engine.

The delta engine scores the gap between what the bounded action predicted and
what reality feedback reported. It is deliberately conservative: contradiction,
partial feedback, and no-action outcomes remain visible for memory quarantine,
evidence replay, and Kernel Wave 6 donor packets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.feedback import FeedbackOutcome, RealityFeedbackFrame


class OutcomeDeltaStatus(StrEnum):
    """Status assigned after comparing prediction against feedback."""

    MATCHED = "matched"
    DEGRADED = "degraded"
    CONTRADICTED = "contradicted"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class OutcomeDelta:
    """Structured prediction-vs-outcome comparison."""

    delta_id: str
    intent_id: str
    action_id: str
    feedback_frame_id: str
    status: OutcomeDeltaStatus
    predicted_outcome: str
    observed_outcome: str
    match_score: BoundedScore
    confidence: BoundedScore
    doctrine_rule_codes: tuple[str, ...]
    contradiction_reasons: tuple[str, ...] = ()
    required_next_steps: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "delta_id",
            require_non_empty_text(self.delta_id, "delta_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "action_id",
            require_non_empty_text(self.action_id, "action_id"),
        )
        object.__setattr__(
            self,
            "feedback_frame_id",
            require_non_empty_text(self.feedback_frame_id, "feedback_frame_id"),
        )
        object.__setattr__(
            self,
            "predicted_outcome",
            require_non_empty_text(self.predicted_outcome, "predicted_outcome"),
        )
        object.__setattr__(
            self,
            "observed_outcome",
            require_non_empty_text(self.observed_outcome, "observed_outcome"),
        )
        object.__setattr__(
            self,
            "doctrine_rule_codes",
            tuple(
                require_non_empty_text(code, "doctrine_rule_code")
                for code in self.doctrine_rule_codes
            ),
        )
        object.__setattr__(
            self,
            "contradiction_reasons",
            tuple(
                require_non_empty_text(reason, "contradiction_reason")
                for reason in self.contradiction_reasons
            ),
        )
        object.__setattr__(
            self,
            "required_next_steps",
            tuple(
                require_non_empty_text(step, "required_next_step")
                for step in self.required_next_steps
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def supports_memory_update(self) -> bool:
        """Return whether the delta supports positive memory update."""

        return self.status is OutcomeDeltaStatus.MATCHED and self.match_score.is_at_least(
            0.75
        )

    @property
    def requires_quarantine(self) -> bool:
        """Return whether the delta must pressure memory quarantine."""

        return self.status in {
            OutcomeDeltaStatus.CONTRADICTED,
            OutcomeDeltaStatus.BLOCKED,
        }


def _contradiction_reasons_from_frame(
    frame: RealityFeedbackFrame,
) -> tuple[str, ...]:
    """Return contradiction reasons derived from feedback signals."""

    return tuple(
        f"{signal.code}: expected {signal.expected_value}, observed "
        f"{signal.observed_value}"
        for signal in frame.signals
        if signal.contradicts_prediction
    )


def build_outcome_delta(
    *,
    delta_id: str,
    feedback_frame: RealityFeedbackFrame,
) -> OutcomeDelta:
    """Build an outcome delta from a feedback frame."""

    doctrine_rule_codes = (
        "reality_gets_vote",
        "evidence_before_claim",
        "completion_not_output",
    )

    if feedback_frame.outcome is FeedbackOutcome.NO_ACTION:
        return OutcomeDelta(
            delta_id=delta_id,
            intent_id=feedback_frame.intent_id,
            action_id=feedback_frame.action_id,
            feedback_frame_id=feedback_frame.frame_id,
            status=OutcomeDeltaStatus.BLOCKED,
            predicted_outcome=feedback_frame.predicted_outcome,
            observed_outcome=feedback_frame.observed_summary,
            match_score=BoundedScore(0.0),
            confidence=BoundedScore(0.0),
            doctrine_rule_codes=doctrine_rule_codes,
            required_next_steps=("preserve no-action state and avoid memory promotion",),
        )

    if feedback_frame.outcome is FeedbackOutcome.CONTRADICTED:
        return OutcomeDelta(
            delta_id=delta_id,
            intent_id=feedback_frame.intent_id,
            action_id=feedback_frame.action_id,
            feedback_frame_id=feedback_frame.frame_id,
            status=OutcomeDeltaStatus.CONTRADICTED,
            predicted_outcome=feedback_frame.predicted_outcome,
            observed_outcome=feedback_frame.observed_summary,
            match_score=BoundedScore(0.0),
            confidence=feedback_frame.confidence,
            doctrine_rule_codes=doctrine_rule_codes,
            contradiction_reasons=_contradiction_reasons_from_frame(feedback_frame),
            required_next_steps=(
                "downgrade confidence and send contradiction to memory quarantine",
            ),
        )

    if feedback_frame.outcome is FeedbackOutcome.PARTIAL:
        return OutcomeDelta(
            delta_id=delta_id,
            intent_id=feedback_frame.intent_id,
            action_id=feedback_frame.action_id,
            feedback_frame_id=feedback_frame.frame_id,
            status=OutcomeDeltaStatus.DEGRADED,
            predicted_outcome=feedback_frame.predicted_outcome,
            observed_outcome=feedback_frame.observed_summary,
            match_score=BoundedScore(feedback_frame.confidence.value * 0.5),
            confidence=feedback_frame.confidence,
            doctrine_rule_codes=doctrine_rule_codes,
            required_next_steps=("preserve degraded evidence before memory use",),
        )

    return OutcomeDelta(
        delta_id=delta_id,
        intent_id=feedback_frame.intent_id,
        action_id=feedback_frame.action_id,
        feedback_frame_id=feedback_frame.frame_id,
        status=OutcomeDeltaStatus.MATCHED,
        predicted_outcome=feedback_frame.predicted_outcome,
        observed_outcome=feedback_frame.observed_summary,
        match_score=feedback_frame.confidence,
        confidence=feedback_frame.confidence,
        doctrine_rule_codes=doctrine_rule_codes,
        required_next_steps=("eligible for bounded memory update review",),
    )


def validate_outcome_delta(delta: OutcomeDelta) -> tuple[ValidationFinding, ...]:
    """Validate outcome delta before memory binding."""

    findings: list[ValidationFinding] = []

    if "reality_gets_vote" not in delta.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "delta_missing_reality_doctrine",
                "Outcome delta must cite reality_gets_vote doctrine.",
            )
        )

    if "evidence_before_claim" not in delta.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "delta_missing_evidence_doctrine",
                "Outcome delta must cite evidence_before_claim doctrine.",
            )
        )

    if "completion_not_output" not in delta.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "delta_missing_completion_doctrine",
                "Outcome delta must not treat outcome comparison as completion.",
            )
        )

    if delta.status is OutcomeDeltaStatus.CONTRADICTED and not (
        delta.contradiction_reasons
    ):
        findings.append(
            blocker_finding(
                "delta_contradiction_missing_reasons",
                "Contradicted outcome delta requires contradiction reasons.",
            )
        )

    if delta.status is OutcomeDeltaStatus.MATCHED and delta.match_score.is_below(0.75):
        findings.append(
            blocker_finding(
                "delta_matched_score_below_memory_threshold",
                "Matched outcome delta must meet memory-update threshold.",
            )
        )

    if delta.status is OutcomeDeltaStatus.BLOCKED and delta.match_score.value != 0.0:
        findings.append(
            blocker_finding(
                "delta_blocked_has_nonzero_match_score",
                "Blocked outcome delta must preserve zero match score.",
            )
        )

    if delta.status is OutcomeDeltaStatus.DEGRADED:
        findings.append(
            warning_finding(
                "delta_degraded_outcome",
                "Outcome delta is degraded and should not promote memory directly.",
            )
        )

    if delta.requires_quarantine:
        findings.append(
            warning_finding(
                "delta_requires_quarantine",
                "Outcome delta requires memory quarantine pressure.",
            )
        )

    if delta.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "delta_confidence_below_target",
                "Outcome delta confidence is below the target threshold.",
            )
        )

    return tuple(findings)
