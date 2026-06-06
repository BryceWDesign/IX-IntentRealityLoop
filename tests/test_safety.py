from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    ValidationSeverity,
)
from ix_intent_reality_loop.permission import (
    ConsentStatus,
    PermissionGateResult,
    PermissionScope,
)
from ix_intent_reality_loop.safety import (
    InteractionState,
    SafetyGateResult,
    SafetyLevel,
    SafetyMap,
    SafetySignal,
    evaluate_safety_gate,
    validate_safety_gate_result,
)


def _permission_result(
    *,
    requested_scope: PermissionScope = PermissionScope.SIMULATED_ACTION,
    disposition: DecisionDisposition = DecisionDisposition.ALLOW,
    confidence: float = 0.9,
) -> PermissionGateResult:
    return PermissionGateResult(
        gate_id="permission-001",
        intent_id="intent-001",
        decision_id="arbiter-001",
        requested_scope=requested_scope,
        consent_status=ConsentStatus.FRESH,
        disposition=disposition,
        authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
        confidence=BoundedScore(confidence),
        rationale="Permission accepted for evaluation.",
        doctrine_rule_codes=("intent_not_permission", "human_authority_persists"),
        consent_id="consent-001",
        required_next_steps=("send to safety gate",),
    )


def _safety_map(
    *,
    level: SafetyLevel = SafetyLevel.GREEN,
    is_blocking: bool = False,
) -> SafetyMap:
    return SafetyMap(
        map_id="safety-map-001",
        intent_id="intent-001",
        signals=(
            SafetySignal(
                code="workspace_clear",
                level=level,
                message="Workspace safety signal.",
                is_blocking=is_blocking,
            ),
        ),
    )


def test_safety_map_tracks_worst_level_and_blockers() -> None:
    safety_map = SafetyMap(
        map_id="safety-map-002",
        intent_id="intent-001",
        signals=(
            SafetySignal(
                code="workspace_clear",
                level=SafetyLevel.GREEN,
                message="Workspace is clear.",
            ),
            SafetySignal(
                code="thermal_unknown",
                level=SafetyLevel.UNKNOWN,
                message="Thermal state is unknown.",
            ),
        ),
    )

    assert safety_map.worst_level is SafetyLevel.UNKNOWN
    assert safety_map.has_blocking_signal
    assert safety_map.signal_codes == ("workspace_clear", "thermal_unknown")


def test_evaluate_safety_gate_allows_green_text_output() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-001",
        permission_result=_permission_result(
            requested_scope=PermissionScope.TEXT_OUTPUT,
        ),
        safety_map=_safety_map(),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.ALLOW
    assert result.interaction_state is InteractionState.TEXT_ONLY
    assert result.permits_reality_feedback


def test_evaluate_safety_gate_allows_green_simulated_action() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-002",
        permission_result=_permission_result(
            requested_scope=PermissionScope.SIMULATED_ACTION,
        ),
        safety_map=_safety_map(),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.ALLOW
    assert result.interaction_state is InteractionState.SIMULATED_ACTION
    assert result.confidence.value == 0.9


def test_evaluate_safety_gate_uses_bounded_contact_review_state() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-003",
        permission_result=_permission_result(
            requested_scope=PermissionScope.BOUNDED_CONTACT_REVIEW,
        ),
        safety_map=_safety_map(),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.ALLOW
    assert result.interaction_state is InteractionState.BOUNDED_CONTACT_REVIEW


def test_evaluate_safety_gate_clamps_yellow_safety_signal() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-004",
        permission_result=_permission_result(),
        safety_map=_safety_map(level=SafetyLevel.YELLOW),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.CLAMP
    assert result.interaction_state is InteractionState.VERIFY
    assert result.confidence.value == 0.75
    assert result.permits_reality_feedback


def test_evaluate_safety_gate_safe_holds_red_signal() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-005",
        permission_result=_permission_result(),
        safety_map=_safety_map(level=SafetyLevel.RED),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    findings = validate_safety_gate_result(result)

    assert result.disposition is DecisionDisposition.SAFE_HOLD
    assert result.interaction_state is InteractionState.EMERGENCY_RETREAT
    assert result.blocks_action
    assert any(finding.severity is ValidationSeverity.WARNING for finding in findings)


def test_evaluate_safety_gate_safe_holds_blocking_signal() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-006",
        permission_result=_permission_result(),
        safety_map=_safety_map(level=SafetyLevel.YELLOW, is_blocking=True),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.SAFE_HOLD
    assert result.interaction_state is InteractionState.SAFE_HOLD


def test_evaluate_safety_gate_safe_holds_blocked_permission_result() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-007",
        permission_result=_permission_result(
            disposition=DecisionDisposition.DEFER,
            confidence=0.0,
        ),
        safety_map=_safety_map(),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.SAFE_HOLD
    assert result.interaction_state is InteractionState.SAFE_HOLD
    assert result.blocks_action


def test_evaluate_safety_gate_refuses_live_physical_actuation() -> None:
    result = evaluate_safety_gate(
        gate_id="safety-008",
        permission_result=_permission_result(
            requested_scope=PermissionScope.LIVE_PHYSICAL_ACTUATION,
        ),
        safety_map=_safety_map(),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    findings = validate_safety_gate_result(result)
    finding_codes = {finding.code for finding in findings}

    assert result.disposition is DecisionDisposition.REFUSE
    assert result.interaction_state is InteractionState.EMERGENCY_RETREAT
    assert "safety_gate_confidence_below_target" in finding_codes


def test_evaluate_safety_gate_rejects_mismatched_intent() -> None:
    safety_map = SafetyMap(
        map_id="safety-map-003",
        intent_id="intent-999",
        signals=(
            SafetySignal(
                code="workspace_clear",
                level=SafetyLevel.GREEN,
                message="Workspace clear.",
            ),
        ),
    )

    with pytest.raises(ValueError, match="safety map intent_id must match"):
        evaluate_safety_gate(
            gate_id="safety-009",
            permission_result=_permission_result(),
            safety_map=safety_map,
            checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_validate_safety_gate_result_blocks_invalid_allow() -> None:
    result = SafetyGateResult(
        gate_id="safety-010",
        intent_id="intent-001",
        permission_gate_id="permission-001",
        safety_map_id="safety-map-001",
        safety_level=SafetyLevel.RED,
        disposition=DecisionDisposition.ALLOW,
        interaction_state=InteractionState.EMERGENCY_RETREAT,
        confidence=BoundedScore(0.9),
        rationale="Invalid allow.",
        doctrine_rule_codes=(),
        preserved_signal_codes=(),
    )

    findings = validate_safety_gate_result(result)
    finding_codes = {finding.code for finding in findings}

    assert "safety_gate_missing_reality_doctrine" in finding_codes
    assert "safety_gate_missing_completion_doctrine" in finding_codes
    assert "safety_gate_allows_blocking_safety_level" in finding_codes
    assert "safety_gate_allows_emergency_retreat" in finding_codes
    assert "safety_gate_missing_preserved_signals" in finding_codes
