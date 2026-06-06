from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.blackfox_handoff import (
    BlackFoxGovernanceHandoff,
    GovernanceRisk,
    build_blackfox_governance_handoff,
    validate_blackfox_governance_handoff,
)
from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
)
from ix_intent_reality_loop.evidence import EvidenceBundle, EvidenceItem, EvidenceItemKind
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


def test_build_blackfox_handoff_allows_low_risk_complete_evidence() -> None:
    handoff = build_blackfox_governance_handoff(
        handoff_id="blackfox-001",
        bundle=_bundle(),
        manifest=_manifest(),
    )

    assert handoff.risk is GovernanceRisk.LOW
    assert handoff.disposition is DecisionDisposition.ALLOW
    assert handoff.authority_state is AuthorityState.SYSTEM_RECOMMENDATION_ONLY
    assert handoff.trust_score.value == 1.0
    assert not handoff.requires_human_review


def test_build_blackfox_handoff_clamps_moderate_warning_evidence() -> None:
    warning = ValidationFinding(
        code="warning",
        message="Warning requires review.",
        severity=ValidationSeverity.WARNING,
    )

    handoff = build_blackfox_governance_handoff(
        handoff_id="blackfox-002",
        bundle=_bundle(findings=(warning,)),
        manifest=_manifest(),
    )
    findings = validate_blackfox_governance_handoff(handoff)
    finding_codes = {finding.code for finding in findings}

    assert handoff.risk is GovernanceRisk.MODERATE
    assert handoff.disposition is DecisionDisposition.CLAMP
    assert handoff.requires_human_review
    assert "blackfox_handoff_requires_human_review" in finding_codes


def test_build_blackfox_handoff_defers_high_degraded_evidence() -> None:
    handoff = build_blackfox_governance_handoff(
        handoff_id="blackfox-003",
        bundle=_bundle(status=EvidenceStatus.DEGRADED),
        manifest=_manifest(bundle_status=EvidenceStatus.DEGRADED),
    )

    assert handoff.risk is GovernanceRisk.HIGH
    assert handoff.disposition is DecisionDisposition.DEFER
    assert handoff.requires_human_review


def test_build_blackfox_handoff_safe_holds_blocked_evidence() -> None:
    blocker = ValidationFinding(
        code="blocker",
        message="Blocker prevents handoff.",
        severity=ValidationSeverity.BLOCKER,
    )

    handoff = build_blackfox_governance_handoff(
        handoff_id="blackfox-004",
        bundle=_bundle(status=EvidenceStatus.REJECTED, findings=(blocker,)),
        manifest=_manifest(bundle_status=EvidenceStatus.REJECTED),
    )
    findings = validate_blackfox_governance_handoff(handoff)
    finding_codes = {finding.code for finding in findings}

    assert handoff.risk is GovernanceRisk.BLOCKED
    assert handoff.disposition is DecisionDisposition.SAFE_HOLD
    assert handoff.is_blocked
    assert handoff.trust_score.value == 0.0
    assert "blackfox_handoff_blocked" in finding_codes
    assert "blackfox_handoff_trust_below_target" in finding_codes


def test_build_blackfox_handoff_rejects_mismatched_manifest_bundle() -> None:
    manifest = ReplayManifest(
        manifest_id="manifest-002",
        bundle_id="wrong-bundle",
        intent_id="intent-001",
        replay_log_id="replay-001",
        memory_ledger_id="ledger-001",
        bundle_status=EvidenceStatus.COMPLETE,
        bundle_digest=DigestRecord(
            subject_id="wrong-bundle",
            subject_kind="evidence_bundle",
            algorithm=DigestAlgorithm.SHA256,
            digest_hex="c" * 64,
        ),
        item_digests=(
            DigestRecord(
                subject_id="item-001",
                subject_kind="evidence_item",
                algorithm=DigestAlgorithm.SHA256,
                digest_hex="d" * 64,
            ),
        ),
        finding_digests=(),
        doctrine_rule_codes=("evidence_before_claim",),
    )

    with pytest.raises(ValueError, match="manifest bundle_id must match"):
        build_blackfox_governance_handoff(
            handoff_id="blackfox-005",
            bundle=_bundle(),
            manifest=manifest,
        )


def test_blackfox_handoff_rejects_duplicate_review_items() -> None:
    handoff = build_blackfox_governance_handoff(
        handoff_id="blackfox-006",
        bundle=_bundle(),
        manifest=_manifest(),
    )
    duplicate_item = handoff.review_items[0]

    with pytest.raises(ValueError, match="unique item_id"):
        BlackFoxGovernanceHandoff(
            handoff_id="blackfox-007",
            intent_id="intent-001",
            bundle_id="bundle-001",
            manifest_id="manifest-001",
            disposition=DecisionDisposition.ALLOW,
            risk=GovernanceRisk.LOW,
            authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
            trust_score=BoundedScore(1.0),
            summary="Invalid duplicate review item handoff.",
            doctrine_rule_codes=(
                "evidence_before_claim",
                "human_authority_persists",
                "completion_not_output",
                "no_agi_overclaim",
            ),
            review_items=(duplicate_item, duplicate_item),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_blackfox_handoff_rejects_naive_timestamp() -> None:
    handoff = build_blackfox_governance_handoff(
        handoff_id="blackfox-008",
        bundle=_bundle(),
        manifest=_manifest(),
    )

    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        BlackFoxGovernanceHandoff(
            handoff_id="blackfox-009",
            intent_id=handoff.intent_id,
            bundle_id=handoff.bundle_id,
            manifest_id=handoff.manifest_id,
            disposition=handoff.disposition,
            risk=handoff.risk,
            authority_state=handoff.authority_state,
            trust_score=handoff.trust_score,
            summary=handoff.summary,
            doctrine_rule_codes=handoff.doctrine_rule_codes,
            review_items=handoff.review_items,
            created_at=datetime(2026, 1, 1),
        )


def test_validate_blackfox_handoff_blocks_invalid_allow() -> None:
    handoff = BlackFoxGovernanceHandoff(
        handoff_id="blackfox-010",
        intent_id="intent-001",
        bundle_id="bundle-001",
        manifest_id="manifest-001",
        disposition=DecisionDisposition.ALLOW,
        risk=GovernanceRisk.HIGH,
        authority_state=AuthorityState.HUMAN_REVIEW_REQUIRED,
        trust_score=BoundedScore(0.4),
        summary="Invalid allow.",
        doctrine_rule_codes=(),
        review_items=(),
        blocker_codes=("blocker",),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_blackfox_governance_handoff(handoff)
    finding_codes = {finding.code for finding in findings}

    assert "blackfox_handoff_missing_authority_doctrine" in finding_codes
    assert "blackfox_handoff_missing_evidence_doctrine" in finding_codes
    assert "blackfox_handoff_missing_no_agi_doctrine" in finding_codes
    assert "blackfox_handoff_allows_non_low_risk" in finding_codes
    assert "blackfox_handoff_allows_blockers" in finding_codes
    assert "blackfox_handoff_missing_review_items" in finding_codes
