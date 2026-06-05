from datetime import UTC, datetime, timedelta

import pytest

from ix_intent_reality_loop.arbiter import FourthEyeDecision
from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    ValidationSeverity,
)
from ix_intent_reality_loop.permission import (
    ConsentRecord,
    ConsentStatus,
    PermissionGateResult,
    PermissionScope,
    evaluate_permission_gate,
    validate_permission_gate_result,
)


def _decision(
    *,
    disposition: DecisionDisposition = DecisionDisposition.ALLOW,
    confidence: float = 0.9,
) -> FourthEyeDecision:
    return FourthEyeDecision(
        decision_id="arbiter-001",
        intent_id="intent-001",
        comparison_id="comparison-001",
        disposition=disposition,
        confidence=BoundedScore(confidence),
        rationale="Select lane for gated evaluation.",
        doctrine_rule_codes=("human_authority_persists", "completion_not_output"),
        selected_lane_id="lane-001",
        required_next_steps=("send to permission gate",),
    )


def test_consent_record_tracks_fresh_scoped_consent() -> None:
    granted_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-001",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.SIMULATED_ACTION,
        granted_at=granted_at,
        expires_at=granted_at + timedelta(minutes=10),
        constraints=("simulation only",),
    )

    assert consent.status_at(
        requested_scope=PermissionScope.SIMULATED_ACTION,
        checked_at=granted_at + timedelta(minutes=1),
    ) is ConsentStatus.FRESH
    assert consent.is_fresh_for(
        requested_scope=PermissionScope.SIMULATED_ACTION,
        checked_at=granted_at + timedelta(minutes=1),
    )


def test_consent_record_detects_stale_revoked_and_wrong_scope() -> None:
    granted_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-002",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.TEXT_OUTPUT,
        granted_at=granted_at,
        expires_at=granted_at + timedelta(minutes=5),
    )
    revoked = ConsentRecord(
        consent_id="consent-003",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.TEXT_OUTPUT,
        granted_at=granted_at,
        revoked=True,
    )

    assert consent.status_at(
        requested_scope=PermissionScope.TEXT_OUTPUT,
        checked_at=granted_at + timedelta(minutes=6),
    ) is ConsentStatus.STALE
    assert consent.status_at(
        requested_scope=PermissionScope.SIMULATED_ACTION,
        checked_at=granted_at + timedelta(minutes=1),
    ) is ConsentStatus.WRONG_SCOPE
    assert revoked.status_at(
        requested_scope=PermissionScope.TEXT_OUTPUT,
        checked_at=granted_at + timedelta(minutes=1),
    ) is ConsentStatus.REVOKED


def test_consent_record_rejects_invalid_expiration() -> None:
    granted_at = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="expires_at must be after granted_at"):
        ConsentRecord(
            consent_id="consent-004",
            intent_id="intent-001",
            granted_by="human-reviewer",
            scope=PermissionScope.TEXT_OUTPUT,
            granted_at=granted_at,
            expires_at=granted_at,
        )


def test_evaluate_permission_gate_allows_fresh_scoped_consent() -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-005",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.SIMULATED_ACTION,
        granted_at=checked_at,
        expires_at=checked_at + timedelta(minutes=5),
        constraints=("simulation only",),
    )

    result = evaluate_permission_gate(
        gate_id="permission-001",
        decision=_decision(),
        requested_scope=PermissionScope.SIMULATED_ACTION,
        consent=consent,
        checked_at=checked_at + timedelta(minutes=1),
    )

    assert result.disposition is DecisionDisposition.ALLOW
    assert result.consent_status is ConsentStatus.FRESH
    assert result.authority_state is AuthorityState.SYSTEM_RECOMMENDATION_ONLY
    assert result.permits_safety_gate
    assert result.preserved_constraints == ("simulation only",)


