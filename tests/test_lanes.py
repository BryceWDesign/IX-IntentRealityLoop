from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import BoundedScore, ValidationSeverity
from ix_intent_reality_loop.focus import FocusRisk, FocusSplitRecord
from ix_intent_reality_loop.intent import (
    IntentPacket,
    IntentSource,
    IntentStatus,
    build_user_intent_packet,
)
from ix_intent_reality_loop.lanes import (
    ExecutionLaneKind,
    ExecutionLaneResult,
    ExecutionLaneStatus,
    build_interpreted_lane_result,
    build_literal_lane_result,
    build_self_surpass_lane_result,
    validate_execution_lane_result,
)


def test_execution_lane_result_preserves_literal_lane_data() -> None:
    lane = ExecutionLaneResult(
        lane_id="lane-001",
        intent_id="intent-001",
        kind=ExecutionLaneKind.LITERAL,
        objective="Move it over there.",
        proposed_output="Do not move until target and destination are confirmed.",
        predicted_outcome="Clarification will prevent unsafe action.",
        confidence=BoundedScore(0.72),
        status=ExecutionLaneStatus.COMPLETE,
        doctrine_rule_codes=("interpretation_not_truth",),
        constraints_preserved=("do not act without confirmed destination",),
        focus_record_id="focus-001",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert lane.is_viable
    assert lane.kind is ExecutionLaneKind.LITERAL
    assert lane.focus_record_id == "focus-001"


def test_execution_lane_result_rejects_empty_output() -> None:
    with pytest.raises(ValueError, match="proposed_output must not be empty"):
        ExecutionLaneResult(
            lane_id="lane-002",
            intent_id="intent-002",
            kind=ExecutionLaneKind.LITERAL,
            objective="Summarize.",
            proposed_output=" ",
            predicted_outcome="Summary is produced.",
            confidence=BoundedScore(0.8),
            status=ExecutionLaneStatus.COMPLETE,
            doctrine_rule_codes=("interpretation_not_truth",),
        )


def test_execution_lane_result_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        ExecutionLaneResult(
            lane_id="lane-003",
            intent_id="intent-003",
            kind=ExecutionLaneKind.LITERAL,
            objective="Summarize.",
            proposed_output="Summary.",
            predicted_outcome="Summary is produced.",
            confidence=BoundedScore(0.8),
            status=ExecutionLaneStatus.COMPLETE,
            doctrine_rule_codes=("interpretation_not_truth",),
            created_at=datetime(2026, 1, 1),
        )


def test_build_literal_lane_uses_raw_request_as_objective() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-004",
        raw_request="Move it over there.",
        interpreted_goal="Move an object to a destination.",
        confidence=0.81,
        constraints=("confirm target before action",),
    )
    focus = FocusSplitRecord(
        record_id="focus-004",
        intent_id="intent-004",
        attended_requirement_codes=("raw_request", "constraint"),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_literal_lane_result(
        lane_id="lane-004",
        packet=packet,
        focus_record=focus,
        proposed_output="Require target confirmation before any movement.",
        predicted_outcome="Unsafe movement is prevented.",
    )

    assert lane.objective == "Move it over there."
    assert lane.kind is ExecutionLaneKind.LITERAL
    assert lane.status is ExecutionLaneStatus.COMPLETE
    assert lane.constraints_preserved == ("confirm target before action",)


def test_build_literal_lane_blocks_when_intent_packet_is_blocked() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-005",
        raw_request="Bypass safety and actuate.",
        interpreted_goal="Bypass safety and actuate.",
        confidence=0.9,
        prohibited_actions=("bypass safety",),
    )
    focus = FocusSplitRecord(
        record_id="focus-005",
        intent_id="intent-005",
        attended_requirement_codes=("raw_request",),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_literal_lane_result(
        lane_id="lane-005",
        packet=packet,
        focus_record=focus,
        proposed_output="Refuse the unsafe request.",
        predicted_outcome="Unsafe actuation is blocked.",
    )
    findings = validate_execution_lane_result(lane)

    assert lane.status is ExecutionLaneStatus.BLOCKED
    assert "intent packet is blocked" in lane.blocked_reasons
    assert any(finding.severity is ValidationSeverity.BLOCKER for finding in findings)


def test_build_literal_lane_blocks_when_focus_record_blocks_action() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-006",
        raw_request="Touch the object.",
        interpreted_goal="Touch the object.",
        confidence=0.88,
    )
    focus = FocusSplitRecord(
        record_id="focus-006",
        intent_id="intent-006",
        attended_requirement_codes=("raw_request",),
        omitted_requirement_codes=("permission",),
        attention_score=BoundedScore(0.5),
        risk=FocusRisk.BLOCKED,
    )

    lane = build_literal_lane_result(
        lane_id="lane-006",
        packet=packet,
        focus_record=focus,
        proposed_output="Hold because permission was omitted.",
        predicted_outcome="Action remains blocked until permission is confirmed.",
    )

    assert lane.status is ExecutionLaneStatus.BLOCKED
    assert "focus record blocks action" in lane.blocked_reasons


