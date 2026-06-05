from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.comparison import (
    LaneComparisonRecord,
    build_lane_comparison_record,
    validate_lane_comparison_record,
)
from ix_intent_reality_loop.core import BoundedScore, ValidationSeverity
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
        blocked_reasons=blocked_reasons,
    )


def test_lane_comparison_record_preserves_lane_sets() -> None:
    record = LaneComparisonRecord(
        comparison_id="comparison-001",
        intent_id="intent-001",
        lane_ids=("lane-001", "lane-002"),
        viable_lane_ids=("lane-001",),
        blocked_lane_ids=("lane-002",),
        omitted_lane_kinds=(ExecutionLaneKind.SELF_SURPASS,),
        recommended_lane_id="lane-001",
        alignment_score=BoundedScore(0.5),
        divergence_reasons=("literal and interpreted objectives differ",),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert not record.has_full_triadic_coverage
    assert record.has_viable_recommendation
    assert record.created_at.tzinfo is UTC


def test_lane_comparison_record_rejects_invalid_recommended_lane() -> None:
    with pytest.raises(ValueError, match="recommended_lane_id must be one"):
        LaneComparisonRecord(
            comparison_id="comparison-002",
            intent_id="intent-002",
            lane_ids=("lane-001",),
            viable_lane_ids=("lane-001",),
            blocked_lane_ids=(),
            omitted_lane_kinds=(),
            recommended_lane_id="lane-999",
            alignment_score=BoundedScore(1.0),
        )


def test_lane_comparison_record_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        LaneComparisonRecord(
            comparison_id="comparison-003",
            intent_id="intent-003",
            lane_ids=("lane-001",),
            viable_lane_ids=("lane-001",),
            blocked_lane_ids=(),
            omitted_lane_kinds=(),
            recommended_lane_id="lane-001",
            alignment_score=BoundedScore(1.0),
            created_at=datetime(2026, 1, 1),
        )


def test_build_lane_comparison_record_selects_highest_confidence_viable_lane() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.7,
        objective="Move it over there.",
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.9,
        objective="Ask which object and destination are intended.",
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.8,
    )

    record = build_lane_comparison_record(
        comparison_id="comparison-004",
        lanes=(literal, interpreted, self_surpass),
    )

    assert record.has_full_triadic_coverage
    assert record.recommended_lane_id == "lane-interpreted"
    assert record.alignment_score.value == 1.0
    assert "literal and interpreted objectives differ" in record.divergence_reasons
    assert "self-surpass objective requires boundary review" in (
        record.divergence_reasons
    )


def test_build_lane_comparison_record_tracks_blocked_lanes() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.7,
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.8,
        status=ExecutionLaneStatus.BLOCKED,
        blocked_reasons=("focus record blocks action",),
    )
    self_surpass = _lane(
        lane_id="lane-self-surpass",
        kind=ExecutionLaneKind.SELF_SURPASS,
        confidence=0.9,
    )

    record = build_lane_comparison_record(
        comparison_id="comparison-005",
        lanes=(literal, interpreted, self_surpass),
    )
    findings = validate_lane_comparison_record(record)
    finding_codes = {finding.code for finding in findings}

    assert record.recommended_lane_id == "lane-self-surpass"
    assert record.blocked_lane_ids == ("lane-interpreted",)
    assert record.alignment_score.value == pytest.approx(2 / 3)
    assert "comparison_contains_blocked_lanes" in finding_codes


def test_build_lane_comparison_record_blocks_missing_triadic_lane() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.7,
    )
    interpreted = _lane(
        lane_id="lane-interpreted",
        kind=ExecutionLaneKind.INTERPRETED,
        confidence=0.8,
    )

    record = build_lane_comparison_record(
        comparison_id="comparison-006",
        lanes=(literal, interpreted),
    )
    findings = validate_lane_comparison_record(record)

    assert record.omitted_lane_kinds == (ExecutionLaneKind.SELF_SURPASS,)
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )


def test_build_lane_comparison_record_rejects_empty_lane_set() -> None:
    with pytest.raises(ValueError, match="lanes must not be empty"):
        build_lane_comparison_record(comparison_id="comparison-007", lanes=())


def test_build_lane_comparison_record_rejects_mixed_intents() -> None:
    literal = _lane(
        lane_id="lane-literal",
        kind=ExecutionLaneKind.LITERAL,
        confidence=0.7,
    )
    other = ExecutionLaneResult(
        lane_id="lane-other",
        intent_id="intent-999",
        kind=ExecutionLaneKind.INTERPRETED,
        objective="Other objective.",
        proposed_output="Other output.",
        predicted_outcome="Other outcome.",
        confidence=BoundedScore(0.8),
        status=ExecutionLaneStatus.COMPLETE,
        doctrine_rule_codes=("completion_not_output",),
    )

    with pytest.raises(ValueError, match="all lanes must share"):
        build_lane_comparison_record(
            comparison_id="comparison-008",
            lanes=(literal, other),
        )
