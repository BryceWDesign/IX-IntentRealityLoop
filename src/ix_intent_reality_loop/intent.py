"""Intent packet model.

An intent packet records what the system believes is being requested while
preserving uncertainty. It does not grant permission, approve action, or mark a
task complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_mapping,
    require_non_empty_text,
    utc_now,
    warning_finding,
)


class IntentSource(StrEnum):
    """Origin of an intent packet."""

    USER_REQUEST = "user_request"
    SIMULATED_SIGNAL = "simulated_signal"
    SYSTEM_CONTEXT = "system_context"
    HUMAN_REVIEW = "human_review"


class IntentStatus(StrEnum):
    """Review status for an inferred intent."""

    DRAFT = "draft"
    READY_FOR_GATING = "ready_for_gating"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class IntentPacket:
    """A bounded record of inferred intent before permission or action."""

    intent_id: str
    source: IntentSource
    raw_request: str
    interpreted_goal: str
    confidence: BoundedScore
    status: IntentStatus = IntentStatus.DRAFT
    constraints: tuple[str, ...] = ()
    uncertainty_reasons: tuple[str, ...] = ()
    prohibited_actions: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "raw_request",
            require_non_empty_text(self.raw_request, "raw_request"),
        )
        object.__setattr__(
            self,
            "interpreted_goal",
            require_non_empty_text(self.interpreted_goal, "interpreted_goal"),
        )
        object.__setattr__(
            self,
            "constraints",
            tuple(
                require_non_empty_text(constraint, "constraint")
                for constraint in self.constraints
            ),
        )
        object.__setattr__(
            self,
            "uncertainty_reasons",
            tuple(
                require_non_empty_text(reason, "uncertainty_reason")
                for reason in self.uncertainty_reasons
            ),
        )
        object.__setattr__(
            self,
            "prohibited_actions",
            tuple(
                require_non_empty_text(action, "prohibited_action")
                for action in self.prohibited_actions
            ),
        )
        object.__setattr__(self, "context", require_mapping(self.context, "context"))
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def requires_clarification(self) -> bool:
        """Return whether uncertainty requires clarification before gating."""

        return (
            self.status is IntentStatus.NEEDS_CLARIFICATION
            or bool(self.uncertainty_reasons)
            or self.confidence.is_below(0.5)
        )

    @property
    def is_actionable_candidate(self) -> bool:
        """Return whether this packet may proceed to permission and safety gates."""

        return (
            self.status is IntentStatus.READY_FOR_GATING
            and not self.requires_clarification
            and not self.prohibited_actions
        )


def build_user_intent_packet(
    *,
    intent_id: str,
    raw_request: str,
    interpreted_goal: str,
    confidence: float,
    constraints: tuple[str, ...] = (),
    uncertainty_reasons: tuple[str, ...] = (),
    prohibited_actions: tuple[str, ...] = (),
    context: dict[str, Any] | None = None,
) -> IntentPacket:
    """Build a user-request intent packet with status derived from risk signals."""

    bounded_confidence = BoundedScore(confidence)
    if prohibited_actions:
        status = IntentStatus.BLOCKED
    elif uncertainty_reasons or bounded_confidence.is_below(0.5):
        status = IntentStatus.NEEDS_CLARIFICATION
    else:
        status = IntentStatus.READY_FOR_GATING

    return IntentPacket(
        intent_id=intent_id,
        source=IntentSource.USER_REQUEST,
        raw_request=raw_request,
        interpreted_goal=interpreted_goal,
        confidence=bounded_confidence,
        status=status,
        constraints=constraints,
        uncertainty_reasons=uncertainty_reasons,
        prohibited_actions=prohibited_actions,
        context={} if context is None else context,
    )


def validate_intent_packet(packet: IntentPacket) -> tuple[ValidationFinding, ...]:
    """Validate whether an intent packet can safely move toward gating."""

    findings: list[ValidationFinding] = []

    if packet.confidence.is_below(0.5):
        findings.append(
            blocker_finding(
                "intent_confidence_below_gate",
                "Intent confidence is below the minimum gating threshold.",
            )
        )

    if packet.uncertainty_reasons:
        findings.append(
            warning_finding(
                "intent_uncertainty_present",
                "Intent contains uncertainty reasons that must be preserved.",
            )
        )

    if packet.prohibited_actions:
        findings.append(
            blocker_finding(
                "intent_contains_prohibited_action",
                "Intent includes prohibited action signals and cannot proceed.",
            )
        )

    if packet.status is IntentStatus.BLOCKED:
        findings.append(
            blocker_finding(
                "intent_status_blocked",
                "Intent packet is explicitly blocked.",
            )
        )

    if packet.status is IntentStatus.NEEDS_CLARIFICATION:
        findings.append(
            warning_finding(
                "intent_needs_clarification",
                "Intent packet requires clarification before action gating.",
            )
        )

    return tuple(findings)
