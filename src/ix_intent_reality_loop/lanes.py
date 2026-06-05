"""Execution lanes for governed request handling.

Execution lanes keep competing treatments of the same request separate. The
literal lane preserves the request as written so later arbiters can detect when
interpretation, improvement pressure, or convenience drifted away from the
actual user input.

The interpreted lane records what the system believes the user likely means
while preserving uncertainty, constraints, permission boundaries, and doctrine.
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
from ix_intent_reality_loop.focus import FocusSplitRecord
from ix_intent_reality_loop.intent import IntentPacket, IntentStatus


class ExecutionLaneKind(StrEnum):
    """Canonical execution lane kinds."""

    LITERAL = "literal"
    INTERPRETED = "interpreted"
    SELF_SURPASS = "self_surpass"


class ExecutionLaneStatus(StrEnum):
    """Status of an execution lane result."""

    DRAFT = "draft"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ExecutionLaneResult:
    """Result produced by one execution lane before fourth-eye arbitration."""

    lane_id: str
    intent_id: str
    kind: ExecutionLaneKind
    objective: str
    proposed_output: str
    predicted_outcome: str
    confidence: BoundedScore
    status: ExecutionLaneStatus
    doctrine_rule_codes: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    constraints_preserved: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    focus_record_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lane_id",
            require_non_empty_text(self.lane_id, "lane_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "objective",
            require_non_empty_text(self.objective, "objective"),
        )
        object.__setattr__(
            self,
            "proposed_output",
            require_non_empty_text(self.proposed_output, "proposed_output"),
        )
        object.__setattr__(
            self,
            "predicted_outcome",
            require_non_empty_text(self.predicted_outcome, "predicted_outcome"),
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
            "assumptions",
            tuple(
                require_non_empty_text(assumption, "assumption")
                for assumption in self.assumptions
            ),
        )
        object.__setattr__(
            self,
            "constraints_preserved",
            tuple(
                require_non_empty_text(constraint, "constraint")
                for constraint in self.constraints_preserved
            ),
        )
        object.__setattr__(
            self,
            "blocked_reasons",
            tuple(
                require_non_empty_text(reason, "blocked_reason")
                for reason in self.blocked_reasons
            ),
        )
        if self.focus_record_id is not None:
            object.__setattr__(
                self,
                "focus_record_id",
                require_non_empty_text(self.focus_record_id, "focus_record_id"),
            )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def is_viable(self) -> bool:
        """Return whether this lane can be considered by the arbiter."""

        return self.status is ExecutionLaneStatus.COMPLETE and not self.blocked_reasons


def _validate_focus_record_matches_packet(
    *,
    packet: IntentPacket,
    focus_record: FocusSplitRecord,
) -> None:
    """Require focus analysis to belong to the same intent packet."""

    if focus_record.intent_id != packet.intent_id:
        raise ValueError("focus record intent_id must match intent packet intent_id")


def _common_blocked_reasons(
    *,
    packet: IntentPacket,
    focus_record: FocusSplitRecord,
) -> tuple[str, ...]:
    """Return common blocked reasons shared by execution lanes."""

    blocked_reasons: list[str] = []

    if packet.status is IntentStatus.BLOCKED:
        blocked_reasons.append("intent packet is blocked")

    if focus_record.blocks_action:
        blocked_reasons.append("focus record blocks action")

    return tuple(blocked_reasons)


def _status_from_blocked_reasons(
    blocked_reasons: tuple[str, ...],
) -> ExecutionLaneStatus:
    """Return a lane status from blocked reasons."""

    return (
        ExecutionLaneStatus.BLOCKED
        if blocked_reasons
        else ExecutionLaneStatus.COMPLETE
    )


def build_literal_lane_result(
    *,
    lane_id: str,
    packet: IntentPacket,
    focus_record: FocusSplitRecord,
    proposed_output: str,
    predicted_outcome: str,
) -> ExecutionLaneResult:
    """Build a literal lane result from the exact request text.

    The literal lane is blocked when the intent packet is blocked or when focus
    analysis shows that a blocking requirement was omitted. Low confidence or
    clarification needs are preserved as assumptions instead of being hidden.
    """

    _validate_focus_record_matches_packet(packet=packet, focus_record=focus_record)

    blocked_reasons = _common_blocked_reasons(
        packet=packet,
        focus_record=focus_record,
    )
    assumptions: list[str] = []

    if packet.requires_clarification:
        assumptions.append("literal request requires clarification before action")

    return ExecutionLaneResult(
        lane_id=lane_id,
        intent_id=packet.intent_id,
        kind=ExecutionLaneKind.LITERAL,
        objective=packet.raw_request,
        proposed_output=proposed_output,
        predicted_outcome=predicted_outcome,
        confidence=packet.confidence,
        status=_status_from_blocked_reasons(blocked_reasons),
        doctrine_rule_codes=(
            "thought_not_action",
            "interpretation_not_truth",
            "completion_not_output",
        ),
        assumptions=tuple(assumptions),
        constraints_preserved=packet.constraints,
        blocked_reasons=blocked_reasons,
        focus_record_id=focus_record.record_id,
    )


def build_interpreted_lane_result(
    *,
    lane_id: str,
    packet: IntentPacket,
    focus_record: FocusSplitRecord,
    proposed_output: str,
    predicted_outcome: str,
    interpretation_assumptions: tuple[str, ...] = (),
) -> ExecutionLaneResult:
    """Build an interpreted lane result from the inferred user goal.

    The interpreted lane may improve usefulness over the literal wording, but it
    must not treat interpretation as truth, permission, or completion. Any
    uncertainty and assumptions remain visible to the arbiter.
    """

    _validate_focus_record_matches_packet(packet=packet, focus_record=focus_record)

    blocked_reasons = _common_blocked_reasons(
        packet=packet,
        focus_record=focus_record,
    )
    assumptions = list(interpretation_assumptions)

    if packet.requires_clarification:
        assumptions.append("interpreted goal requires clarification before action")

    if packet.raw_request.strip() != packet.interpreted_goal.strip():
        assumptions.append("interpreted objective differs from literal request")

    return ExecutionLaneResult(
        lane_id=lane_id,
        intent_id=packet.intent_id,
        kind=ExecutionLaneKind.INTERPRETED,
        objective=packet.interpreted_goal,
        proposed_output=proposed_output,
        predicted_outcome=predicted_outcome,
        confidence=packet.confidence,
        status=_status_from_blocked_reasons(blocked_reasons),
        doctrine_rule_codes=(
            "thought_not_action",
            "intent_not_permission",
            "interpretation_not_truth",
            "completion_not_output",
        ),
        assumptions=tuple(assumptions),
        constraints_preserved=packet.constraints,
        blocked_reasons=blocked_reasons,
        focus_record_id=focus_record.record_id,
    )


def validate_execution_lane_result(
    lane: ExecutionLaneResult,
) -> tuple[ValidationFinding, ...]:
    """Validate an execution lane result before arbitration."""

    findings: list[ValidationFinding] = []

    if lane.status is ExecutionLaneStatus.BLOCKED:
        findings.append(
            blocker_finding(
                "lane_status_blocked",
                "Execution lane is explicitly blocked.",
            )
        )

    if lane.blocked_reasons:
        findings.append(
            blocker_finding(
                "lane_blocked_reasons_present",
                "Execution lane contains blocked reasons.",
            )
        )

    if lane.assumptions:
        findings.append(
            warning_finding(
                "lane_assumptions_present",
                "Execution lane contains assumptions that must be preserved.",
            )
        )

    if lane.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "lane_confidence_below_target",
                "Execution lane confidence is below the target threshold.",
            )
        )

    if lane.kind is ExecutionLaneKind.LITERAL and "interpretation_not_truth" not in (
        lane.doctrine_rule_codes
    ):
        findings.append(
            blocker_finding(
                "literal_lane_missing_doctrine",
                "Literal lane must cite interpretation_not_truth doctrine.",
            )
        )

    if lane.kind is ExecutionLaneKind.INTERPRETED and "intent_not_permission" not in (
        lane.doctrine_rule_codes
    ):
        findings.append(
            blocker_finding(
                "interpreted_lane_missing_doctrine",
                "Interpreted lane must cite intent_not_permission doctrine.",
            )
        )

    return tuple(findings)
