"""Permission and consent gate.

This layer separates selected intent from authority. A fourth-eye arbiter may
recommend a lane, but permission must still be fresh, scoped, non-revoked, and
compatible with source-available evaluation boundaries before anything can move
toward safety or action decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.arbiter import FourthEyeDecision
from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)


class PermissionScope(StrEnum):
    """Permission scope requested by a selected agency-loop decision."""

    TEXT_OUTPUT = "text_output"
    SIMULATED_ACTION = "simulated_action"
    BOUNDED_CONTACT_REVIEW = "bounded_contact_review"
    LIVE_PHYSICAL_ACTUATION = "live_physical_actuation"


class ConsentStatus(StrEnum):
    """Status of a consent record at gate-check time."""

    FRESH = "fresh"
    STALE = "stale"
    REVOKED = "revoked"
    WRONG_SCOPE = "wrong_scope"
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    """Explicit consent record for a bounded permission scope."""

    consent_id: str
    intent_id: str
    granted_by: str
    scope: PermissionScope
    granted_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    revoked: bool = False
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "consent_id",
            require_non_empty_text(self.consent_id, "consent_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "granted_by",
            require_non_empty_text(self.granted_by, "granted_by"),
        )
        object.__setattr__(
            self,
            "granted_at",
            require_aware_utc(self.granted_at, "granted_at"),
        )
        if self.expires_at is not None:
            normalized_expires_at = require_aware_utc(self.expires_at, "expires_at")
            if normalized_expires_at <= self.granted_at:
                raise ValueError("expires_at must be after granted_at")
            object.__setattr__(self, "expires_at", normalized_expires_at)
        object.__setattr__(
            self,
            "constraints",
            tuple(
                require_non_empty_text(constraint, "constraint")
                for constraint in self.constraints
            ),
        )

    def status_at(
        self, *, requested_scope: PermissionScope, checked_at: datetime
    ) -> ConsentStatus:
        """Return consent status for a requested scope at a specific time."""

        normalized_checked_at = require_aware_utc(checked_at, "checked_at")
        if self.revoked:
            return ConsentStatus.REVOKED
        if self.scope is not requested_scope:
            return ConsentStatus.WRONG_SCOPE
        if self.expires_at is not None and normalized_checked_at >= self.expires_at:
            return ConsentStatus.STALE
        return ConsentStatus.FRESH

    def is_fresh_for(
        self,
        *,
        requested_scope: PermissionScope,
        checked_at: datetime,
    ) -> bool:
        """Return whether consent is fresh for the requested scope."""

        return (
            self.status_at(
                requested_scope=requested_scope,
                checked_at=checked_at,
            )
            is ConsentStatus.FRESH
        )


@dataclass(frozen=True, slots=True)
class PermissionGateResult:
    """Result of permission and consent gating."""

    gate_id: str
    intent_id: str
    decision_id: str
    requested_scope: PermissionScope
    consent_status: ConsentStatus
    disposition: DecisionDisposition
    authority_state: AuthorityState
    confidence: BoundedScore
    rationale: str
    doctrine_rule_codes: tuple[str, ...]
    consent_id: str | None = None
    required_next_steps: tuple[str, ...] = ()
    preserved_constraints: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "gate_id",
            require_non_empty_text(self.gate_id, "gate_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "decision_id",
            require_non_empty_text(self.decision_id, "decision_id"),
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
        if self.consent_id is not None:
            object.__setattr__(
                self,
                "consent_id",
                require_non_empty_text(self.consent_id, "consent_id"),
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
            "preserved_constraints",
            tuple(
                require_non_empty_text(constraint, "preserved_constraint")
                for constraint in self.preserved_constraints
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def permits_safety_gate(self) -> bool:
        """Return whether the result can proceed to safety gating."""

        return self.disposition in {
            DecisionDisposition.ALLOW,
            DecisionDisposition.CLAMP,
        }

    @property
    def blocks_action(self) -> bool:
        """Return whether permission gating blocks action."""

        return self.disposition in {
            DecisionDisposition.DEFER,
            DecisionDisposition.REFUSE,
            DecisionDisposition.ESCALATE,
            DecisionDisposition.SAFE_HOLD,
        }


def evaluate_permission_gate(
    *,
    gate_id: str,
    decision: FourthEyeDecision,
    requested_scope: PermissionScope,
    consent: ConsentRecord | None,
    checked_at: datetime | None = None,
) -> PermissionGateResult:
    """Evaluate permission and consent for an arbiter decision."""

    check_time = (
        utc_now()
        if checked_at is None
        else require_aware_utc(
            checked_at,
            "checked_at",
        )
    )
    doctrine_rule_codes = (
        "intent_not_permission",
        "human_authority_persists",
        "completion_not_output",
    )

    if decision.blocks_action:
        return PermissionGateResult(
            gate_id=gate_id,
            intent_id=decision.intent_id,
            decision_id=decision.decision_id,
            requested_scope=requested_scope,
            consent_status=ConsentStatus.ABSENT
            if consent is None
            else (
                consent.status_at(
                    requested_scope=requested_scope,
                    checked_at=check_time,
                )
            ),
            disposition=DecisionDisposition.SAFE_HOLD,
            authority_state=AuthorityState.HUMAN_REVIEW_REQUIRED,
            confidence=BoundedScore(0.0),
            rationale=(
                "Permission gate safe-held because arbiter decision blocks action."
            ),
            doctrine_rule_codes=doctrine_rule_codes,
            consent_id=None if consent is None else consent.consent_id,
            required_next_steps=(
                "resolve arbiter blocking decision before permission",
            ),
            preserved_constraints=() if consent is None else consent.constraints,
            created_at=check_time,
        )

    if requested_scope is PermissionScope.LIVE_PHYSICAL_ACTUATION:
        return PermissionGateResult(
            gate_id=gate_id,
            intent_id=decision.intent_id,
            decision_id=decision.decision_id,
            requested_scope=requested_scope,
            consent_status=ConsentStatus.ABSENT
            if consent is None
            else (
                consent.status_at(
                    requested_scope=requested_scope,
                    checked_at=check_time,
                )
            ),
            disposition=DecisionDisposition.REFUSE,
            authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
            confidence=BoundedScore(0.0),
            rationale=(
                "Live physical actuation is outside IX-IntentRealityLoop "
                "evaluation boundaries."
            ),
            doctrine_rule_codes=doctrine_rule_codes,
            consent_id=None if consent is None else consent.consent_id,
            required_next_steps=(
                "use simulated action or bounded contact review only",
            ),
            preserved_constraints=() if consent is None else consent.constraints,
            created_at=check_time,
        )

    if consent is None:
        return PermissionGateResult(
            gate_id=gate_id,
            intent_id=decision.intent_id,
            decision_id=decision.decision_id,
            requested_scope=requested_scope,
            consent_status=ConsentStatus.ABSENT,
            disposition=DecisionDisposition.DEFER,
            authority_state=AuthorityState.HUMAN_REVIEW_REQUIRED,
            confidence=BoundedScore(0.0),
            rationale="Permission gate deferred because no consent record exists.",
            doctrine_rule_codes=doctrine_rule_codes,
            required_next_steps=("obtain explicit scoped human consent",),
            created_at=check_time,
        )

    if consent.intent_id != decision.intent_id:
        raise ValueError("consent intent_id must match decision intent_id")

    consent_status = consent.status_at(
        requested_scope=requested_scope,
        checked_at=check_time,
    )
    if consent_status is not ConsentStatus.FRESH:
        return PermissionGateResult(
            gate_id=gate_id,
            intent_id=decision.intent_id,
            decision_id=decision.decision_id,
            requested_scope=requested_scope,
            consent_status=consent_status,
            disposition=DecisionDisposition.DEFER,
            authority_state=AuthorityState.HUMAN_REVIEW_REQUIRED,
            confidence=BoundedScore(0.0),
            rationale=(
                f"Permission gate deferred because consent is {consent_status.value}."
            ),
            doctrine_rule_codes=doctrine_rule_codes,
            consent_id=consent.consent_id,
            required_next_steps=("refresh consent before action gating",),
            preserved_constraints=consent.constraints,
            created_at=check_time,
        )

    disposition = (
        DecisionDisposition.CLAMP
        if decision.disposition is DecisionDisposition.CLAMP
        else DecisionDisposition.ALLOW
    )

    return PermissionGateResult(
        gate_id=gate_id,
        intent_id=decision.intent_id,
        decision_id=decision.decision_id,
        requested_scope=requested_scope,
        consent_status=ConsentStatus.FRESH,
        disposition=disposition,
        authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
        confidence=decision.confidence,
        rationale="Permission gate accepted fresh scoped consent for evaluation.",
        doctrine_rule_codes=doctrine_rule_codes,
        consent_id=consent.consent_id,
        required_next_steps=("send permission-approved decision to safety gate",),
        preserved_constraints=consent.constraints,
        created_at=check_time,
    )


def validate_permission_gate_result(
    result: PermissionGateResult,
) -> tuple[ValidationFinding, ...]:
    """Validate permission gate output before safety gating."""

    findings: list[ValidationFinding] = []

    if "intent_not_permission" not in result.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "permission_gate_missing_intent_doctrine",
                "Permission gate must cite intent_not_permission doctrine.",
            )
        )

    if "human_authority_persists" not in result.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "permission_gate_missing_authority_doctrine",
                "Permission gate must cite persistent human authority doctrine.",
            )
        )

    if result.requested_scope is PermissionScope.LIVE_PHYSICAL_ACTUATION:
        findings.append(
            blocker_finding(
                "permission_gate_live_actuation_requested",
                "Live physical actuation is outside evaluation boundaries.",
            )
        )

    if result.permits_safety_gate and result.consent_status is not ConsentStatus.FRESH:
        findings.append(
            blocker_finding(
                "permission_gate_allowed_without_fresh_consent",
                "Permission gate cannot allow without fresh scoped consent.",
            )
        )

    if result.permits_safety_gate and result.authority_state is not (
        AuthorityState.SYSTEM_RECOMMENDATION_ONLY
    ):
        findings.append(
            blocker_finding(
                "permission_gate_misstates_authority",
                "Permission gate may only recommend; it cannot grant final authority.",
            )
        )

    if result.blocks_action and not result.required_next_steps:
        findings.append(
            warning_finding(
                "permission_gate_block_missing_next_steps",
                "Blocking permission result should preserve required next steps.",
            )
        )

    if result.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "permission_gate_confidence_below_target",
                "Permission gate confidence is below the target threshold.",
            )
        )

    return tuple(findings)
