"""Memory binding decisions.

Memory is not truth. This layer decides whether an outcome delta may update
memory, downgrade prior confidence, quarantine a contradiction, or reject memory
promotion entirely. It keeps feedback consequence separate from completion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.core import (
    BoundedScore,
    EvidenceStatus,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.delta import OutcomeDelta, OutcomeDeltaStatus


class MemoryBindingAction(StrEnum):
    """Action taken against memory after outcome comparison."""

    UPDATE = "update"
    DOWNGRADE = "downgrade"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class MemoryBindingReason(StrEnum):
    """Canonical reason for a memory binding decision."""

    MATCHED_OUTCOME = "matched_outcome"
    DEGRADED_OUTCOME = "degraded_outcome"
    CONTRADICTED_OUTCOME = "contradicted_outcome"
    BLOCKED_NO_ACTION = "blocked_no_action"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class MemoryBindingDecision:
    """Decision for updating, downgrading, quarantining, or rejecting memory."""

    memory_decision_id: str
    intent_id: str
    delta_id: str
    action: MemoryBindingAction
    reason: MemoryBindingReason
    evidence_status: EvidenceStatus
    confidence_after_binding: BoundedScore
    rationale: str
    doctrine_rule_codes: tuple[str, ...]
    memory_keys: tuple[str, ...] = ()
    quarantine_tags: tuple[str, ...] = ()
    required_next_steps: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "memory_decision_id",
            require_non_empty_text(
                self.memory_decision_id,
                "memory_decision_id",
            ),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "delta_id",
            require_non_empty_text(self.delta_id, "delta_id"),
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
        object.__setattr__(
            self,
            "memory_keys",
            tuple(
                require_non_empty_text(key, "memory_key") for key in self.memory_keys
            ),
        )
        object.__setattr__(
            self,
            "quarantine_tags",
            tuple(
                require_non_empty_text(tag, "quarantine_tag")
                for tag in self.quarantine_tags
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
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def permits_positive_memory_update(self) -> bool:
        """Return whether this decision permits positive memory promotion."""

        return (
            self.action is MemoryBindingAction.UPDATE
            and self.evidence_status is EvidenceStatus.COMPLETE
            and self.confidence_after_binding.is_at_least(0.75)
        )

    @property
    def quarantines_memory(self) -> bool:
        """Return whether this decision places memory under quarantine."""

        return self.action is MemoryBindingAction.QUARANTINE


def build_memory_binding_decision(
    *,
    memory_decision_id: str,
    delta: OutcomeDelta,
    memory_keys: tuple[str, ...] = (),
) -> MemoryBindingDecision:
    """Build a memory binding decision from an outcome delta."""

    doctrine_rule_codes = (
        "reality_gets_vote",
        "evidence_before_claim",
        "completion_not_output",
    )

    if delta.status is OutcomeDeltaStatus.MATCHED and delta.supports_memory_update:
        return MemoryBindingDecision(
            memory_decision_id=memory_decision_id,
            intent_id=delta.intent_id,
            delta_id=delta.delta_id,
            action=MemoryBindingAction.UPDATE,
            reason=MemoryBindingReason.MATCHED_OUTCOME,
            evidence_status=EvidenceStatus.COMPLETE,
            confidence_after_binding=delta.confidence,
            rationale="Matched outcome supports bounded memory update review.",
            doctrine_rule_codes=doctrine_rule_codes,
            memory_keys=memory_keys,
            required_next_steps=("record bounded memory update evidence",),
        )

    if delta.status is OutcomeDeltaStatus.DEGRADED:
        return MemoryBindingDecision(
            memory_decision_id=memory_decision_id,
            intent_id=delta.intent_id,
            delta_id=delta.delta_id,
            action=MemoryBindingAction.DOWNGRADE,
            reason=MemoryBindingReason.DEGRADED_OUTCOME,
            evidence_status=EvidenceStatus.DEGRADED,
            confidence_after_binding=BoundedScore(delta.confidence.value * 0.5),
            rationale="Degraded outcome downgrades memory confidence.",
            doctrine_rule_codes=doctrine_rule_codes,
            memory_keys=memory_keys,
            required_next_steps=("preserve degraded evidence before reuse",),
        )

    if delta.status is OutcomeDeltaStatus.CONTRADICTED:
        return MemoryBindingDecision(
            memory_decision_id=memory_decision_id,
            intent_id=delta.intent_id,
            delta_id=delta.delta_id,
            action=MemoryBindingAction.QUARANTINE,
            reason=MemoryBindingReason.CONTRADICTED_OUTCOME,
            evidence_status=EvidenceStatus.REJECTED,
            confidence_after_binding=BoundedScore(0.0),
            rationale="Contradicted outcome requires memory quarantine.",
            doctrine_rule_codes=doctrine_rule_codes,
            memory_keys=memory_keys,
            quarantine_tags=("prediction_contradicted",),
            required_next_steps=("quarantine contradicted memory before reuse",),
        )

    if delta.status is OutcomeDeltaStatus.BLOCKED:
        return MemoryBindingDecision(
            memory_decision_id=memory_decision_id,
            intent_id=delta.intent_id,
            delta_id=delta.delta_id,
            action=MemoryBindingAction.QUARANTINE,
            reason=MemoryBindingReason.BLOCKED_NO_ACTION,
            evidence_status=EvidenceStatus.REJECTED,
            confidence_after_binding=BoundedScore(0.0),
            rationale="Blocked no-action outcome cannot promote memory.",
            doctrine_rule_codes=doctrine_rule_codes,
            memory_keys=memory_keys,
            quarantine_tags=("no_action", "blocked_outcome"),
            required_next_steps=("preserve no-action evidence without promotion",),
        )

    return MemoryBindingDecision(
        memory_decision_id=memory_decision_id,
        intent_id=delta.intent_id,
        delta_id=delta.delta_id,
        action=MemoryBindingAction.REJECT,
        reason=MemoryBindingReason.INSUFFICIENT_EVIDENCE,
        evidence_status=EvidenceStatus.REJECTED,
        confidence_after_binding=BoundedScore(0.0),
        rationale="Outcome delta lacks sufficient evidence for memory use.",
        doctrine_rule_codes=doctrine_rule_codes,
        memory_keys=memory_keys,
        quarantine_tags=("insufficient_evidence",),
        required_next_steps=("rebuild outcome evidence before memory use",),
    )


def validate_memory_binding_decision(
    decision: MemoryBindingDecision,
) -> tuple[ValidationFinding, ...]:
    """Validate memory binding before evidence bundling."""

    findings: list[ValidationFinding] = []

    if "reality_gets_vote" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "memory_missing_reality_doctrine",
                "Memory binding must cite reality_gets_vote doctrine.",
            )
        )

    if "evidence_before_claim" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "memory_missing_evidence_doctrine",
                "Memory binding must cite evidence_before_claim doctrine.",
            )
        )

    if "completion_not_output" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "memory_missing_completion_doctrine",
                "Memory binding must not treat memory update as completion.",
            )
        )

    if decision.action is MemoryBindingAction.UPDATE and not decision.memory_keys:
        findings.append(
            blocker_finding(
                "memory_update_missing_keys",
                "Positive memory update requires explicit memory keys.",
            )
        )

    if decision.action is MemoryBindingAction.UPDATE and (
        decision.evidence_status is not EvidenceStatus.COMPLETE
    ):
        findings.append(
            blocker_finding(
                "memory_update_without_complete_evidence",
                "Positive memory update requires complete evidence.",
            )
        )

    if decision.action is MemoryBindingAction.QUARANTINE and not (
        decision.quarantine_tags
    ):
        findings.append(
            blocker_finding(
                "memory_quarantine_missing_tags",
                "Memory quarantine requires explicit quarantine tags.",
            )
        )

    if decision.action is MemoryBindingAction.REJECT and (
        decision.confidence_after_binding.value != 0.0
    ):
        findings.append(
            blocker_finding(
                "memory_reject_has_nonzero_confidence",
                "Rejected memory binding must preserve zero confidence.",
            )
        )

    if decision.action is MemoryBindingAction.DOWNGRADE:
        findings.append(
            warning_finding(
                "memory_downgraded",
                "Memory confidence was downgraded after degraded outcome.",
            )
        )

    if decision.quarantines_memory:
        findings.append(
            warning_finding(
                "memory_quarantined",
                "Memory was quarantined and must not be reused as truth.",
            )
        )

    if decision.confidence_after_binding.is_below(0.5):
        findings.append(
            warning_finding(
                "memory_confidence_below_target",
                "Memory confidence after binding is below target threshold.",
            )
        )

    return tuple(findings)
