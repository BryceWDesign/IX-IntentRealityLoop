from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import BoundedScore, ValidationSeverity
from ix_intent_reality_loop.delta import (
    OutcomeDelta,
    OutcomeDeltaStatus,
    build_outcome_delta,
    validate_outcome_delta,
)
from ix_intent_reality_loop.feedback import (
    FeedbackModality,
    FeedbackOutcome,
    RealityFeedbackFrame,
    RealityFeedbackSignal,
)


def _signal(
    *,
    confidence: float = 0.9,
    contradicts_prediction: bool = False,
) -> RealityFeedbackSignal:
    return RealityFeedbackSignal(
        code="simulated_position",
        modality=FeedbackModality.SIMULATED_WORLD,
        expected_value="inside_bounds",
        observed_value="outside_bounds" if contradicts_prediction else "inside_bounds",
        message="Simulated position feedback.",
        confidence=BoundedScore(confidence),
        contradicts_prediction=contradicts_prediction,
    )


def _frame(
    *,
    outcome: FeedbackOutcome,
    confidence: float = 0.9,
    signals: tuple[RealityFeedbackSignal, ...] | None = None,
) -> RealityFeedbackFrame:
    return RealityFeedbackFrame(
        frame_id="feedback-001",
        intent_id="intent-001",
        action_id="action-001",
        outcome=outcome,
        observed_summary="Observed bounded result.",
        confidence=BoundedScore(confidence),
        doctrine_rule_codes=(
            "reality_gets_vote",
            "completion_not_output",
            "evidence_before_claim",
        ),
        signals=() if signals is None else signals,
        predicted_outcome="Predicted bounded result.",
        preserved_action_limits=("no live physical actuation",),
    )


def test_build_outcome_delta_marks_confirmed_feedback_as_matched() -> None:
    delta = build_outcome_delta(
        delta_id="delta-001",
        feedback_frame=_frame(
            outcome=FeedbackOutcome.CONFIRMED,
            signals=(_signal(),),
        ),
    )

    assert delta.status is OutcomeDeltaStatus.MATCHED
    assert delta.match_score.value == 0.9
    assert delta.supports_memory_update
    assert not delta.requires_quarantine


def test_build_outcome_delta_marks_partial_feedback_as_degraded() -> None:
    delta = build_outcome_delta(
        delta_id="delta-002",
        feedback_frame=_frame(
            outcome=FeedbackOutcome.PARTIAL,
            confidence=0.6,
            signals=(_signal(confidence=0.6),),
        ),
    )
    findings = validate_outcome_delta(delta)
    finding_codes = {finding.code for finding in findings}

    assert delta.status is OutcomeDeltaStatus.DEGRADED
    assert delta.match_score.value == 0.3
    assert not delta.supports_memory_update
    assert "delta_degraded_outcome" in finding_codes


def test_build_outcome_delta_marks_contradiction_and_preserves_reasons() -> None:
    delta = build_outcome_delta(
        delta_id="delta-003",
        feedback_frame=_frame(
            outcome=FeedbackOutcome.CONTRADICTED,
            signals=(_signal(contradicts_prediction=True),),
        ),
    )
    findings = validate_outcome_delta(delta)
    finding_codes = {finding.code for finding in findings}

    assert delta.status is OutcomeDeltaStatus.CONTRADICTED
    assert delta.match_score.value == 0.0
    assert delta.requires_quarantine
    assert delta.contradiction_reasons == (
        "simulated_position: expected inside_bounds, observed outside_bounds",
    )
    assert "delta_requires_quarantine" in finding_codes


def test_build_outcome_delta_marks_no_action_as_blocked() -> None:
    delta = build_outcome_delta(
        delta_id="delta-004",
        feedback_frame=_frame(outcome=FeedbackOutcome.NO_ACTION),
    )
    findings = validate_outcome_delta(delta)
    finding_codes = {finding.code for finding in findings}

    assert delta.status is OutcomeDeltaStatus.BLOCKED
    assert delta.match_score.value == 0.0
    assert delta.requires_quarantine
    assert "delta_requires_quarantine" in finding_codes
    assert "delta_confidence_below_target" in finding_codes


def test_outcome_delta_rejects_empty_observed_outcome() -> None:
    with pytest.raises(ValueError, match="observed_outcome must not be empty"):
        OutcomeDelta(
            delta_id="delta-005",
            intent_id="intent-001",
            action_id="action-001",
            feedback_frame_id="feedback-001",
            status=OutcomeDeltaStatus.MATCHED,
            predicted_outcome="Prediction.",
            observed_outcome=" ",
            match_score=BoundedScore(0.9),
            confidence=BoundedScore(0.9),
            doctrine_rule_codes=("reality_gets_vote",),
        )


def test_outcome_delta_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        OutcomeDelta(
            delta_id="delta-006",
            intent_id="intent-001",
            action_id="action-001",
            feedback_frame_id="feedback-001",
            status=OutcomeDeltaStatus.MATCHED,
            predicted_outcome="Prediction.",
            observed_outcome="Observation.",
            match_score=BoundedScore(0.9),
            confidence=BoundedScore(0.9),
            doctrine_rule_codes=("reality_gets_vote",),
            created_at=datetime(2026, 1, 1),
        )


def test_validate_outcome_delta_blocks_invalid_matched_delta() -> None:
    delta = OutcomeDelta(
        delta_id="delta-007",
        intent_id="intent-001",
        action_id="action-001",
        feedback_frame_id="feedback-001",
        status=OutcomeDeltaStatus.MATCHED,
        predicted_outcome="Prediction.",
        observed_outcome="Observation.",
        match_score=BoundedScore(0.5),
        confidence=BoundedScore(0.9),
        doctrine_rule_codes=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_outcome_delta(delta)
    finding_codes = {finding.code for finding in findings}

    assert "delta_missing_reality_doctrine" in finding_codes
    assert "delta_missing_evidence_doctrine" in finding_codes
    assert "delta_missing_completion_doctrine" in finding_codes
    assert "delta_matched_score_below_memory_threshold" in finding_codes
    assert any(finding.severity is ValidationSeverity.BLOCKER for finding in findings)


def test_validate_outcome_delta_blocks_contradiction_without_reasons() -> None:
    delta = OutcomeDelta(
        delta_id="delta-008",
        intent_id="intent-001",
        action_id="action-001",
        feedback_frame_id="feedback-001",
        status=OutcomeDeltaStatus.CONTRADICTED,
        predicted_outcome="Prediction.",
        observed_outcome="Observation.",
        match_score=BoundedScore(0.0),
        confidence=BoundedScore(0.9),
        doctrine_rule_codes=(
            "reality_gets_vote",
            "evidence_before_claim",
            "completion_not_output",
        ),
        contradiction_reasons=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_outcome_delta(delta)
    finding_codes = {finding.code for finding in findings}

    assert "delta_contradiction_missing_reasons" in finding_codes
