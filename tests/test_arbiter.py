import pytest

from ix_intent_reality_loop.arbiter import (
    FourthEyeDecision,
    arbitrate_fourth_eye_decision,
    validate_fourth_eye_decision,
)
from ix_intent_reality_loop.comparison import build_lane_comparison_record
from ix_intent_reality_loop.core import (
    BoundedScore,
    DecisionDisposition,
    ValidationSeverity,
)
from ix_intent_reality_loop.lanes import (
    ExecutionLaneKind,
    ExecutionLaneResult,
    ExecutionLaneStatus,
)


def _lane(
    *,
    lane_id: str,
    kind: ExecutionLaneKind,
    confidence: float,
    objective: str | None = None,
    status: ExecutionLaneStatus = ExecutionLaneStatus.COMPLETE,
    blocked_reasons: tuple[str, ...] = (),
    constraints_preserved: tuple[str, ...] = (),
) -> ExecutionLaneResult:
    return ExecutionLaneResult(
        lane_id=lane_id,
        intent_id="intent-001",
        kind=kind,
        objective=objective if objective is not None else f"{kind.value} objective",
        proposed_output=f"{kind.value} output",
        predicted_outcome=f"{kind.value} outcome",
        confidence=BoundedScore(confidence),
        status=status,
        doctrine_rule_codes=("completion_not_output",),
        constraints_preserved=constraints_preserved,
        blocked_reasons=blocked_reasons,
    )


def test_fourth_eye_decision_preserves_authority_boundaries() -> None:
    decision = FourthEyeDecision(
        decision_id="arbiter-001",
        intent_id="intent-001",
        comparison_id="comparison-001",
        disposition=DecisionDisposition.CLAMP,
        confidence=BoundedScore(0.82),
        rationale="Clamp selected lane because divergence remains.",
        doctrine_rule_codes=("human_authority_persists", "completion_not_output"),
        selected_lane_id="lane-001",
        merged_lane_ids=("lane-001", "lane-002"),
        required_next_steps=("send to permission gate",),
    )

    assert decision.can_move_to_permission_gate
    assert not decision.blocks_action


def test_fourth_eye_decision_rejects_empty_rationale() -> None:
    with pytest.raises(ValueError, match="rationale must not be empty"):
        FourthEyeDecision(
            decision_id="arbiter-002",
            intent_id="intent-002",
            comparison_id="comparison-002",
            disposition=DecisionDisposition.ALLOW,
            confidence=BoundedScore(0.9),
            rationale=" ",
            doctrine_rule_codes=("human_authority_persists",),
        )


def test_arbitrate_escalates_when_triadic_coverage_is_missing() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.8,
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.9,
    )
    comparison = build_lane_comparison_record(
        comparison_id="comparison-003",
        lanes=(literal, interpreted),
    )

    decision = arbitrate_fourth_eye_decision(
        decision_id="arbiter-003",
        comparison=comparison,
        lanes=(literal, interpreted),
    )
    findings = validate_fourth_eye_decision(decision)

    assert decision.disposition is DecisionDisposition.ESCALATE
    assert decision.blocks_action
    assert "comparison_missing_triadic_lane" in decision.preserved_warnings
    assert any(finding.severity is ValidationSeverity.WARNING for finding in findings)


def test_arbitrate_safe_holds_when_no_viable_lane_survives() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.8,
        status=ExecutionLaneStatus.BLOCKED,
        blocked_reasons=("blocked literal",),
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.7,
        status=ExecutionLaneStatus.BLOCKED,
        blocked_reasons=("blocked interpreted",),
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.6,
        status=ExecutionLaneStatus.BLOCKED,
        blocked_reasons=("blocked self-surpass",),
    )
    comparison = build_lane_comparison_record(
        comparison_id="comparison-004",
        lanes=(literal, interpreted, self_surpass),
    )

    decision = arbitrate_fourth_eye_decision(
        decision_id="arbiter-004",
        comparison=comparison,
        lanes=(literal, interpreted, self_surpass),
    )

    assert decision.disposition is DecisionDisposition.SAFE_HOLD
    assert decision.confidence.value == 0.0
    assert decision.selected_lane_id is None


def test_arbitrate_defers_when_alignment_is_below_target() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.8,
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.7,
        status=ExecutionLaneStatus.BLOCKED,
        blocked_reasons=("blocked interpreted",),
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.6,
        status=ExecutionLaneStatus.BLOCKED,
        blocked_reasons=("blocked self-surpass",),
    )
    comparison = build_lane_comparison_record(
        comparison_id="comparison-005",
        lanes=(literal, interpreted, self_surpass),
    )

    decision = arbitrate_fourth_eye_decision(
        decision_id="arbiter-005",
        comparison=comparison,
        lanes=(literal, interpreted, self_surpass),
    )

    assert decision.disposition is DecisionDisposition.DEFER
    assert decision.selected_lane_id == "lane-literal"
    assert decision.blocks_action


def test_arbitrate_clamps_when_divergence_remains() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.72,
        objective="Move it over there.",
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.88,
        objective="Ask which object and destination are intended.",
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.81,
    )
    comparison = build_lane_comparison_record(
        comparison_id="comparison-006",
        lanes=(literal, interpreted, self_surpass),
    )

    decision = arbitrate_fourth_eye_decision(
        decision_id="arbiter-006",
        comparison=comparison,
        lanes=(literal, interpreted, self_surpass),
    )

    assert decision.disposition is DecisionDisposition.CLAMP
    assert decision.selected_lane_id == "lane-interpreted"
    assert decision.can_move_to_permission_gate
    assert "comparison_divergence_present" in decision.preserved_warnings


def test_arbitrate_allows_when_full_alignment_has_no_divergence() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.72,
        objective="Summarize the evidence.",
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.88,
        objective="Summarize the evidence.",
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.81,
        objective="Summarize the evidence.",
        constraints_preserved=("boundary-preserved",),
    )
    comparison = build_lane_comparison_record(
        comparison_id="comparison-007",
        lanes=(literal, interpreted, self_surpass),
    )

    decision = arbitrate_fourth_eye_decision(
        decision_id="arbiter-007",
        comparison=comparison,
        lanes=(literal, interpreted, self_surpass),
    )

    assert decision.disposition is DecisionDisposition.ALLOW
    assert decision.selected_lane_id == "lane-interpreted"
    assert decision.can_move_to_permission_gate


def test_arbitrate_rejects_comparison_with_missing_lane_objects() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.8,
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.9,
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.7,
    )
    comparison = build_lane_comparison_record(
        comparison_id="comparison-008",
        lanes=(literal, interpreted, self_surpass),
    )

    with pytest.raises(ValueError, match="comparison lane_ids must be present"):
        arbitrate_fourth_eye_decision(
            decision_id="arbiter-008",
            comparison=comparison,
            lanes=(literal, interpreted),
        )


def test_validate_fourth_eye_decision_blocks_missing_doctrine() -> None:
    decision = FourthEyeDecision(
        decision_id="arbiter-009",
        intent_id="intent-009",
        comparison_id="comparison-009",
        disposition=DecisionDisposition.ALLOW,
        confidence=BoundedScore(0.9),
        rationale="Select lane.",
        doctrine_rule_codes=(),
        selected_lane_id=None,
    )

    findings = validate_fourth_eye_decision(decision)
    finding_codes = {finding.code for finding in findings}

    assert "arbiter_missing_human_authority_doctrine" in finding_codes
    assert "arbiter_missing_completion_doctrine" in finding_codes
    assert "arbiter_gate_candidate_missing_selected_lane" in finding_codes
