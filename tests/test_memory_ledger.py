from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import (
    BoundedScore,
    EvidenceStatus,
    ValidationSeverity,
)
from ix_intent_reality_loop.memory import (
    MemoryBindingAction,
    MemoryBindingDecision,
    MemoryBindingReason,
)
from ix_intent_reality_loop.memory_ledger import (
    MemoryLedger,
    MemoryLedgerEntry,
    apply_memory_binding_decision,
    build_memory_ledger_entry,
    validate_memory_ledger,
)


def _decision(
    *,
    action: MemoryBindingAction,
    confidence: float,
    memory_keys: tuple[str, ...] = ("bounded_result",),
    quarantine_tags: tuple[str, ...] = (),
) -> MemoryBindingDecision:
    return MemoryBindingDecision(
        memory_decision_id="memory-001",
        intent_id="intent-001",
        delta_id="delta-001",
        action=action,
        reason=(
            MemoryBindingReason.MATCHED_OUTCOME
            if action is MemoryBindingAction.UPDATE
            else MemoryBindingReason.CONTRADICTED_OUTCOME
        ),
        evidence_status=(
            EvidenceStatus.COMPLETE
            if action is MemoryBindingAction.UPDATE
            else EvidenceStatus.REJECTED
        ),
        confidence_after_binding=BoundedScore(confidence),
        rationale="Memory binding decision.",
        doctrine_rule_codes=(
            "reality_gets_vote",
            "evidence_before_claim",
            "completion_not_output",
        ),
        memory_keys=memory_keys,
        quarantine_tags=quarantine_tags,
    )


def test_build_memory_ledger_entry_preserves_decision_fields() -> None:
    decision = _decision(
        action=MemoryBindingAction.UPDATE,
        confidence=0.91,
    )

    entry = build_memory_ledger_entry(
        entry_id="ledger-entry-001",
        decision=decision,
    )

    assert entry.action is MemoryBindingAction.UPDATE
    assert entry.is_positive_update
    assert not entry.is_quarantined
    assert entry.memory_keys == ("bounded_result",)


def test_apply_memory_binding_decision_returns_new_ledger_snapshot() -> None:
    ledger = MemoryLedger(ledger_id="ledger-001")
    decision = _decision(
        action=MemoryBindingAction.UPDATE,
        confidence=0.91,
    )

    updated = apply_memory_binding_decision(
        ledger=ledger,
        entry_id="ledger-entry-002",
        decision=decision,
    )

    assert ledger.entries == ()
    assert len(updated.entries) == 1
    assert updated.positive_update_count == 1


def test_memory_ledger_groups_entries_by_memory_key() -> None:
    entry_one = MemoryLedgerEntry(
        entry_id="ledger-entry-003",
        memory_decision_id="memory-001",
        intent_id="intent-001",
        action=MemoryBindingAction.UPDATE,
        memory_keys=("shared", "first"),
        confidence_after_binding=BoundedScore(0.9),
        summary="First update.",
    )
    entry_two = MemoryLedgerEntry(
        entry_id="ledger-entry-004",
        memory_decision_id="memory-002",
        intent_id="intent-001",
        action=MemoryBindingAction.DOWNGRADE,
        memory_keys=("shared", "second"),
        confidence_after_binding=BoundedScore(0.4),
        summary="Second downgrade.",
    )

    ledger = MemoryLedger(
        ledger_id="ledger-002",
        entries=(entry_one, entry_two),
    )

    grouped = ledger.by_memory_key()

    assert tuple(entry.entry_id for entry in grouped["shared"]) == (
        "ledger-entry-003",
        "ledger-entry-004",
    )
    with pytest.raises(TypeError):
        grouped["new"] = (entry_one,)  # type: ignore[index]


def test_memory_ledger_tracks_quarantine_tags() -> None:
    entry = MemoryLedgerEntry(
        entry_id="ledger-entry-005",
        memory_decision_id="memory-003",
        intent_id="intent-001",
        action=MemoryBindingAction.QUARANTINE,
        memory_keys=("contradicted_prediction",),
        confidence_after_binding=BoundedScore(0.0),
        summary="Quarantine contradicted prediction.",
        quarantine_tags=("prediction_contradicted",),
    )

    ledger = MemoryLedger(ledger_id="ledger-003", entries=(entry,))

    assert ledger.quarantine_count == 1
    assert ledger.quarantine_tags() == frozenset({"prediction_contradicted"})


def test_memory_ledger_rejects_duplicate_entry_ids() -> None:
    entry = MemoryLedgerEntry(
        entry_id="duplicate",
        memory_decision_id="memory-004",
        intent_id="intent-001",
        action=MemoryBindingAction.UPDATE,
        memory_keys=("result",),
        confidence_after_binding=BoundedScore(0.9),
        summary="Update.",
    )

    with pytest.raises(ValueError, match="unique entry_id"):
        MemoryLedger(ledger_id="ledger-004", entries=(entry, entry))


def test_memory_ledger_entry_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        MemoryLedgerEntry(
            entry_id="ledger-entry-006",
            memory_decision_id="memory-005",
            intent_id="intent-001",
            action=MemoryBindingAction.UPDATE,
            memory_keys=("result",),
            confidence_after_binding=BoundedScore(0.9),
            summary="Update.",
            created_at=datetime(2026, 1, 1),
        )


def test_validate_memory_ledger_warns_when_empty() -> None:
    findings = validate_memory_ledger(MemoryLedger(ledger_id="ledger-005"))

    assert findings[0].code == "memory_ledger_empty"


def test_validate_memory_ledger_blocks_invalid_positive_update() -> None:
    entry = MemoryLedgerEntry(
        entry_id="ledger-entry-007",
        memory_decision_id="memory-006",
        intent_id="intent-001",
        action=MemoryBindingAction.UPDATE,
        memory_keys=(),
        confidence_after_binding=BoundedScore(0.6),
        summary="Invalid update.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_memory_ledger(
        MemoryLedger(ledger_id="ledger-006", entries=(entry,))
    )
    finding_codes = {finding.code for finding in findings}

    assert "memory_ledger_update_missing_keys" in finding_codes
    assert "memory_ledger_update_below_confidence_threshold" in finding_codes
    assert any(finding.severity is ValidationSeverity.BLOCKER for finding in findings)


def test_validate_memory_ledger_warns_for_quarantine_and_downgrade() -> None:
    quarantine_entry = MemoryLedgerEntry(
        entry_id="ledger-entry-008",
        memory_decision_id="memory-007",
        intent_id="intent-001",
        action=MemoryBindingAction.QUARANTINE,
        memory_keys=("contradiction",),
        confidence_after_binding=BoundedScore(0.0),
        summary="Quarantine.",
        quarantine_tags=("prediction_contradicted",),
    )
    downgrade_entry = MemoryLedgerEntry(
        entry_id="ledger-entry-009",
        memory_decision_id="memory-008",
        intent_id="intent-001",
        action=MemoryBindingAction.DOWNGRADE,
        memory_keys=("partial",),
        confidence_after_binding=BoundedScore(0.3),
        summary="Downgrade.",
    )

    findings = validate_memory_ledger(
        MemoryLedger(
            ledger_id="ledger-007",
            entries=(quarantine_entry, downgrade_entry),
        )
    )
    finding_codes = {finding.code for finding in findings}

    assert "memory_ledger_contains_quarantine" in finding_codes
    assert "memory_ledger_contains_downgrade" in finding_codes
