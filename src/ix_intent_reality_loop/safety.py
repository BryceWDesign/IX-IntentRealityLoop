"""Safety map and risk state gate.

Permission is still not safety. This layer evaluates whether a permission-gated
decision can proceed into text output, simulated action, bounded contact review,
retreat, or safe-hold. It intentionally refuses live physical actuation and
keeps IX-IntentRealityLoop inside evaluation boundaries.
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
from ix_intent_reality_loop.permission import PermissionGateResult, PermissionScope


class SafetyLevel(StrEnum):
    """Safety-map level inspired by bounded contact review systems."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"


class InteractionState(StrEnum):
    """Bounded interaction state after safety evaluation."""

    TEXT_ONLY = "text_only"
    VERIFY = "verify"
    SIMULATED_ACTION = "simulated_action"
    BOUNDED_CONTACT_REVIEW = "bounded_contact_review"
    RETREAT = "retreat"
    EMERGENCY_RETREAT = "emergency_retreat"
    SAFE_HOLD = "safe_hold"


@dataclass(frozen=True, slots=True)
class SafetySignal:
    """One safety signal contributing to a safety map."""

    code: str
    level: SafetyLevel
    message: str
    is_blocking: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_non_empty_text(self.code, "code"))
        object.__setattr__(
            self,
            "message",
            require_non_empty_text(self.message, "message"),
        )


