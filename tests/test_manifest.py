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
)
from ix_intent_reality_loop.manifest import (
    DigestAlgorithm,
    DigestRecord,
    ReplayManifest,
    build_digest_record,
    build_replay_manifest,
    validate_replay_manifest,
)


def _bundle(*, status: EvidenceStatus = EvidenceStatus.COMPLETE) -> EvidenceBundle:
    return EvidenceBundle(
        bundle_id="bundle-001",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        narrative_summary="Bounded agency-loop evidence bundle.",
        status=status,
        items=(
            EvidenceItem(
                item_id="item-001",
                kind=EvidenceItemKind.REPLAY_LOG,
                subject_id="replay-001",
                summary="Replay log included.",
                status=EvidenceStatus.COMPLETE,
            ),
            EvidenceItem(
                item_id="item-002",
                kind=EvidenceItemKind.MEMORY_LEDGER,
                subject_id="ledger-001",
                summary="Memory ledger included.",
                status=EvidenceStatus.COMPLETE,
            ),
        ),
        findings=(
            ()
            if status is EvidenceStatus.COMPLETE
            else (
                ValidationFinding(
                    code="bundle_warning",
                    message="Bundle requires review.",
                    severity=ValidationSeverity.WARNING,
                ),
            )
        ),
        doctrine_rule_codes=(
            "evidence_before_claim",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        required_next_steps=("prepare digest-bound replay manifest",),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_digest_record_requires_sha256_length_and_hex() -> None:
    DigestRecord(
        subject_id="subject-001",
        subject_kind="test",
        algorithm=DigestAlgorithm.SHA256,
        digest_hex="a" * 64,
    )

    with pytest.raises(ValueError, match="64 hexadecimal"):
        DigestRecord(
            subject_id="subject-002",
            subject_kind="test",
            algorithm=DigestAlgorithm.SHA256,
            digest_hex="a" * 63,
        )

    with pytest.raises(ValueError, match="hexadecimal"):
        DigestRecord(
            subject_id="subject-003",
            subject_kind="test",
            algorithm=DigestAlgorithm.SHA256,
            digest_hex="z" * 64,
        )


def test_build_digest_record_is_stable_for_same_payload_order() -> None:
    first = build_digest_record(
        subject_id="subject-004",
        subject_kind="payload",
        payload={"b": "two", "a": "one", "score": 1},
    )
    second = build_digest_record(
        subject_id="subject-004",
        subject_kind="payload",
        payload={"score": 1, "a": "one", "b": "two"},
    )

    assert first.digest_hex == second.digest_hex
    assert first.algorithm is DigestAlgorithm.SHA256


def test_build_replay_manifest_binds_bundle_items_and_findings() -> None:
    manifest = build_replay_manifest(
        manifest_id="manifest-001",
        bundle=_bundle(),
    )

    assert manifest.bundle_id == "bundle-001"
    assert manifest.bundle_digest.subject_id == "bundle-001"
    assert len(manifest.item_digests) == 2
    assert len(manifest.finding_digests) == 0
    assert manifest.digest_count == 3
    assert manifest.is_review_ready


def test_build_replay_manifest_preserves_degraded_bundle_status() -> None:
    manifest = build_replay_manifest(
        manifest_id="manifest-002",
        bundle=_bundle(status=EvidenceStatus.DEGRADED),
    )
    findings = validate_replay_manifest(manifest)
    finding_codes = {finding.code for finding in findings}

    assert manifest.bundle_status is EvidenceStatus.DEGRADED
    assert len(manifest.finding_digests) == 1
    assert not manifest.is_review_ready
    assert "manifest_degraded_bundle" in finding_codes
    assert "manifest_not_review_ready" in finding_codes


def test_replay_manifest_rejects_duplicate_item_digest_subjects() -> None:
    digest = DigestRecord(
        subject_id="item-duplicate",
        subject_kind="evidence_item",
        algorithm=DigestAlgorithm.SHA256,
        digest_hex="a" * 64,
    )

    with pytest.raises(ValueError, match="unique subject_id"):
        ReplayManifest(
            manifest_id="manifest-003",
            bundle_id="bundle-001",
            intent_id="intent-001",
            replay_log_id="replay-001",
            memory_ledger_id="ledger-001",
            bundle_status=EvidenceStatus.COMPLETE,
            bundle_digest=DigestRecord(
                subject_id="bundle-001",
                subject_kind="evidence_bundle",
                algorithm=DigestAlgorithm.SHA256,
                digest_hex="b" * 64,
            ),
            item_digests=(digest, digest),
            finding_digests=(),
            doctrine_rule_codes=("evidence_before_claim",),
        )


def test_replay_manifest_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        ReplayManifest(
            manifest_id="manifest-004",
            bundle_id="bundle-001",
            intent_id="intent-001",
            replay_log_id="replay-001",
            memory_ledger_id="ledger-001",
            bundle_status=EvidenceStatus.COMPLETE,
            bundle_digest=DigestRecord(
                subject_id="bundle-001",
                subject_kind="evidence_bundle",
                algorithm=DigestAlgorithm.SHA256,
                digest_hex="c" * 64,
            ),
            item_digests=(),
            finding_digests=(),
            doctrine_rule_codes=("evidence_before_claim",),
            created_at=datetime(2026, 1, 1),
        )


def test_validate_replay_manifest_blocks_invalid_manifest() -> None:
    manifest = ReplayManifest(
        manifest_id="manifest-005",
        bundle_id="bundle-001",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        bundle_status=EvidenceStatus.COMPLETE,
        bundle_digest=DigestRecord(
            subject_id="wrong-bundle",
            subject_kind="evidence_bundle",
            algorithm=DigestAlgorithm.SHA256,
            digest_hex="d" * 64,
        ),
        item_digests=(),
        finding_digests=(),
        doctrine_rule_codes=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_replay_manifest(manifest)
    finding_codes = {finding.code for finding in findings}

    assert "manifest_missing_evidence_doctrine" in finding_codes
    assert "manifest_missing_completion_doctrine" in finding_codes
    assert "manifest_missing_no_agi_doctrine" in finding_codes
    assert "manifest_bundle_digest_subject_mismatch" in finding_codes
    assert "manifest_missing_item_digests" in finding_codes
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )


def test_validate_replay_manifest_warns_for_rejected_bundle() -> None:
    manifest = build_replay_manifest(
        manifest_id="manifest-006",
        bundle=_bundle(status=EvidenceStatus.REJECTED),
    )

    findings = validate_replay_manifest(manifest)
    finding_codes = {finding.code for finding in findings}

    assert "manifest_rejected_bundle" in finding_codes
    assert "manifest_not_review_ready" in finding_codes
