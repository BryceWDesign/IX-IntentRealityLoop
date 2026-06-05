from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import (
    BoundedScore,
    EvidenceStatus,
    ValidationSeverity,
)
from ix_intent_reality_loop.delta import OutcomeDelta, OutcomeDeltaStatus
from ix_intent_reality_loop.memory import (
    MemoryBindingAction,
    MemoryBindingDecision,
    MemoryBindingReason,
    build_memory_binding_decision,
    validate_memory_binding_decision,
)


def _delta(
    *,
    status: OutcomeDeltaStatus,
    match_score: float,
    confidence: float,
    contradiction_reasons: tuple[str, ...] = (),
) -> OutcomeDelta:
    return OutcomeDelta(
        delta_id="delta-001",
        intent_id="intent-001",
        action_id="action-001",
        feedback_frame_id="feedback-001",
        status=status,
        predicted_outcome="Predicted bounded result.",
        observed_outcome="Observed bounded result.",
        match_score=BoundedScore(match_score),
        confidence=BoundedScore(confidence),
        doctrine_rule_codes=(
            "reality_gets_vote",
            "evidence_before_claim",
            "completion_not_output",
        ),
        contradiction_reasons=contradiction_reasons,
        required_next_steps=("review memory binding",),
    )


def test_build_memory_binding_decision_updates_matched_memory() -> None:
    decision = build_memory_binding_decision(
        memory_decision_id="memory-001",
        delta=_delta(
            status=OutcomeDeltaStatus.MATCHED,
            match_score=0.9,
            confidence=0.9,
        ),
        memory_keys=("bounded_step_result",),
    )

    assert decision.action is MemoryBindingAction.UPDATE
    assert decision.reason is MemoryBindingReason.MATCHED_OUTCOME
    assert decision.evidence_status is EvidenceStatus.COMPLETE
    assert decision.permits_positive_memory_update


def test_build_memory_binding_decision_downgrades_degraded_outcome() -> None:
    decision = build_memory_binding_decision(
        memory_decision_id="memory-002",
        delta=_delta(
            status=OutcomeDeltaStatus.DEGRADED,
            match_score=0.3,
            confidence=0.6,
        ),
        memory_keys=("partial_result",),
    )
    findings = validate_memory_binding_decision(decision)
    finding_codes = {finding.code for finding in findings}

    assert decision.action is MemoryBindingAction.DOWNGRADE
    assert decision.evidence_status is EvidenceStatus.DEGRADED
    assert decision.confidence_after_binding.value == 0.3
    assert "memory_downgraded" in finding_codes
    assert not decision.permits_positive_memory_update


def test_build_memory_binding_decision_quarantines_contradiction() -> None:
    decision = build_memory_binding_decision(
        memory_decision_id="memory-003",
        delta=_delta(
            status=OutcomeDeltaStatus.CONTRADICTED,
            match_score=0.0,
            confidence=0.8,
            contradiction_reasons=("simulated_position mismatch",),
        ),
        memory_keys=("unsafe_prediction",),
    )
    findings = validate_memory_binding_decision(decision)
    finding_codes = {finding.code for finding in findings}

    assert decision.action is MemoryBindingAction.QUARANTINE
    assert decision.reason is MemoryBindingReason.CONTRADICTED_OUTCOME
    assert decision.quarantines_memory
    assert "prediction_contradicted" in decision.quarantine_tags
    assert "memory_quarantined" in finding_codes


def test_build_memory_binding_decision_quarantines_blocked_no_action() -> None:
    decision = build_memory_binding_decision(
        memory_decision_id="memory-004",
        delta=_delta(
            status=OutcomeDeltaStatus.BLOCKED,
            match_score=0.0,
            confidence=0.0,
        ),
        memory_keys=("blocked_attempt",),
    )

    assert decision.action is MemoryBindingAction.QUARANTINE
    assert decision.reason is MemoryBindingReason.BLOCKED_NO_ACTION
    assert "no_action" in decision.quarantine_tags
    assert decision.confidence_after_binding.value == 0.0


def test_memory_binding_decision_rejects_empty_rationale() -> None:
    with pytest.raises(ValueError, match="rationale must not be empty"):
        MemoryBindingDecision(
            memory_decision_id="memory-005",
            intent_id="intent-001",
            delta_id="delta-001",
            action=MemoryBindingAction.UPDATE,
            reason=MemoryBindingReason.MATCHED_OUTCOME,
            evidence_status=EvidenceStatus.COMPLETE,
            confidence_after_binding=BoundedScore(0.9),
            rationale=" ",
            doctrine_rule_codes=("reality_gets_vote",),
        )


def test_memory_binding_decision_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        MemoryBindingDecision(
            memory_decision_id="memory-006",
            intent_id="intent-001",
            delta_id="delta-001",
            action=MemoryBindingAction.UPDATE,
            reason=MemoryBindingReason.MATCHED_OUTCOME,
            evidence_status=EvidenceStatus.COMPLETE,
            confidence_after_binding=BoundedScore(0.9),
            rationale="Memory update.",
            doctrine_rule_codes=("reality_gets_vote",),
            created_at=datetime(2026, 1, 1),
        )


def test_validate_memory_binding_decision_blocks_invalid_update() -> None:
    decision = MemoryBindingDecision(
        memory_decision_id="memory-007",
        intent_id="intent-001",
        delta_id="delta-001",
        action=MemoryBindingAction.UPDATE,
        reason=MemoryBindingReason.MATCHED_OUTCOME,
        evidence_status=EvidenceStatus.DEGRADED,
        confidence_after_binding=BoundedScore(0.9),
        rationale="Invalid update.",
        doctrine_rule_codes=(),
        memory_keys=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_memory_binding_decision(decision)
    finding_codes = {finding.code for finding in findings}

    assert "memory_missing_reality_doctrine" in finding_codes
    assert "memory_missing_evidence_doctrine" in finding_codes
    assert "memory_missing_completion_doctrine" in finding_codes
    assert "memory_update_missing_keys" in finding_codes
    assert "memory_update_without_complete_evidence" in finding_codes
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )


def test_validate_memory_binding_decision_blocks_invalid_quarantine() -> None:
    decision = MemoryBindingDecision(
        memory_decision_id="memory-008",
        intent_id="intent-001",
        delta_id="delta-001",
        action=MemoryBindingAction.QUARANTINE,
        reason=MemoryBindingReason.CONTRADICTED_OUTCOME,
        evidence_status=EvidenceStatus.REJECTED,
        confidence_after_binding=BoundedScore(0.0),
        rationale="Invalid quarantine.",
        doctrine_rule_codes=(
            "reality_gets_vote",
            "evidence_before_claim",
            "completion_not_output",
        ),
        quarantine_tags=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_memory_binding_decision(decision)
    finding_codes = {finding.code for finding in findings}

    assert "memory_quarantine_missing_tags" in finding_codes
    assert "memory_quarantined" in finding_codes
