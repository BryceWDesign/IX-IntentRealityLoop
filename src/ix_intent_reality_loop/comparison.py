"""Lane comparison records.

This module compares literal, interpreted, and self-surpass lane results before
fourth-eye arbitration. It does not grant permission, perform action, or mark
completion. It only records which lanes survived, which lanes failed, and where
their objectives diverged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.lanes import (
    ExecutionLaneKind,
    ExecutionLaneResult,
)


_REQUIRED_TRIADIC_KINDS = frozenset(
    {
        ExecutionLaneKind.LITERAL,
        ExecutionLaneKind.INTERPRETED,
        ExecutionLaneKind.SELF_SURPASS,
    }
)


@dataclass(frozen=True, slots=True)
class LaneComparisonRecord:
    """Comparison of competing execution lanes for one intent."""

    comparison_id: str
    intent_id: str
    lane_ids: tuple[str, ...]
    viable_lane_ids: tuple[str, ...]
    blocked_lane_ids: tuple[str, ...]
    omitted_lane_kinds: tuple[ExecutionLaneKind, ...]
    recommended_lane_id: str | None
    alignment_score: BoundedScore
    divergence_reasons: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "comparison_id",
            require_non_empty_text(self.comparison_id, "comparison_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "lane_ids",
            tuple(require_non_empty_text(lane_id, "lane_id") for lane_id in self.lane_ids),
        )
        object.__setattr__(
            self,
            "viable_lane_ids",
            tuple(
                require_non_empty_text(lane_id, "viable_lane_id")
                for lane_id in self.viable_lane_ids
            ),
        )
        object.__setattr__(
            self,
            "blocked_lane_ids",
            tuple(
                require_non_empty_text(lane_id, "blocked_lane_id")
                for lane_id in self.blocked_lane_ids
            ),
        )
        if self.recommended_lane_id is not None:
            object.__setattr__(
                self,
                "recommended_lane_id",
                require_non_empty_text(
                    self.recommended_lane_id,
                    "recommended_lane_id",
                ),
            )
        object.__setattr__(
            self,
            "divergence_reasons",
            tuple(
                require_non_empty_text(reason, "divergence_reason")
                for reason in self.divergence_reasons
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

        lane_id_set = set(self.lane_ids)
        if set(self.viable_lane_ids).difference(lane_id_set):
            raise ValueError("viable_lane_ids must be a subset of lane_ids")
        if set(self.blocked_lane_ids).difference(lane_id_set):
            raise ValueError("blocked_lane_ids must be a subset of lane_ids")
        if self.recommended_lane_id is not None and (
            self.recommended_lane_id not in self.viable_lane_ids
        ):
            raise ValueError("recommended_lane_id must be one of viable_lane_ids")

    @property
    def has_full_triadic_coverage(self) -> bool:
        """Return whether literal, interpreted, and self-surpass lanes are present."""

        return not self.omitted_lane_kinds

    @property
    def has_viable_recommendation(self) -> bool:
        """Return whether comparison produced a viable recommended lane."""

        return self.recommended_lane_id is not None


def _require_same_intent(lanes: tuple[ExecutionLaneResult, ...]) -> str:
    """Return shared intent id or raise when lanes do not belong together."""

    if not lanes:
        raise ValueError("lanes must not be empty")

    intent_ids = {lane.intent_id for lane in lanes}
    if len(intent_ids) != 1:
        raise ValueError("all lanes must share the same intent_id")

    return lanes[0].intent_id


def _objective_divergence_reasons(
    lanes: tuple[ExecutionLaneResult, ...],
) -> tuple[str, ...]:
    """Return objective-level divergence signals for compared lanes."""

    reasons: list[str] = []
    objectives_by_kind = {lane.kind: lane.objective for lane in lanes}

    literal_objective = objectives_by_kind.get(ExecutionLaneKind.LITERAL)
    interpreted_objective = objectives_by_kind.get(ExecutionLaneKind.INTERPRETED)
    self_surpass_objective = objectives_by_kind.get(ExecutionLaneKind.SELF_SURPASS)

    if literal_objective and interpreted_objective:
        if literal_objective.strip() != interpreted_objective.strip():
            reasons.append("literal and interpreted objectives differ")

    if self_surpass_objective:
        reasons.append("self-surpass objective requires boundary review")

    blocked_kinds = tuple(lane.kind for lane in lanes if not lane.is_viable)
    if blocked_kinds:
        joined_kinds = ", ".join(kind.value for kind in blocked_kinds)
        reasons.append(f"nonviable lane kind(s): {joined_kinds}")

    return tuple(reasons)


def build_lane_comparison_record(
    *,
    comparison_id: str,
    lanes: tuple[ExecutionLaneResult, ...],
) -> LaneComparisonRecord:
    """Build a comparison record from execution lane results."""

    intent_id = _require_same_intent(lanes)
    lane_ids = tuple(lane.lane_id for lane in lanes)
    kinds_present = {lane.kind for lane in lanes}
    omitted_lane_kinds = tuple(
        lane_kind
        for lane_kind in (
            ExecutionLaneKind.LITERAL,
            ExecutionLaneKind.INTERPRETED,
            ExecutionLaneKind.SELF_SURPASS,
        )
        if lane_kind not in kinds_present
    )
    viable_lanes = tuple(lane for lane in lanes if lane.is_viable)
    blocked_lanes = tuple(lane for lane in lanes if not lane.is_viable)
    recommended_lane = (
        max(viable_lanes, key=lambda lane: lane.confidence.value)
        if viable_lanes
        else None
    )
    alignment_score = BoundedScore(len(viable_lanes) / len(lanes))

    return LaneComparisonRecord(
        comparison_id=comparison_id,
        intent_id=intent_id,
        lane_ids=lane_ids,
        viable_lane_ids=tuple(lane.lane_id for lane in viable_lanes),
        blocked_lane_ids=tuple(lane.lane_id for lane in blocked_lanes),
        omitted_lane_kinds=omitted_lane_kinds,
        recommended_lane_id=(
            None if recommended_lane is None else recommended_lane.lane_id
        ),
        alignment_score=alignment_score,
        divergence_reasons=_objective_divergence_reasons(lanes),
    )


def validate_lane_comparison_record(
    record: LaneComparisonRecord,
) -> tuple[ValidationFinding, ...]:
    """Validate a lane comparison record before fourth-eye arbitration."""

    findings: list[ValidationFinding] = []

    if not record.has_full_triadic_coverage:
        missing = ", ".join(kind.value for kind in record.omitted_lane_kinds)
        findings.append(
            blocker_finding(
                "comparison_missing_triadic_lane",
                f"Lane comparison is missing required lane kind(s): {missing}.",
            )
        )

    if not record.has_viable_recommendation:
        findings.append(
            blocker_finding(
                "comparison_has_no_viable_recommendation",
                "Lane comparison has no viable lane to recommend.",
            )
        )

    if record.blocked_lane_ids:
        findings.append(
            warning_finding(
                "comparison_contains_blocked_lanes",
                "One or more lanes were blocked and must remain visible.",
            )
        )

    if record.divergence_reasons:
        findings.append(
            warning_finding(
                "comparison_divergence_present",
                "Lane objectives or viability diverged and require arbitration.",
            )
        )

    if record.alignment_score.is_below(0.67):
        findings.append(
            warning_finding(
                "comparison_alignment_below_target",
                "Less than two thirds of compared lanes remained viable.",
            )
        )

    return tuple(findings)
