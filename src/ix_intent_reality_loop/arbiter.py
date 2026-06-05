"""Fourth-eye arbitration.

The fourth-eye arbiter compares lane evidence without granting itself final
authority. It can select, clamp, defer, refuse, escalate, or safe-hold a
candidate result, but later permission, safety, reality feedback, evidence, and
human authority layers still decide whether anything may be treated as complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ix_intent_reality_loop.comparison import (
    LaneComparisonRecord,
    validate_lane_comparison_record,
)
from ix_intent_reality_loop.core import (
    BoundedScore,
    DecisionDisposition,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.lanes import ExecutionLaneResult


@dataclass(frozen=True, slots=True)
class FourthEyeDecision:
    """Arbiter decision over literal, interpreted, and self-surpass lanes."""

    decision_id: str
    intent_id: str
    comparison_id: str
    disposition: DecisionDisposition
    confidence: BoundedScore
    rationale: str
    doctrine_rule_codes: tuple[str, ...]
    selected_lane_id: str | None = None
    merged_lane_ids: tuple[str, ...] = ()
    required_next_steps: tuple[str, ...] = ()
    preserved_warnings: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            require_non_empty_text(self.decision_id, "decision_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "comparison_id",
            require_non_empty_text(self.comparison_id, "comparison_id"),
        )
        object.__setattr__(
            self,
            "rationale",
            require_non_empty_text(self.rationale, "rationale"),
        )
        object.__setattr__(
            self,
            "doctrine_rule_codes",
            tuple(
                require_non_empty_text(code, "doctrine_rule_code")
                for code in self.doctrine_rule_codes
            ),
        )
        if self.selected_lane_id is not None:
            object.__setattr__(
                self,
                "selected_lane_id",
                require_non_empty_text(self.selected_lane_id, "selected_lane_id"),
            )
        object.__setattr__(
            self,
            "merged_lane_ids",
            tuple(
                require_non_empty_text(lane_id, "merged_lane_id")
                for lane_id in self.merged_lane_ids
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
            "preserved_warnings",
            tuple(
                require_non_empty_text(warning, "preserved_warning")
                for warning in self.preserved_warnings
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def can_move_to_permission_gate(self) -> bool:
        """Return whether decision may move toward permission and safety gates."""

        return self.disposition in {
            DecisionDisposition.ALLOW,
            DecisionDisposition.CLAMP,
        }

    @property
    def blocks_action(self) -> bool:
        """Return whether decision blocks action or requires non-action handling."""

        return self.disposition in {
            DecisionDisposition.DEFER,
            DecisionDisposition.REFUSE,
            DecisionDisposition.ESCALATE,
            DecisionDisposition.SAFE_HOLD,
        }


def _lane_index(lanes: tuple[ExecutionLaneResult, ...]) -> dict[str, ExecutionLaneResult]:
    """Return lanes keyed by lane id, rejecting duplicates."""

    indexed: dict[str, ExecutionLaneResult] = {}
    for lane in lanes:
        if lane.lane_id in indexed:
            raise ValueError(f"duplicate lane_id: {lane.lane_id}")
        indexed[lane.lane_id] = lane
    return indexed


def arbitrate_fourth_eye_decision(
    *,
    decision_id: str,
    comparison: LaneComparisonRecord,
    lanes: tuple[ExecutionLaneResult, ...],
) -> FourthEyeDecision:
    """Create a fourth-eye decision from a lane comparison record.

    The arbiter is intentionally conservative. Missing triadic coverage,
    absence of a viable recommendation, or low alignment prevents allow.
    Divergence or blocked lanes clamps the recommendation instead of pretending
    the request is clean.
    """

    indexed_lanes = _lane_index(lanes)
    if set(comparison.lane_ids).difference(indexed_lanes):
        raise ValueError("comparison lane_ids must be present in lanes")

    comparison_findings = validate_lane_comparison_record(comparison)
    blocker_codes = tuple(
        finding.code for finding in comparison_findings if finding.severity == "blocker"
    )
    warning_codes = tuple(
        finding.code for finding in comparison_findings if finding.severity == "warning"
    )

    doctrine_rule_codes = (
        "thought_not_action",
        "intent_not_permission",
        "surpass_first_pass_not_user_authority",
        "human_authority_persists",
        "completion_not_output",
        "evidence_before_claim",
    )

    if "comparison_missing_triadic_lane" in blocker_codes:
        return FourthEyeDecision(
            decision_id=decision_id,
            intent_id=comparison.intent_id,
            comparison_id=comparison.comparison_id,
            disposition=DecisionDisposition.ESCALATE,
            confidence=BoundedScore(0.0),
            rationale="Arbitration escalated because triadic lane coverage is missing.",
            doctrine_rule_codes=doctrine_rule_codes,
            required_next_steps=("supply literal, interpreted, and self-surpass lanes",),
            preserved_warnings=(*blocker_codes, *warning_codes),
        )

    if comparison.recommended_lane_id is None:
        return FourthEyeDecision(
            decision_id=decision_id,
            intent_id=comparison.intent_id,
            comparison_id=comparison.comparison_id,
            disposition=DecisionDisposition.SAFE_HOLD,
            confidence=BoundedScore(0.0),
            rationale="Arbitration safe-held because no viable lane survived.",
            doctrine_rule_codes=doctrine_rule_codes,
            required_next_steps=("rebuild request lanes with viable evidence",),
            preserved_warnings=(*blocker_codes, *warning_codes),
        )

    recommended_lane = indexed_lanes[comparison.recommended_lane_id]
    if comparison.alignment_score.is_below(0.67):
        return FourthEyeDecision(
            decision_id=decision_id,
            intent_id=comparison.intent_id,
            comparison_id=comparison.comparison_id,
            disposition=DecisionDisposition.DEFER,
            confidence=comparison.alignment_score,
            rationale="Arbitration deferred because lane alignment is below target.",
            doctrine_rule_codes=doctrine_rule_codes,
            selected_lane_id=recommended_lane.lane_id,
            required_next_steps=("resolve lane disagreement before action",),
            preserved_warnings=(*blocker_codes, *warning_codes),
        )

    if comparison.blocked_lane_ids or comparison.divergence_reasons:
        return FourthEyeDecision(
            decision_id=decision_id,
            intent_id=comparison.intent_id,
            comparison_id=comparison.comparison_id,
            disposition=DecisionDisposition.CLAMP,
            confidence=BoundedScore(
                min(comparison.alignment_score.value, recommended_lane.confidence.value)
            ),
            rationale=(
                "Arbitration selected a viable lane but clamped it because "
                "blocked lanes or divergence remain preserved."
            ),
            doctrine_rule_codes=doctrine_rule_codes,
            selected_lane_id=recommended_lane.lane_id,
            merged_lane_ids=comparison.viable_lane_ids,
            required_next_steps=("send clamped recommendation to permission gate",),
            preserved_warnings=(*blocker_codes, *warning_codes),
        )

    return FourthEyeDecision(
        decision_id=decision_id,
        intent_id=comparison.intent_id,
        comparison_id=comparison.comparison_id,
        disposition=DecisionDisposition.ALLOW,
        confidence=BoundedScore(
            min(comparison.alignment_score.value, recommended_lane.confidence.value)
        ),
        rationale="Arbitration selected the highest-confidence viable lane.",
        doctrine_rule_codes=doctrine_rule_codes,
        selected_lane_id=recommended_lane.lane_id,
        required_next_steps=("send recommendation to permission gate",),
        preserved_warnings=warning_codes,
    )


def validate_fourth_eye_decision(
    decision: FourthEyeDecision,
) -> tuple[ValidationFinding, ...]:
    """Validate a fourth-eye decision before permission and safety gating."""

    findings: list[ValidationFinding] = []

    if "human_authority_persists" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "arbiter_missing_human_authority_doctrine",
                "Fourth-eye decision must preserve human authority.",
            )
        )

    if "completion_not_output" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "arbiter_missing_completion_doctrine",
                "Fourth-eye decision must not treat output as completion.",
            )
        )

    if decision.can_move_to_permission_gate and decision.selected_lane_id is None:
        findings.append(
            blocker_finding(
                "arbiter_gate_candidate_missing_selected_lane",
                "Allow or clamp decision must select a lane before gating.",
            )
        )

    if decision.blocks_action and not decision.required_next_steps:
        findings.append(
            warning_finding(
                "arbiter_blocking_decision_missing_next_steps",
                "Blocking arbiter decision should preserve required next steps.",
            )
        )

    if decision.disposition is DecisionDisposition.ALLOW and decision.preserved_warnings:
        findings.append(
            warning_finding(
                "arbiter_allow_preserves_warnings",
                "Allow decision preserved warnings that later gates must review.",
            )
        )

    if decision.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "arbiter_confidence_below_target",
                "Fourth-eye decision confidence is below the target threshold.",
            )
        )

    return tuple(findings)
