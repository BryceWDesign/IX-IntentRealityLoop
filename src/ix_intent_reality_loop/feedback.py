"""Reality feedback frame.

Reality feedback is where the loop stops treating prediction as enough. A
bounded action decision must be compared against observed text, simulated world,
haptic, proximity, thermal, or safety-state feedback before memory or completion
can be considered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.action import BoundedActionDecision
from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)


class FeedbackModality(StrEnum):
    """Feedback channel for bounded agency-loop observations."""

    TEXT_REVIEW = "text_review"
    SIMULATED_WORLD = "simulated_world"
    HAPTIC = "haptic"
    PROXIMITY = "proximity"
    THERMAL = "thermal"
    SAFETY_STATE = "safety_state"


class FeedbackOutcome(StrEnum):
    """Outcome of comparing bounded action prediction to feedback."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    CONTRADICTED = "contradicted"
    BLOCKED = "blocked"
    NO_ACTION = "no_action"


@dataclass(frozen=True, slots=True)
class RealityFeedbackSignal:
    """One observed feedback signal from a bounded evaluation path."""

    code: str
    modality: FeedbackModality
    expected_value: str
    observed_value: str
    message: str
    confidence: BoundedScore
    contradicts_prediction: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_non_empty_text(self.code, "code"))
        object.__setattr__(
            self,
            "expected_value",
            require_non_empty_text(self.expected_value, "expected_value"),
        )
        object.__setattr__(
            self,
            "observed_value",
            require_non_empty_text(self.observed_value, "observed_value"),
        )
        object.__setattr__(
            self,
            "message",
            require_non_empty_text(self.message, "message"),
        )


@dataclass(frozen=True, slots=True)
class RealityFeedbackFrame:
    """Feedback frame comparing prediction against observed outcome."""

    frame_id: str
    intent_id: str
    action_id: str
    outcome: FeedbackOutcome
    observed_summary: str
    confidence: BoundedScore
    doctrine_rule_codes: tuple[str, ...]
    signals: tuple[RealityFeedbackSignal, ...]
    predicted_outcome: str
    preserved_action_limits: tuple[str, ...]
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "frame_id",
            require_non_empty_text(self.frame_id, "frame_id"),
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
            "observed_summary",
            require_non_empty_text(self.observed_summary, "observed_summary"),
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
            "predicted_outcome",
            require_non_empty_text(self.predicted_outcome, "predicted_outcome"),
        )
        object.__setattr__(
            self,
            "preserved_action_limits",
            tuple(
                require_non_empty_text(limit, "preserved_action_limit")
                for limit in self.preserved_action_limits
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def has_contradiction(self) -> bool:
        """Return whether any feedback signal contradicts prediction."""

        return any(signal.contradicts_prediction for signal in self.signals)

    @property
    def can_enter_outcome_delta(self) -> bool:
        """Return whether feedback can be compared by the outcome-delta engine."""

        return self.outcome in {
            FeedbackOutcome.CONFIRMED,
            FeedbackOutcome.PARTIAL,
            FeedbackOutcome.CONTRADICTED,
        }


def _average_signal_confidence(
    signals: tuple[RealityFeedbackSignal, ...],
) -> BoundedScore:
    """Return average confidence across feedback signals."""

    if not signals:
        return BoundedScore(0.0)
    total = sum(signal.confidence.value for signal in signals)
    return BoundedScore(total / len(signals))


def build_reality_feedback_frame(
    *,
    frame_id: str,
    action_decision: BoundedActionDecision,
    observed_summary: str,
    signals: tuple[RealityFeedbackSignal, ...],
) -> RealityFeedbackFrame:
    """Build a feedback frame from a bounded action decision and observations."""

    doctrine_rule_codes = (
        "reality_gets_vote",
        "completion_not_output",
        "evidence_before_claim",
    )

    if action_decision.blocks_action:
        return RealityFeedbackFrame(
            frame_id=frame_id,
            intent_id=action_decision.intent_id,
            action_id=action_decision.action_id,
            outcome=FeedbackOutcome.NO_ACTION,
            observed_summary="No action feedback: bounded action decision blocked.",
            confidence=BoundedScore(0.0),
            doctrine_rule_codes=doctrine_rule_codes,
            signals=signals,
            predicted_outcome=action_decision.predicted_outcome,
            preserved_action_limits=action_decision.execution_limits,
        )

    if not signals:
        raise ValueError("signals must not be empty for feedback-eligible actions")

    signal_confidence = _average_signal_confidence(signals)
    confidence = BoundedScore(
        min(action_decision.confidence.value, signal_confidence.value)
    )

    if any(signal.contradicts_prediction for signal in signals):
        outcome = FeedbackOutcome.CONTRADICTED
    elif all(signal.confidence.is_at_least(0.75) for signal in signals):
        outcome = FeedbackOutcome.CONFIRMED
    else:
        outcome = FeedbackOutcome.PARTIAL

    return RealityFeedbackFrame(
        frame_id=frame_id,
        intent_id=action_decision.intent_id,
        action_id=action_decision.action_id,
        outcome=outcome,
        observed_summary=observed_summary,
        confidence=confidence,
        doctrine_rule_codes=doctrine_rule_codes,
        signals=signals,
        predicted_outcome=action_decision.predicted_outcome,
        preserved_action_limits=action_decision.execution_limits,
    )


def validate_reality_feedback_frame(
    frame: RealityFeedbackFrame,
) -> tuple[ValidationFinding, ...]:
    """Validate feedback before prediction-vs-outcome delta scoring."""

    findings: list[ValidationFinding] = []

    if "reality_gets_vote" not in frame.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "feedback_missing_reality_doctrine",
                "Feedback frame must cite reality_gets_vote doctrine.",
            )
        )

    if "completion_not_output" not in frame.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "feedback_missing_completion_doctrine",
                "Feedback frame must not treat observation as completion.",
            )
        )

    if frame.outcome is FeedbackOutcome.CONTRADICTED and not frame.has_contradiction:
        findings.append(
            blocker_finding(
                "feedback_contradiction_without_signal",
                "Contradicted feedback outcome requires a contradictory signal.",
            )
        )

    if frame.outcome is FeedbackOutcome.CONFIRMED and frame.has_contradiction:
        findings.append(
            blocker_finding(
                "feedback_confirmed_despite_contradiction",
                "Confirmed feedback cannot contain contradictory signals.",
            )
        )

    if frame.outcome is not FeedbackOutcome.NO_ACTION and not frame.signals:
        findings.append(
            blocker_finding(
                "feedback_missing_observation_signals",
                "Action feedback must preserve observation signals.",
            )
        )

    if frame.can_enter_outcome_delta and "no live physical actuation" not in (
        frame.preserved_action_limits
    ):
        findings.append(
            blocker_finding(
                "feedback_missing_no_live_actuation_limit",
                "Feedback-eligible frame must preserve no-live-actuation limit.",
            )
        )

    if frame.outcome is FeedbackOutcome.PARTIAL:
        findings.append(
            warning_finding(
                "feedback_partial_observation",
                "Feedback only partially confirms the predicted outcome.",
            )
        )

    if frame.outcome is FeedbackOutcome.CONTRADICTED:
        findings.append(
            warning_finding(
                "feedback_prediction_contradicted",
                "Feedback contradicts the predicted outcome.",
            )
        )

    if frame.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "feedback_confidence_below_target",
                "Feedback confidence is below the target threshold.",
            )
        )

    return tuple(findings)
