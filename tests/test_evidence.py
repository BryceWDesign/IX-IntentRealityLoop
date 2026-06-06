from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import (
    BoundedScore,
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
)
from ix_intent_reality_loop.evidence import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceItemKind,
    build_evidence_bundle,
    validate_evidence_bundle,
)
from ix_intent_reality_loop.memory import MemoryBindingAction
from ix_intent_reality_loop.memory_ledger import MemoryLedger, MemoryLedgerEntry
from ix_intent_reality_loop.replay import (
    ReplayEvent,
    ReplayEventLog,
    ReplayEventType,
    build_replay_event,
    required_replay_event_sequence,
)


def _event(
    *,
    event_id: str,
    event_type: ReplayEventType,
) -> ReplayEvent:
    return build_replay_event(
        event_id=event_id,
        intent_id="intent-001",
        event_type=event_type,
        subject_id=f"{event_type.value}-subject",
        summary=f"{event_type.value} summary.",
        payload={"event_type": event_type.value},
    )


def _complete_replay_log() -> ReplayEventLog:
    return ReplayEventLog(
        log_id="replay-001",
        intent_id="intent-001",
        events=tuple(
            _event(event_id=f"event-{index:03d}", event_type=event_type)
            for index, event_type in enumerate(
                required_replay_event_sequence(),
                start=1,
            )
        ),
    )


def _ledger() -> MemoryLedger:
    return MemoryLedger(
        ledger_id="ledger-001",
        entries=(
            MemoryLedgerEntry(
                entry_id="ledger-entry-001",
                memory_decision_id="memory-001",
                intent_id="intent-001",
                action=MemoryBindingAction.UPDATE,
                memory_keys=("bounded_result",),
                confidence_after_binding=BoundedScore(0.91),
                summary="Matched outcome supports bounded memory update.",
            ),
        ),
    )


def test_evidence_item_rejects_empty_summary() -> None:
    with pytest.raises(ValueError, match="summary must not be empty"):
        EvidenceItem(
            item_id="item-001",
            kind=EvidenceItemKind.REPLAY_LOG,
            subject_id="replay-001",
            summary=" ",
            status=EvidenceStatus.COMPLETE,
        )


def test_evidence_bundle_preserves_findings_and_counts() -> None:
    bundle = EvidenceBundle(
        bundle_id="bundle-001",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        narrative_summary="Bounded evidence bundle.",
        status=EvidenceStatus.DEGRADED,
        items=(
            EvidenceItem(
                item_id="item-002",
                kind=EvidenceItemKind.VALIDATION_FINDING,
                subject_id="finding",
                summary="Warning finding.",
                status=EvidenceStatus.DEGRADED,
            ),
        ),
        findings=(
            ValidationFinding(
                code="warning",
                message="Warning finding.",
                severity=ValidationSeverity.WARNING,
            ),
        ),
        doctrine_rule_codes=("evidence_before_claim",),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert bundle.warning_count == 1
    assert bundle.blocker_count == 0
    assert not bundle.is_review_ready


def test_evidence_bundle_rejects_duplicate_item_ids() -> None:
    item = EvidenceItem(
        item_id="duplicate",
        kind=EvidenceItemKind.REPLAY_LOG,
        subject_id="replay-001",
        summary="Replay log.",
        status=EvidenceStatus.COMPLETE,
    )

    with pytest.raises(ValueError, match="unique item_id"):
        EvidenceBundle(
            bundle_id="bundle-002",
            intent_id="intent-001",
            replay_log_id="replay-001",
            memory_ledger_id="ledger-001",
            narrative_summary="Bounded evidence bundle.",
            status=EvidenceStatus.COMPLETE,
            items=(item, item),
            findings=(),
            doctrine_rule_codes=("evidence_before_claim",),
        )


def test_evidence_bundle_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        EvidenceBundle(
            bundle_id="bundle-003",
            intent_id="intent-001",
            replay_log_id="replay-001",
            memory_ledger_id="ledger-001",
            narrative_summary="Bounded evidence bundle.",
            status=EvidenceStatus.COMPLETE,
            items=(),
            findings=(),
            doctrine_rule_codes=("evidence_before_claim",),
            created_at=datetime(2026, 1, 1),
        )


def test_build_evidence_bundle_collects_replay_and_ledger_items() -> None:
    bundle = build_evidence_bundle(
        bundle_id="bundle-004",
        replay_log=_complete_replay_log(),
        memory_ledger=_ledger(),
        narrative_summary="Bounded agency-loop evidence bundle.",
    )
    findings = validate_evidence_bundle(bundle)
    finding_codes = {finding.code for finding in findings}

    assert bundle.status is EvidenceStatus.DEGRADED
    assert bundle.warning_count == 1
    assert bundle.blocker_count == 0
    assert not bundle.is_review_ready
    assert "replay_log_missing_memory_ledger_snapshot" in (
        finding.code for finding in bundle.findings
    )
    assert "evidence_bundle_degraded" in finding_codes


def test_build_evidence_bundle_rejects_prohibited_claims() -> None:
    bundle = build_evidence_bundle(
        bundle_id="bundle-005",
        replay_log=_complete_replay_log(),
        memory_ledger=_ledger(),
        narrative_summary="This evidence proves certified AGI.",
    )

    assert bundle.status is EvidenceStatus.REJECTED
    assert bundle.blocker_count == 1
    assert not bundle.is_review_ready


def test_build_evidence_bundle_blocks_incomplete_replay_log() -> None:
    replay_log = ReplayEventLog(
        log_id="replay-002",
        intent_id="intent-001",
        events=(
            _event(
                event_id="event-001",
                event_type=ReplayEventType.INTENT_PACKET,
            ),
        ),
    )

    bundle = build_evidence_bundle(
        bundle_id="bundle-006",
        replay_log=replay_log,
        memory_ledger=_ledger(),
        narrative_summary="Incomplete replay evidence bundle.",
    )

    assert bundle.status is EvidenceStatus.REJECTED
    assert bundle.blocker_count > 0


def test_validate_evidence_bundle_blocks_missing_doctrine_and_items() -> None:
    bundle = EvidenceBundle(
        bundle_id="bundle-007",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        narrative_summary="Invalid evidence bundle.",
        status=EvidenceStatus.COMPLETE,
        items=(),
        findings=(
            ValidationFinding(
                code="blocker",
                message="Blocker finding.",
                severity=ValidationSeverity.BLOCKER,
            ),
        ),
        doctrine_rule_codes=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_evidence_bundle(bundle)
    finding_codes = {finding.code for finding in findings}

    assert "evidence_bundle_missing_evidence_doctrine" in finding_codes
    assert "evidence_bundle_missing_completion_doctrine" in finding_codes
    assert "evidence_bundle_missing_no_agi_doctrine" in finding_codes
    assert "evidence_bundle_missing_items" in finding_codes
    assert "evidence_bundle_complete_with_blockers" in finding_codes
