"""Bounded action decision model.

This layer converts a safety-gated path into an explicit bounded action record.
It still does not perform live actuation. The record only describes what may be
evaluated next: text output, simulated action, bounded contact review, retreat,
or safe-hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

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
from ix_intent_reality_loop.safety import (
    InteractionState,
    SafetyGateResult,
)


class ActionMode(StrEnum):
    """Mode for a bounded action decision."""

    TEXT_RESPONSE = "text_response"
    SIMULATED_STEP = "simulated_step"
    BOUNDED_CONTACT_REVIEW = "bounded_contact_review"
    VERIFY_ONLY = "verify_only"
    RETREAT = "retreat"
    SAFE_HOLD = "safe_hold"


@dataclass(frozen=True, slots=True)
class BoundedActionDecision:
    """A non-actuating decision record emitted after safety gating."""

    action_id: str
    intent_id: str
    safety_gate_id: str
    mode: ActionMode
    disposition: DecisionDisposition
    selected_action: str
    predicted_outcome: str
    confidence: BoundedScore
    doctrine_rule_codes: tuple[str, ...]
    preserved_safety_signals: tuple[str, ...]
    required_next_steps: tuple[str, ...] = ()
    execution_limits: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            require_non_empty_text(self.action_id, "action_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "safety_gate_id",
            require_non_empty_text(self.safety_gate_id, "safety_gate_id"),
        )
        object.__setattr__(
            self,
            "selected_action",
            require_non_empty_text(self.selected_action, "selected_action"),
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
            "preserved_safety_signals",
            tuple(
                require_non_empty_text(code, "preserved_safety_signal")
                for code in self.preserved_safety_signals
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
            "execution_limits",
            tuple(
                require_non_empty_text(limit, "execution_limit")
                for limit in self.execution_limits
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def can_enter_feedback_loop(self) -> bool:
        """Return whether this decision can enter simulated feedback evaluation."""

        return self.disposition in {
            DecisionDisposition.ALLOW,
            DecisionDisposition.CLAMP,
        } and self.mode in {
            ActionMode.TEXT_RESPONSE,
            ActionMode.SIMULATED_STEP,
            ActionMode.BOUNDED_CONTACT_REVIEW,
            ActionMode.VERIFY_ONLY,
        }

    @property
    def blocks_action(self) -> bool:
        """Return whether this decision blocks action-like progression."""

        return self.disposition in {
            DecisionDisposition.DEFER,
            DecisionDisposition.REFUSE,
            DecisionDisposition.ESCALATE,
            DecisionDisposition.SAFE_HOLD,
        }


def _mode_from_interaction_state(state: InteractionState) -> ActionMode:
    """Map a safety interaction state to a bounded action mode."""

    if state is InteractionState.TEXT_ONLY:
        return ActionMode.TEXT_RESPONSE
    if state is InteractionState.SIMULATED_ACTION:
        return ActionMode.SIMULATED_STEP
    if state is InteractionState.BOUNDED_CONTACT_REVIEW:
        return ActionMode.BOUNDED_CONTACT_REVIEW
    if state is InteractionState.VERIFY:
        return ActionMode.VERIFY_ONLY
    if state in {
        InteractionState.RETREAT,
        InteractionState.EMERGENCY_RETREAT,
    }:
        return ActionMode.RETREAT
    return ActionMode.SAFE_HOLD


def plan_bounded_action(
    *,
    action_id: str,
    safety_result: SafetyGateResult,
    selected_action: str,
    predicted_outcome: str,
) -> BoundedActionDecision:
    """Plan a bounded non-actuating action from a safety gate result."""

    doctrine_rule_codes = (
        "thought_not_action",
        "intent_not_permission",
        "reality_gets_vote",
        "human_authority_persists",
        "completion_not_output",
    )
    mode = _mode_from_interaction_state(safety_result.interaction_state)

    if safety_result.blocks_action:
        return BoundedActionDecision(
            action_id=action_id,
            intent_id=safety_result.intent_id,
            safety_gate_id=safety_result.gate_id,
            mode=mode,
            disposition=DecisionDisposition.SAFE_HOLD,
            selected_action="No action: hold bounded agency loop.",
            predicted_outcome="No action occurs while safety gate blocks progression.",
            confidence=BoundedScore(0.0),
            doctrine_rule_codes=doctrine_rule_codes,
            preserved_safety_signals=safety_result.preserved_signal_codes,
            required_next_steps=safety_result.required_next_steps,
            execution_limits=("no execution while safety gate blocks action",),
        )

    execution_limits = (
        "evaluation runtime only",
        "no live physical actuation",
        "human authority remains final",
    )
    if mode is ActionMode.BOUNDED_CONTACT_REVIEW:
        execution_limits = (
            *execution_limits,
            "bounded contact review is descriptive and non-actuating",
        )

    return BoundedActionDecision(
        action_id=action_id,
        intent_id=safety_result.intent_id,
        safety_gate_id=safety_result.gate_id,
        mode=mode,
        disposition=safety_result.disposition,
        selected_action=selected_action,
        predicted_outcome=predicted_outcome,
        confidence=safety_result.confidence,
        doctrine_rule_codes=doctrine_rule_codes,
        preserved_safety_signals=safety_result.preserved_signal_codes,
        required_next_steps=("send bounded action decision to feedback model",),
        execution_limits=execution_limits,
    )


def validate_bounded_action_decision(
    decision: BoundedActionDecision,
) -> tuple[ValidationFinding, ...]:
    """Validate a bounded action decision before feedback simulation."""

    findings: list[ValidationFinding] = []

    if "thought_not_action" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "action_missing_thought_doctrine",
                "Action decision must cite thought_not_action doctrine.",
            )
        )

    if "completion_not_output" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "action_missing_completion_doctrine",
                "Action decision must not treat action planning as completion.",
            )
        )

    if "human_authority_persists" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "action_missing_authority_doctrine",
                "Action decision must preserve human authority.",
            )
        )

    if decision.can_enter_feedback_loop and not decision.preserved_safety_signals:
        findings.append(
            blocker_finding(
                "action_missing_safety_signal_evidence",
                "Feedback-eligible action must preserve safety signal evidence.",
            )
        )

    if decision.mode is ActionMode.RETREAT and decision.can_enter_feedback_loop:
        findings.append(
            blocker_finding(
                "action_retreat_cannot_enter_feedback_loop",
                "Retreat mode cannot be treated as an allowed feedback action.",
            )
        )

    if decision.mode is ActionMode.SAFE_HOLD and decision.can_enter_feedback_loop:
        findings.append(
            blocker_finding(
                "action_safe_hold_cannot_enter_feedback_loop",
                "Safe-hold mode cannot be treated as an allowed feedback action.",
            )
        )

    if decision.can_enter_feedback_loop and "no live physical actuation" not in (
        decision.execution_limits
    ):
        findings.append(
            blocker_finding(
                "action_missing_no_live_actuation_limit",
                "Feedback-eligible action must preserve no-live-actuation limit.",
            )
        )

    if decision.blocks_action and not decision.required_next_steps:
        findings.append(
            warning_finding(
                "action_block_missing_next_steps",
                "Blocking action decision should preserve required next steps.",
            )
        )

    if decision.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "action_confidence_below_target",
                "Bounded action confidence is below the target threshold.",
            )
        )

    return tuple(findings)
