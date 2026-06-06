from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.blackfox_handoff import (
    BlackFoxGovernanceHandoff,
    GovernanceRisk,
)
from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
)
from ix_intent_reality_loop.evidence import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceItemKind,
)
from ix_intent_reality_loop.kernel_handoff import (
    KernelDonorStatus,
    KernelWave6DonorPacket,
    build_kernel_wave6_donor_packet,
    validate_kernel_wave6_donor_packet,
)
from ix_intent_reality_loop.manifest import (
    DigestAlgorithm,
    DigestRecord,
    ReplayManifest,
)


def _bundle(
    *,
    status: EvidenceStatus = EvidenceStatus.COMPLETE,
    findings: tuple[ValidationFinding, ...] = (),
) -> EvidenceBundle:
    return EvidenceBundle(
        bundle_id="bundle-001",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        narrative_summary="Bounded evidence bundle.",
        status=status,
        items=(
            EvidenceItem(
                item_id="item-001",
                kind=EvidenceItemKind.REPLAY_LOG,
                subject_id="replay-001",
                summary="Replay log included.",
                status=EvidenceStatus.COMPLETE,
            ),
        ),
        findings=findings,
        doctrine_rule_codes=(
            "evidence_before_claim",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _manifest(
    *,
    bundle_status: EvidenceStatus = EvidenceStatus.COMPLETE,
) -> ReplayManifest:
    return ReplayManifest(
        manifest_id="manifest-001",
        bundle_id="bundle-001",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        bundle_status=bundle_status,
        bundle_digest=DigestRecord(
            subject_id="bundle-001",
            subject_kind="evidence_bundle",
            algorithm=DigestAlgorithm.SHA256,
            digest_hex="a" * 64,
        ),
        item_digests=(
            DigestRecord(
                subject_id="item-001",
                subject_kind="evidence_item",
                algorithm=DigestAlgorithm.SHA256,
                digest_hex="b" * 64,
            ),
        ),
        finding_digests=(),
        doctrine_rule_codes=(
            "evidence_before_claim",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _handoff(
    *,
    risk: GovernanceRisk = GovernanceRisk.LOW,
    disposition: DecisionDisposition = DecisionDisposition.ALLOW,
    authority_state: AuthorityState = AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
    trust_score: float = 1.0,
    blocker_codes: tuple[str, ...] = (),
    warning_codes: tuple[str, ...] = (),
) -> BlackFoxGovernanceHandoff:
    return BlackFoxGovernanceHandoff(
        handoff_id="blackfox-001",
        intent_id="intent-001",
        bundle_id="bundle-001",
        manifest_id="manifest-001",
        disposition=disposition,
        risk=risk,
        authority_state=authority_state,
        trust_score=BoundedScore(trust_score),
        summary="Governance handoff.",
        doctrine_rule_codes=(
            "evidence_before_claim",
            "human_authority_persists",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        review_items=(),
        blocker_codes=blocker_codes,
        warning_codes=warning_codes,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_build_kernel_wave6_donor_packet_ready_for_low_risk_evidence() -> None:
    packet = build_kernel_wave6_donor_packet(
        packet_id="kernel-donor-001",
        bundle=_bundle(),
        manifest=_manifest(),
        handoff=_handoff(),
    )

    assert packet.donor_status is KernelDonorStatus.READY_FOR_REVIEW
    assert packet.is_review_ready
    assert not packet.is_blocked
    assert packet.review_confidence.value == 1.0
    assert "does not claim AGI" in packet.rejected_claims


def test_build_kernel_wave6_donor_packet_degrades_warning_evidence() -> None:
    warning = ValidationFinding(
        code="warning",
        message="Warning requires review.",
        severity=ValidationSeverity.WARNING,
    )

    packet = build_kernel_wave6_donor_packet(
        packet_id="kernel-donor-002",
        bundle=_bundle(status=EvidenceStatus.DEGRADED, findings=(warning,)),
        manifest=_manifest(bundle_status=EvidenceStatus.DEGRADED),
        handoff=_handoff(
            risk=GovernanceRisk.MODERATE,
            disposition=DecisionDisposition.CLAMP,
            authority_state=AuthorityState.HUMAN_REVIEW_REQUIRED,
            trust_score=0.65,
            warning_codes=("warning",),
        ),
    )
    findings = validate_kernel_wave6_donor_packet(packet)
    finding_codes = {finding.code for finding in findings}

    assert packet.donor_status is KernelDonorStatus.DEGRADED_REVIEW_REQUIRED
    assert not packet.is_review_ready
    assert "kernel_donor_degraded_review_required" in finding_codes


def test_build_kernel_wave6_donor_packet_blocks_rejected_evidence() -> None:
    blocker = ValidationFinding(
        code="blocker",
        message="Blocker prevents donor use.",
        severity=ValidationSeverity.BLOCKER,
    )

    packet = build_kernel_wave6_donor_packet(
        packet_id="kernel-donor-003",
        bundle=_bundle(status=EvidenceStatus.REJECTED, findings=(blocker,)),
        manifest=_manifest(bundle_status=EvidenceStatus.REJECTED),
        handoff=_handoff(
            risk=GovernanceRisk.BLOCKED,
            disposition=DecisionDisposition.SAFE_HOLD,
            authority_state=AuthorityState.HUMAN_REVIEW_REQUIRED,
            trust_score=0.0,
            blocker_codes=("blocker",),
        ),
    )
    findings = validate_kernel_wave6_donor_packet(packet)
    finding_codes = {finding.code for finding in findings}

    assert packet.donor_status is KernelDonorStatus.BLOCKED
    assert packet.is_blocked
    assert "kernel_donor_blocked" in finding_codes
    assert "kernel_donor_confidence_below_target" in finding_codes


def test_build_kernel_wave6_donor_packet_rejects_mismatched_handoff() -> None:
    handoff = BlackFoxGovernanceHandoff(
        handoff_id="blackfox-002",
        intent_id="intent-001",
        bundle_id="wrong-bundle",
        manifest_id="manifest-001",
        disposition=DecisionDisposition.ALLOW,
        risk=GovernanceRisk.LOW,
        authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
        trust_score=BoundedScore(1.0),
        summary="Mismatched governance handoff.",
        doctrine_rule_codes=("evidence_before_claim",),
        review_items=(),
    )

    with pytest.raises(ValueError, match="handoff bundle_id must match"):
        build_kernel_wave6_donor_packet(
            packet_id="kernel-donor-004",
            bundle=_bundle(),
            manifest=_manifest(),
            handoff=handoff,
        )


def test_kernel_wave6_donor_packet_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        KernelWave6DonorPacket(
            packet_id="kernel-donor-005",
            intent_id="intent-001",
            bundle_id="bundle-001",
            manifest_id="manifest-001",
            blackfox_handoff_id="blackfox-001",
            donor_status=KernelDonorStatus.READY_FOR_REVIEW,
            evidence_status=EvidenceStatus.COMPLETE,
            governance_risk=GovernanceRisk.LOW,
            review_confidence=BoundedScore(1.0),
            summary="Donor packet.",
            supported_capabilities=(),
            rejected_claims=("does not claim AGI",),
            blocker_codes=(),
            warning_codes=(),
            doctrine_rule_codes=("no_agi_overclaim",),
            created_at=datetime(2026, 1, 1),
        )


def test_validate_kernel_wave6_donor_packet_blocks_invalid_ready_packet() -> None:
    packet = KernelWave6DonorPacket(
        packet_id="kernel-donor-006",
        intent_id="intent-001",
        bundle_id="bundle-001",
        manifest_id="manifest-001",
        blackfox_handoff_id="blackfox-001",
        donor_status=KernelDonorStatus.READY_FOR_REVIEW,
        evidence_status=EvidenceStatus.COMPLETE,
        governance_risk=GovernanceRisk.HIGH,
        review_confidence=BoundedScore(0.9),
        summary="Invalid ready packet.",
        supported_capabilities=(),
        rejected_claims=(),
        blocker_codes=("blocker",),
        warning_codes=(),
        doctrine_rule_codes=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_kernel_wave6_donor_packet(packet)
    finding_codes = {finding.code for finding in findings}

    assert "kernel_donor_missing_evidence_doctrine" in finding_codes
    assert "kernel_donor_missing_authority_doctrine" in finding_codes
    assert "kernel_donor_missing_no_agi_doctrine" in finding_codes
    assert "kernel_donor_missing_supported_capabilities" in finding_codes
    assert "kernel_donor_missing_agi_rejection" in finding_codes
    assert "kernel_donor_ready_with_blockers" in finding_codes
    assert "kernel_donor_ready_with_non_low_risk" in finding_codes
