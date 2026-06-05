from datetime import UTC, datetime

from ix_intent_reality_loop.action import (
    ActionMode,
    BoundedActionDecision,
    plan_bounded_action,
    validate_bounded_action_decision,
)
from ix_intent_reality_loop.core import (
    BoundedScore,
    DecisionDisposition,
    ValidationSeverity,
)
from ix_intent_reality_loop.safety import (
    InteractionState,
    SafetyGateResult,
    SafetyLevel,
)


def _safety_result(
    *,
    interaction_state: InteractionState = InteractionState.SIMULATED_ACTION,
    disposition: DecisionDisposition = DecisionDisposition.ALLOW,
    confidence: float = 0.9,
) -> SafetyGateResult:
    return SafetyGateResult(
        gate_id="safety-001",
        intent_id="intent-001",
        permission_gate_id="permission-001",
        safety_map_id="safety-map-001",
        safety_level=SafetyLevel.GREEN,
        disposition=disposition,
        interaction_state=interaction_state,
        confidence=BoundedScore(confidence),
        rationale="Safety gate accepted evaluation path.",
        doctrine_rule_codes=("reality_gets_vote", "completion_not_output"),
        preserved_signal_codes=("workspace_clear",),
        required_next_steps=("send to bounded action planner",),
    )


def test_plan_bounded_action_maps_text_output_to_text_response() -> None:
    decision = plan_bounded_action(
        action_id="action-001",
        safety_result=_safety_result(interaction_state=InteractionState.TEXT_ONLY),
        selected_action="Produce bounded text response.",
        predicted_outcome="A text response is produced for review.",
    )

    assert decision.mode is ActionMode.TEXT_RESPONSE
    assert decision.disposition is DecisionDisposition.ALLOW
    assert decision.can_enter_feedback_loop


def test_plan_bounded_action_maps_simulated_action_to_simulated_step() -> None:
    decision = plan_bounded_action(
        action_id="action-002",
        safety_result=_safety_result(
            interaction_state=InteractionState.SIMULATED_ACTION,
        ),
        selected_action="Simulate moving the object.",
        predicted_outcome="Simulation records movement without actuation.",
    )

    assert decision.mode is ActionMode.SIMULATED_STEP
    assert decision.can_enter_feedback_loop
    assert "no live physical actuation" in decision.execution_limits


def test_plan_bounded_action_maps_contact_review_to_non_actuating_review() -> None:
    decision = plan_bounded_action(
        action_id="action-003",
        safety_result=_safety_result(
            interaction_state=InteractionState.BOUNDED_CONTACT_REVIEW,
        ),
        selected_action="Review possible bounded contact path.",
        predicted_outcome="Contact review remains descriptive only.",
    )

    assert decision.mode is ActionMode.BOUNDED_CONTACT_REVIEW
    assert "bounded contact review is descriptive and non-actuating" in (
        decision.execution_limits
    )


def test_plan_bounded_action_clamps_verify_state() -> None:
    decision = plan_bounded_action(
        action_id="action-004",
        safety_result=_safety_result(
            interaction_state=InteractionState.VERIFY,
            disposition=DecisionDisposition.CLAMP,
            confidence=0.75,
        ),
        selected_action="Verify yellow signal before any simulation.",
        predicted_outcome="Verification prevents unsafe escalation.",
    )

    assert decision.mode is ActionMode.VERIFY_ONLY
    assert decision.disposition is DecisionDisposition.CLAMP
    assert decision.can_enter_feedback_loop


def test_plan_bounded_action_safe_holds_blocked_safety_result() -> None:
    decision = plan_bounded_action(
        action_id="action-005",
        safety_result=_safety_result(
            interaction_state=InteractionState.EMERGENCY_RETREAT,
            disposition=DecisionDisposition.SAFE_HOLD,
            confidence=0.0,
        ),
        selected_action="This should be replaced.",
        predicted_outcome="This should be replaced.",
    )
    findings = validate_bounded_action_decision(decision)

    assert decision.mode is ActionMode.RETREAT
    assert decision.disposition is DecisionDisposition.SAFE_HOLD
    assert decision.blocks_action
    assert decision.selected_action == "No action: hold bounded agency loop."
    assert any(
        finding.severity is ValidationSeverity.WARNING for finding in findings
    )


def test_bounded_action_decision_rejects_empty_action_text() -> None:
    try:
        BoundedActionDecision(
            action_id="action-006",
            intent_id="intent-001",
            safety_gate_id="safety-001",
            mode=ActionMode.TEXT_RESPONSE,
            disposition=DecisionDisposition.ALLOW,
            selected_action=" ",
            predicted_outcome="Output is reviewed.",
            confidence=BoundedScore(0.9),
            doctrine_rule_codes=("completion_not_output",),
            preserved_safety_signals=("workspace_clear",),
        )
    except ValueError as exc:
        assert "selected_action must not be empty" in str(exc)
    else:
        raise AssertionError("expected empty selected_action ValueError")


def test_bounded_action_decision_rejects_naive_timestamp() -> None:
    try:
        BoundedActionDecision(
            action_id="action-007",
            intent_id="intent-001",
            safety_gate_id="safety-001",
            mode=ActionMode.TEXT_RESPONSE,
            disposition=DecisionDisposition.ALLOW,
            selected_action="Respond with bounded text.",
            predicted_outcome="Output is reviewed.",
            confidence=BoundedScore(0.9),
            doctrine_rule_codes=("completion_not_output",),
            preserved_safety_signals=("workspace_clear",),
            created_at=datetime(2026, 1, 1),
        )
    except ValueError as exc:
        assert "created_at must be timezone-aware" in str(exc)
    else:
        raise AssertionError("expected naive timestamp ValueError")


def test_validate_bounded_action_decision_blocks_invalid_allow() -> None:
    decision = BoundedActionDecision(
        action_id="action-008",
        intent_id="intent-001",
        safety_gate_id="safety-001",
        mode=ActionMode.SIMULATED_STEP,
        disposition=DecisionDisposition.ALLOW,
        selected_action="Simulate action.",
        predicted_outcome="Simulation occurs.",
        confidence=BoundedScore(0.9),
        doctrine_rule_codes=(),
        preserved_safety_signals=(),
        execution_limits=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_bounded_action_decision(decision)
    finding_codes = {finding.code for finding in findings}

    assert "action_missing_thought_doctrine" in finding_codes
    assert "action_missing_completion_doctrine" in finding_codes
    assert "action_missing_authority_doctrine" in finding_codes
    assert "action_missing_safety_signal_evidence" in finding_codes
    assert "action_missing_no_live_actuation_limit" in finding_codes
