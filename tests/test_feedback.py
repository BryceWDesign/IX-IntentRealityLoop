from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.action import ActionMode, BoundedActionDecision
from ix_intent_reality_loop.core import (
    BoundedScore,
    DecisionDisposition,
    ValidationSeverity,
)
from ix_intent_reality_loop.feedback import (
    FeedbackModality,
    FeedbackOutcome,
    RealityFeedbackFrame,
    RealityFeedbackSignal,
    build_reality_feedback_frame,
    validate_reality_feedback_frame,
)


def _action_decision(
    *,
    disposition: DecisionDisposition = DecisionDisposition.ALLOW,
    confidence: float = 0.9,
) -> BoundedActionDecision:
    return BoundedActionDecision(
        action_id="action-001",
        intent_id="intent-001",
        safety_gate_id="safety-001",
        mode=ActionMode.SIMULATED_STEP,
        disposition=disposition,
        selected_action="Simulate a bounded step.",
        predicted_outcome="The simulated object remains inside safety bounds.",
        confidence=BoundedScore(confidence),
        doctrine_rule_codes=(
            "thought_not_action",
            "human_authority_persists",
            "completion_not_output",
        ),
        preserved_safety_signals=("workspace_clear",),
        required_next_steps=("send to feedback model",),
        execution_limits=(
            "evaluation runtime only",
            "no live physical actuation",
            "human authority remains final",
        ),
    )


def _signal(
    *,
    code: str = "simulated_position",
    confidence: float = 0.9,
    contradicts_prediction: bool = False,
) -> RealityFeedbackSignal:
    return RealityFeedbackSignal(
        code=code,
        modality=FeedbackModality.SIMULATED_WORLD,
        expected_value="inside_bounds",
        observed_value="outside_bounds" if contradicts_prediction else "inside_bounds",
        message="Simulated position feedback.",
        confidence=BoundedScore(confidence),
        contradicts_prediction=contradicts_prediction,
    )


def test_reality_feedback_signal_preserves_observation_data() -> None:
    signal = _signal()

    assert signal.code == "simulated_position"
    assert signal.modality is FeedbackModality.SIMULATED_WORLD
    assert not signal.contradicts_prediction


def test_reality_feedback_signal_rejects_empty_observed_value() -> None:
    with pytest.raises(ValueError, match="observed_value must not be empty"):
        RealityFeedbackSignal(
            code="thermal",
            modality=FeedbackModality.THERMAL,
            expected_value="nominal",
            observed_value=" ",
            message="Thermal feedback.",
            confidence=BoundedScore(0.8),
        )


def test_build_reality_feedback_frame_confirms_matching_high_confidence_signal() -> (
    None
):
    frame = build_reality_feedback_frame(
        frame_id="feedback-001",
        action_decision=_action_decision(),
        observed_summary="Simulation stayed inside bounds.",
        signals=(_signal(),),
    )

    assert frame.outcome is FeedbackOutcome.CONFIRMED
    assert frame.confidence.value == 0.9
    assert frame.can_enter_outcome_delta
    assert not frame.has_contradiction


def test_build_reality_feedback_frame_marks_partial_low_confidence_signal() -> None:
    frame = build_reality_feedback_frame(
        frame_id="feedback-002",
        action_decision=_action_decision(),
        observed_summary="Simulation mostly stayed inside bounds.",
        signals=(_signal(confidence=0.6),),
    )
    findings = validate_reality_feedback_frame(frame)
    finding_codes = {finding.code for finding in findings}

    assert frame.outcome is FeedbackOutcome.PARTIAL
    assert frame.confidence.value == 0.6
    assert "feedback_partial_observation" in finding_codes


def test_build_reality_feedback_frame_marks_contradiction() -> None:
    frame = build_reality_feedback_frame(
        frame_id="feedback-003",
        action_decision=_action_decision(),
        observed_summary="Simulation left expected bounds.",
        signals=(_signal(contradicts_prediction=True),),
    )
    findings = validate_reality_feedback_frame(frame)
    finding_codes = {finding.code for finding in findings}

    assert frame.outcome is FeedbackOutcome.CONTRADICTED
    assert frame.has_contradiction
    assert "feedback_prediction_contradicted" in finding_codes


def test_build_reality_feedback_frame_records_no_action_for_blocked_decision() -> None:
    frame = build_reality_feedback_frame(
        frame_id="feedback-004",
        action_decision=_action_decision(
            disposition=DecisionDisposition.SAFE_HOLD,
            confidence=0.0,
        ),
        observed_summary="This is replaced for blocked actions.",
        signals=(),
    )

    assert frame.outcome is FeedbackOutcome.NO_ACTION
    assert not frame.can_enter_outcome_delta
    assert frame.observed_summary == (
        "No action feedback: bounded action decision blocked."
    )


def test_build_reality_feedback_frame_requires_signals_for_feedback_action() -> None:
    with pytest.raises(ValueError, match="signals must not be empty"):
        build_reality_feedback_frame(
            frame_id="feedback-005",
            action_decision=_action_decision(),
            observed_summary="No signals.",
            signals=(),
        )


def test_reality_feedback_frame_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        RealityFeedbackFrame(
            frame_id="feedback-006",
            intent_id="intent-001",
            action_id="action-001",
            outcome=FeedbackOutcome.CONFIRMED,
            observed_summary="Confirmed.",
            confidence=BoundedScore(0.9),
            doctrine_rule_codes=("reality_gets_vote", "completion_not_output"),
            signals=(_signal(),),
            predicted_outcome="Prediction.",
            preserved_action_limits=("no live physical actuation",),
            created_at=datetime(2026, 1, 1),
        )


def test_validate_reality_feedback_frame_blocks_invalid_confirmed_contradiction() -> (
    None
):
    frame = RealityFeedbackFrame(
        frame_id="feedback-007",
        intent_id="intent-001",
        action_id="action-001",
        outcome=FeedbackOutcome.CONFIRMED,
        observed_summary="Invalid confirmation.",
        confidence=BoundedScore(0.9),
        doctrine_rule_codes=(),
        signals=(_signal(contradicts_prediction=True),),
        predicted_outcome="Prediction.",
        preserved_action_limits=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_reality_feedback_frame(frame)
    finding_codes = {finding.code for finding in findings}

    assert "feedback_missing_reality_doctrine" in finding_codes
    assert "feedback_missing_completion_doctrine" in finding_codes
    assert "feedback_confirmed_despite_contradiction" in finding_codes
    assert "feedback_missing_no_live_actuation_limit" in finding_codes
    assert any(finding.severity is ValidationSeverity.BLOCKER for finding in findings)