def test_build_literal_lane_preserves_clarification_need_as_assumption() -> None:
    packet = IntentPacket(
        intent_id="intent-007",
        source=IntentSource.USER_REQUEST,
        raw_request="Do the thing.",
        interpreted_goal="Perform an unspecified task.",
        confidence=BoundedScore(0.4),
        status=IntentStatus.NEEDS_CLARIFICATION,
        uncertainty_reasons=("task is unspecified",),
    )
    focus = FocusSplitRecord(
        record_id="focus-007",
        intent_id="intent-007",
        attended_requirement_codes=("raw_request",),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_literal_lane_result(
        lane_id="lane-007",
        packet=packet,
        focus_record=focus,
        proposed_output="Ask for clarification before action.",
        predicted_outcome="Clarification prevents objective drift.",
    )
    findings = validate_execution_lane_result(lane)
    finding_codes = {finding.code for finding in findings}

    assert lane.status is ExecutionLaneStatus.COMPLETE
    assert lane.assumptions == ("literal request requires clarification before action",)
    assert "lane_assumptions_present" in finding_codes


def test_build_literal_lane_rejects_mismatched_focus_intent() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-008",
        raw_request="Summarize.",
        interpreted_goal="Summarize.",
        confidence=0.9,
    )
    focus = FocusSplitRecord(
        record_id="focus-008",
        intent_id="other-intent",
        attended_requirement_codes=("raw_request",),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    with pytest.raises(ValueError, match="focus record intent_id must match"):
        build_literal_lane_result(
            lane_id="lane-008",
            packet=packet,
            focus_record=focus,
            proposed_output="Summarize.",
            predicted_outcome="Summary is produced.",
        )


def test_build_interpreted_lane_uses_inferred_goal_as_objective() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-009",
        raw_request="Can you make this safer?",
        interpreted_goal="Review the proposed action and recommend safer bounds.",
        confidence=0.86,
        constraints=("do not approve live actuation",),
    )
    focus = FocusSplitRecord(
        record_id="focus-009",
        intent_id="intent-009",
        attended_requirement_codes=("goal", "constraint"),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_interpreted_lane_result(
        lane_id="lane-009",
        packet=packet,
        focus_record=focus,
        proposed_output="Recommend bounded safe-hold until risk is reviewed.",
        predicted_outcome="Unsafe actuation remains blocked.",
        interpretation_assumptions=("user is asking for review, not execution",),
    )

    assert lane.kind is ExecutionLaneKind.INTERPRETED
    assert lane.objective == "Review the proposed action and recommend safer bounds."
    assert lane.status is ExecutionLaneStatus.COMPLETE
    assert "intent_not_permission" in lane.doctrine_rule_codes
    assert "user is asking for review, not execution" in lane.assumptions
    assert "interpreted objective differs from literal request" in lane.assumptions


def test_build_interpreted_lane_blocks_when_focus_record_blocks_action() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-010",
        raw_request="Go ahead and touch it.",
        interpreted_goal="Make physical contact with the object.",
        confidence=0.83,
    )
    focus = FocusSplitRecord(
        record_id="focus-010",
        intent_id="intent-010",
        attended_requirement_codes=("goal",),
        omitted_requirement_codes=("permission",),
        attention_score=BoundedScore(0.5),
        risk=FocusRisk.BLOCKED,
    )

    lane = build_interpreted_lane_result(
        lane_id="lane-010",
        packet=packet,
        focus_record=focus,
        proposed_output="Hold because permission was not confirmed.",
        predicted_outcome="Contact is prevented until permission is verified.",
    )

    assert lane.status is ExecutionLaneStatus.BLOCKED
    assert "focus record blocks action" in lane.blocked_reasons