def test_evaluate_permission_gate_clamps_clamped_arbiter_decision() -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-006",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.TEXT_OUTPUT,
        granted_at=checked_at,
    )

    result = evaluate_permission_gate(
        gate_id="permission-002",
        decision=_decision(disposition=DecisionDisposition.CLAMP),
        requested_scope=PermissionScope.TEXT_OUTPUT,
        consent=consent,
        checked_at=checked_at,
    )

    assert result.disposition is DecisionDisposition.CLAMP
    assert result.permits_safety_gate


def test_evaluate_permission_gate_defers_without_consent() -> None:
    result = evaluate_permission_gate(
        gate_id="permission-003",
        decision=_decision(),
        requested_scope=PermissionScope.TEXT_OUTPUT,
        consent=None,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.disposition is DecisionDisposition.DEFER
    assert result.consent_status is ConsentStatus.ABSENT
    assert result.blocks_action


def test_evaluate_permission_gate_defers_stale_consent() -> None:
    granted_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-007",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.TEXT_OUTPUT,
        granted_at=granted_at,
        expires_at=granted_at + timedelta(minutes=5),
    )

    result = evaluate_permission_gate(
        gate_id="permission-004",
        decision=_decision(),
        requested_scope=PermissionScope.TEXT_OUTPUT,
        consent=consent,
        checked_at=granted_at + timedelta(minutes=6),
    )

    assert result.disposition is DecisionDisposition.DEFER
    assert result.consent_status is ConsentStatus.STALE
    assert result.blocks_action


def test_evaluate_permission_gate_refuses_live_physical_actuation() -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-008",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.LIVE_PHYSICAL_ACTUATION,
        granted_at=checked_at,
    )

    result = evaluate_permission_gate(
        gate_id="permission-005",
        decision=_decision(),
        requested_scope=PermissionScope.LIVE_PHYSICAL_ACTUATION,
        consent=consent,
        checked_at=checked_at,
    )
    findings = validate_permission_gate_result(result)

    assert result.disposition is DecisionDisposition.REFUSE
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )


def test_evaluate_permission_gate_safe_holds_blocked_arbiter_decision() -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-009",
        intent_id="intent-001",
        granted_by="human-reviewer",
        scope=PermissionScope.TEXT_OUTPUT,
        granted_at=checked_at,
    )

    result = evaluate_permission_gate(
        gate_id="permission-006",
        decision=_decision(disposition=DecisionDisposition.SAFE_HOLD),
        requested_scope=PermissionScope.TEXT_OUTPUT,
        consent=consent,
        checked_at=checked_at,
    )

    assert result.disposition is DecisionDisposition.SAFE_HOLD
    assert result.blocks_action


def test_evaluate_permission_gate_rejects_mismatched_intent() -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=UTC)
    consent = ConsentRecord(
        consent_id="consent-010",
        intent_id="intent-999",
        granted_by="human-reviewer",
        scope=PermissionScope.TEXT_OUTPUT,
        granted_at=checked_at,
    )

    with pytest.raises(ValueError, match="consent intent_id must match"):
        evaluate_permission_gate(
            gate_id="permission-007",
            decision=_decision(),
            requested_scope=PermissionScope.TEXT_OUTPUT,
            consent=consent,
            checked_at=checked_at,
        )


def test_validate_permission_gate_result_blocks_allowed_without_fresh_consent() -> None:
    result = PermissionGateResult(
        gate_id="permission-008",
        intent_id="intent-001",
        decision_id="arbiter-001",
        requested_scope=PermissionScope.TEXT_OUTPUT,
        consent_status=ConsentStatus.ABSENT,
        disposition=DecisionDisposition.ALLOW,
        authority_state=AuthorityState.HUMAN_ACCEPTED,
        confidence=BoundedScore(0.9),
        rationale="Invalid allow.",
        doctrine_rule_codes=(),
    )

    findings = validate_permission_gate_result(result)
    finding_codes = {finding.code for finding in findings}

    assert "permission_gate_missing_intent_doctrine" in finding_codes
    assert "permission_gate_missing_authority_doctrine" in finding_codes
    assert "permission_gate_allowed_without_fresh_consent" in finding_codes
    assert "permission_gate_misstates_authority" in finding_codes