@dataclass(frozen=True, slots=True)
class SafetyMap:
    """Safety map for the selected permission-gated intent."""

    map_id: str
    intent_id: str
    signals: tuple[SafetySignal, ...]
    baseline_level: SafetyLevel = SafetyLevel.GREEN
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "map_id",
            require_non_empty_text(self.map_id, "map_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        if not self.signals:
            raise ValueError("signals must not be empty")
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def worst_level(self) -> SafetyLevel:
        """Return the worst safety level across baseline and signals."""

        priority = {
            SafetyLevel.GREEN: 0,
            SafetyLevel.YELLOW: 1,
            SafetyLevel.RED: 2,
            SafetyLevel.UNKNOWN: 3,
        }
        worst = self.baseline_level
        for signal in self.signals:
            if priority[signal.level] > priority[worst]:
                worst = signal.level
        return worst

    @property
    def has_blocking_signal(self) -> bool:
        """Return whether any signal blocks action."""

        return any(
            signal.is_blocking
            or signal.level in {SafetyLevel.RED, SafetyLevel.UNKNOWN}
            for signal in self.signals
        )

    @property
    def signal_codes(self) -> tuple[str, ...]:
        """Return safety signal codes in recorded order."""

        return tuple(signal.code for signal in self.signals)


@dataclass(frozen=True, slots=True)
class SafetyGateResult:
    """Result of safety gating before reality feedback."""

    gate_id: str
    intent_id: str
    permission_gate_id: str
    safety_map_id: str
    safety_level: SafetyLevel
    disposition: DecisionDisposition
    interaction_state: InteractionState
    confidence: BoundedScore
    rationale: str
    doctrine_rule_codes: tuple[str, ...]
    preserved_signal_codes: tuple[str, ...]
    required_next_steps: tuple[str, ...] = ()
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
            "permission_gate_id",
            require_non_empty_text(self.permission_gate_id, "permission_gate_id"),
        )
        object.__setattr__(
            self,
            "safety_map_id",
            require_non_empty_text(self.safety_map_id, "safety_map_id"),
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
            "preserved_signal_codes",
            tuple(
                require_non_empty_text(code, "preserved_signal_code")
                for code in self.preserved_signal_codes
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
    def permits_reality_feedback(self) -> bool:
        """Return whether the result can proceed to feedback simulation."""

        return self.disposition in {
            DecisionDisposition.ALLOW,
            DecisionDisposition.CLAMP,
        }

    @property
    def blocks_action(self) -> bool:
        """Return whether safety gate prevents action-like evaluation."""

        return self.disposition in {
            DecisionDisposition.DEFER,
            DecisionDisposition.REFUSE,
            DecisionDisposition.ESCALATE,
            DecisionDisposition.SAFE_HOLD,
        }


def evaluate_safety_gate(
    *,
    gate_id: str,
    permission_result: PermissionGateResult,
    safety_map: SafetyMap,
    checked_at: datetime | None = None,
) -> SafetyGateResult:
    """Evaluate safety state for a permission-gated decision."""

    check_time = utc_now() if checked_at is None else require_aware_utc(
        checked_at,
        "checked_at",
    )
    if safety_map.intent_id != permission_result.intent_id:
        raise ValueError("safety map intent_id must match permission result intent_id")

    doctrine_rule_codes = (
        "thought_not_action",
        "intent_not_permission",
        "reality_gets_vote",
        "human_authority_persists",
        "completion_not_output",
    )

    if permission_result.blocks_action:
        return SafetyGateResult(
            gate_id=gate_id,
            intent_id=permission_result.intent_id,
            permission_gate_id=permission_result.gate_id,
            safety_map_id=safety_map.map_id,
            safety_level=safety_map.worst_level,
            disposition=DecisionDisposition.SAFE_HOLD,
            interaction_state=InteractionState.SAFE_HOLD,
            confidence=BoundedScore(0.0),
            rationale="Safety gate safe-held because permission gate blocks action.",
            doctrine_rule_codes=doctrine_rule_codes,
            preserved_signal_codes=safety_map.signal_codes,
            required_next_steps=("resolve permission gate before safety progression",),
            created_at=check_time,
        )

    if permission_result.requested_scope is PermissionScope.LIVE_PHYSICAL_ACTUATION:
        return SafetyGateResult(
            gate_id=gate_id,
            intent_id=permission_result.intent_id,
            permission_gate_id=permission_result.gate_id,
            safety_map_id=safety_map.map_id,
            safety_level=safety_map.worst_level,
            disposition=DecisionDisposition.REFUSE,
            interaction_state=InteractionState.EMERGENCY_RETREAT,
            confidence=BoundedScore(0.0),
            rationale="Safety gate refuses live physical actuation.",
            doctrine_rule_codes=doctrine_rule_codes,
            preserved_signal_codes=safety_map.signal_codes,
            required_next_steps=("return to simulation or text-only evaluation",),
            created_at=check_time,
        )

    if safety_map.has_blocking_signal:
        return SafetyGateResult(
            gate_id=gate_id,
            intent_id=permission_result.intent_id,
            permission_gate_id=permission_result.gate_id,
            safety_map_id=safety_map.map_id,
            safety_level=safety_map.worst_level,
            disposition=DecisionDisposition.SAFE_HOLD,
            interaction_state=(
                InteractionState.EMERGENCY_RETREAT
                if safety_map.worst_level is SafetyLevel.RED
                else InteractionState.SAFE_HOLD
            ),
            confidence=BoundedScore(0.0),
            rationale="Safety gate safe-held because blocking safety signals exist.",
            doctrine_rule_codes=doctrine_rule_codes,
            preserved_signal_codes=safety_map.signal_codes,
            required_next_steps=("clear or downgrade blocking safety signals",),
            created_at=check_time,
        )

    if safety_map.worst_level is SafetyLevel.YELLOW:
        return SafetyGateResult(
            gate_id=gate_id,
            intent_id=permission_result.intent_id,
            permission_gate_id=permission_result.gate_id,
            safety_map_id=safety_map.map_id,
            safety_level=safety_map.worst_level,
            disposition=DecisionDisposition.CLAMP,
            interaction_state=InteractionState.VERIFY,
            confidence=BoundedScore(min(permission_result.confidence.value, 0.75)),
            rationale="Safety gate clamped because yellow safety signals require verify.",
            doctrine_rule_codes=doctrine_rule_codes,
            preserved_signal_codes=safety_map.signal_codes,
            required_next_steps=("verify yellow safety signal before feedback loop",),
            created_at=check_time,
        )

    if permission_result.requested_scope is PermissionScope.TEXT_OUTPUT:
        interaction_state = InteractionState.TEXT_ONLY
    elif permission_result.requested_scope is PermissionScope.SIMULATED_ACTION:
        interaction_state = InteractionState.SIMULATED_ACTION
    else:
        interaction_state = InteractionState.BOUNDED_CONTACT_REVIEW

    disposition = (
        DecisionDisposition.CLAMP
        if permission_result.disposition is DecisionDisposition.CLAMP
        else DecisionDisposition.ALLOW
    )

    return SafetyGateResult(
        gate_id=gate_id,
        intent_id=permission_result.intent_id,
        permission_gate_id=permission_result.gate_id,
        safety_map_id=safety_map.map_id,
        safety_level=safety_map.worst_level,
        disposition=disposition,
        interaction_state=interaction_state,
        confidence=permission_result.confidence,
        rationale="Safety gate accepted green safety map for evaluation path.",
        doctrine_rule_codes=doctrine_rule_codes,
        preserved_signal_codes=safety_map.signal_codes,
        required_next_steps=("send safety-approved path to feedback simulation",),
        created_at=check_time,
    )


def validate_safety_gate_result(
    result: SafetyGateResult,
) -> tuple[ValidationFinding, ...]:
    """Validate safety gate output before reality feedback."""

    findings: list[ValidationFinding] = []

    if "reality_gets_vote" not in result.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "safety_gate_missing_reality_doctrine",
                "Safety gate must cite reality_gets_vote doctrine.",
            )
        )

    if "completion_not_output" not in result.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "safety_gate_missing_completion_doctrine",
                "Safety gate must not treat safety approval as completion.",
            )
        )

    if result.safety_level in {SafetyLevel.RED, SafetyLevel.UNKNOWN} and (
        result.permits_reality_feedback
    ):
        findings.append(
            blocker_finding(
                "safety_gate_allows_blocking_safety_level",
                "Safety gate cannot allow red or unknown safety levels.",
            )
        )

    if result.interaction_state is InteractionState.EMERGENCY_RETREAT and (
        result.permits_reality_feedback
    ):
        findings.append(
            blocker_finding(
                "safety_gate_allows_emergency_retreat",
                "Emergency retreat cannot proceed as an allowed feedback path.",
            )
        )

    if result.permits_reality_feedback and not result.preserved_signal_codes:
        findings.append(
            blocker_finding(
                "safety_gate_missing_preserved_signals",
                "Safety-approved paths must preserve safety signal evidence.",
            )
        )

    if result.blocks_action and not result.required_next_steps:
        findings.append(
            warning_finding(
                "safety_gate_block_missing_next_steps",
                "Blocking safety result should preserve required next steps.",
            )
        )

    if result.confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "safety_gate_confidence_below_target",
                "Safety gate confidence is below the target threshold.",
            )
        )

    return tuple(findings)