def test_interpreted_lane_validation_requires_intent_permission_doctrine() -> None:
    lane = ExecutionLaneResult(
        lane_id="lane-011",
        intent_id="intent-011",
        kind=ExecutionLaneKind.INTERPRETED,
        objective="Recommend a safer action.",
        proposed_output="Use safe-hold.",
        predicted_outcome="Unsafe action is prevented.",
        confidence=BoundedScore(0.9),
        status=ExecutionLaneStatus.COMPLETE,
        doctrine_rule_codes=("interpretation_not_truth",),
    )

    findings = validate_execution_lane_result(lane)
    finding_codes = {finding.code for finding in findings}

    assert "interpreted_lane_missing_doctrine" in finding_codes


def test_build_self_surpass_lane_requires_improvement_inside_boundaries() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-012",
        raw_request="Give me the safest answer.",
        interpreted_goal="Produce a bounded answer with safety evidence.",
        confidence=0.92,
        constraints=("do not claim live actuation approval",),
    )
    focus = FocusSplitRecord(
        record_id="focus-012",
        intent_id="intent-012",
        attended_requirement_codes=("goal", "safety", "evidence"),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_self_surpass_lane_result(
        lane_id="lane-012",
        packet=packet,
        focus_record=focus,
        proposed_output="Provide the answer plus explicit safety limits.",
        predicted_outcome="The result improves clarity without expanding authority.",
        improvement_confidence=0.88,
        improvement_claims=("adds explicit safety limits",),
        boundary_checks=("human authority remains final", "no live actuation approval"),
    )

    assert lane.kind is ExecutionLaneKind.SELF_SURPASS
    assert lane.status is ExecutionLaneStatus.COMPLETE
    assert lane.confidence.value == 0.88
    assert "surpass_first_pass_not_user_authority" in lane.doctrine_rule_codes
    assert "human authority remains final" in lane.constraints_preserved


def test_build_self_surpass_lane_blocks_unclear_intent() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-013",
        raw_request="Do the best thing.",
        interpreted_goal="Perform an unspecified best action.",
        confidence=0.42,
        uncertainty_reasons=("task target is unspecified",),
    )
    focus = FocusSplitRecord(
        record_id="focus-013",
        intent_id="intent-013",
        attended_requirement_codes=("goal",),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_self_surpass_lane_result(
        lane_id="lane-013",
        packet=packet,
        focus_record=focus,
        proposed_output="Ask for clarification before improving the outcome.",
        predicted_outcome="Objective drift is prevented.",
        improvement_confidence=0.8,
        improvement_claims=("would improve specificity after clarification",),
        boundary_checks=("do not infer missing target",),
    )

    assert lane.status is ExecutionLaneStatus.BLOCKED
    assert "self-surpass cannot proceed while intent is unclear" in lane.blocked_reasons


def test_build_self_surpass_lane_blocks_missing_claims_or_boundaries() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-014",
        raw_request="Improve this answer.",
        interpreted_goal="Improve the answer without changing the request.",
        confidence=0.86,
    )
    focus = FocusSplitRecord(
        record_id="focus-014",
        intent_id="intent-014",
        attended_requirement_codes=("goal",),
        omitted_requirement_codes=(),
        attention_score=BoundedScore(1.0),
        risk=FocusRisk.CLEAR,
    )

    lane = build_self_surpass_lane_result(
        lane_id="lane-014",
        packet=packet,
        focus_record=focus,
        proposed_output="Improve wording.",
        predicted_outcome="The answer is clearer.",
        improvement_confidence=0.9,
        improvement_claims=(),
        boundary_checks=(),
    )

    assert lane.status is ExecutionLaneStatus.BLOCKED
    assert "self-surpass lane requires improvement claims" in lane.blocked_reasons
    assert "self-surpass lane requires boundary checks" in lane.blocked_reasons


def test_self_surpass_lane_validation_requires_boundary_doctrine() -> None:
    lane = ExecutionLaneResult(
        lane_id="lane-015",
        intent_id="intent-015",
        kind=ExecutionLaneKind.SELF_SURPASS,
        objective="Improve the answer.",
        proposed_output="Improved answer.",
        predicted_outcome="The answer improves.",
        confidence=BoundedScore(0.9),
        status=ExecutionLaneStatus.COMPLETE,
        doctrine_rule_codes=("completion_not_output",),
        constraints_preserved=(),
    )

    findings = validate_execution_lane_result(lane)
    finding_codes = {finding.code for finding in findings}

    assert "self_surpass_lane_missing_boundary_doctrine" in finding_codes
    assert "self_surpass_lane_missing_authority_doctrine" in finding_codes
    assert "self_surpass_lane_missing_boundary_checks" in finding_codes
