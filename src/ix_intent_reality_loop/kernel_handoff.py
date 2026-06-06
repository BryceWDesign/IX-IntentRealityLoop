"""IX-CognitionKernel Wave 6 donor packet.

The Kernel donor packet translates IX-IntentRealityLoop evidence into a bounded
Wave 6 review artifact. It does not claim AGI. It describes whether the agency
loop produced review-ready, degraded, or blocked donor evidence for Kernel
validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.blackfox_handoff import (
    BlackFoxGovernanceHandoff,
    GovernanceRisk,
)
from ix_intent_reality_loop.core import (
    BoundedScore,
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.evidence import EvidenceBundle
from ix_intent_reality_loop.manifest import ReplayManifest


class KernelDonorStatus(StrEnum):
    """Status for IX-CognitionKernel Wave 6 donor evidence."""

    READY_FOR_REVIEW = "ready_for_review"
    DEGRADED_REVIEW_REQUIRED = "degraded_review_required"
    BLOCKED = "blocked"


class KernelDonorCapability(StrEnum):
    """Bounded capability area the donor packet may support."""

    INTENT_GROUNDING = "intent_grounding"
    TRIADIC_EXECUTION = "triadic_execution"
    FOURTH_EYE_ARBITRATION = "fourth_eye_arbitration"
    PERMISSION_GATING = "permission_gating"
    SENSORIMOTOR_FEEDBACK = "sensorimotor_feedback"
    OUTCOME_DELTA = "outcome_delta"
    MEMORY_BINDING = "memory_binding"
    REPLAY_EVIDENCE = "replay_evidence"


@dataclass(frozen=True, slots=True)
class KernelWave6DonorPacket:
    """Bounded donor packet for IX-CognitionKernel Wave 6 review."""

    packet_id: str
    intent_id: str
    bundle_id: str
    manifest_id: str
    blackfox_handoff_id: str
    donor_status: KernelDonorStatus
    evidence_status: EvidenceStatus
    governance_risk: GovernanceRisk
    review_confidence: BoundedScore
    summary: str
    supported_capabilities: tuple[KernelDonorCapability, ...]
    rejected_claims: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    doctrine_rule_codes: tuple[str, ...]
    required_next_steps: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "packet_id",
            require_non_empty_text(self.packet_id, "packet_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "bundle_id",
            require_non_empty_text(self.bundle_id, "bundle_id"),
        )
        object.__setattr__(
            self,
            "manifest_id",
            require_non_empty_text(self.manifest_id, "manifest_id"),
        )
        object.__setattr__(
            self,
            "blackfox_handoff_id",
            require_non_empty_text(
                self.blackfox_handoff_id,
                "blackfox_handoff_id",
            ),
        )
        object.__setattr__(
            self,
            "summary",
            require_non_empty_text(self.summary, "summary"),
        )
        object.__setattr__(
            self,
            "rejected_claims",
            tuple(
                require_non_empty_text(claim, "rejected_claim")
                for claim in self.rejected_claims
            ),
        )
        object.__setattr__(
            self,
            "blocker_codes",
            tuple(
                require_non_empty_text(code, "blocker_code")
                for code in self.blocker_codes
            ),
        )
        object.__setattr__(
            self,
            "warning_codes",
            tuple(
                require_non_empty_text(code, "warning_code")
                for code in self.warning_codes
            ),
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
    def is_review_ready(self) -> bool:
        """Return whether donor packet can be reviewed by Kernel."""

        return self.donor_status is KernelDonorStatus.READY_FOR_REVIEW

    @property
    def is_blocked(self) -> bool:
        """Return whether donor evidence is blocked."""

        return self.donor_status is KernelDonorStatus.BLOCKED


def _supported_capabilities() -> tuple[KernelDonorCapability, ...]:
    """Return bounded capabilities this donor repo is designed to support."""

    return (
        KernelDonorCapability.INTENT_GROUNDING,
        KernelDonorCapability.TRIADIC_EXECUTION,
        KernelDonorCapability.FOURTH_EYE_ARBITRATION,
        KernelDonorCapability.PERMISSION_GATING,
        KernelDonorCapability.SENSORIMOTOR_FEEDBACK,
        KernelDonorCapability.OUTCOME_DELTA,
        KernelDonorCapability.MEMORY_BINDING,
        KernelDonorCapability.REPLAY_EVIDENCE,
    )


def _required_rejected_claims() -> tuple[str, ...]:
    """Return claims this packet must explicitly reject."""

    return (
        "does not claim AGI",
        "does not certify AGI",
        "does not grant production autonomy",
        "does not authorize live physical actuation",
        "does not replace human authority",
    )


def _status_from_artifacts(
    *,
    bundle: EvidenceBundle,
    manifest: ReplayManifest,
    handoff: BlackFoxGovernanceHandoff,
) -> KernelDonorStatus:
    """Return Kernel donor status from evidence and governance artifacts."""

    if (
        bundle.status is EvidenceStatus.REJECTED
        or manifest.bundle_status is EvidenceStatus.REJECTED
        or handoff.is_blocked
        or handoff.risk is GovernanceRisk.BLOCKED
    ):
        return KernelDonorStatus.BLOCKED

    if (
        bundle.status is EvidenceStatus.DEGRADED
        or manifest.bundle_status is EvidenceStatus.DEGRADED
        or handoff.requires_human_review
        or handoff.risk in {GovernanceRisk.MODERATE, GovernanceRisk.HIGH}
    ):
        return KernelDonorStatus.DEGRADED_REVIEW_REQUIRED

    return KernelDonorStatus.READY_FOR_REVIEW


def build_kernel_wave6_donor_packet(
    *,
    packet_id: str,
    bundle: EvidenceBundle,
    manifest: ReplayManifest,
    handoff: BlackFoxGovernanceHandoff,
) -> KernelWave6DonorPacket:
    """Build a bounded Kernel Wave 6 donor packet."""

    if manifest.bundle_id != bundle.bundle_id:
        raise ValueError("manifest bundle_id must match evidence bundle bundle_id")
    if handoff.bundle_id != bundle.bundle_id:
        raise ValueError("handoff bundle_id must match evidence bundle bundle_id")
    if manifest.intent_id != bundle.intent_id:
        raise ValueError("manifest intent_id must match evidence bundle intent_id")
    if handoff.intent_id != bundle.intent_id:
        raise ValueError("handoff intent_id must match evidence bundle intent_id")

    donor_status = _status_from_artifacts(
        bundle=bundle,
        manifest=manifest,
        handoff=handoff,
    )
    blocker_codes = tuple(
        finding.code
        for finding in bundle.findings
        if finding.severity is ValidationSeverity.BLOCKER
    )
    warning_codes = tuple(
        finding.code
        for finding in bundle.findings
        if finding.severity is ValidationSeverity.WARNING
    )

    if donor_status is KernelDonorStatus.READY_FOR_REVIEW:
        next_steps = ("submit as bounded Wave 6 donor evidence for human review",)
    elif donor_status is KernelDonorStatus.DEGRADED_REVIEW_REQUIRED:
        next_steps = ("resolve or explicitly accept degraded evidence before use",)
    else:
        next_steps = ("do not use as Wave 6 donor evidence until blockers resolve",)

    return KernelWave6DonorPacket(
        packet_id=packet_id,
        intent_id=bundle.intent_id,
        bundle_id=bundle.bundle_id,
        manifest_id=manifest.manifest_id,
        blackfox_handoff_id=handoff.handoff_id,
        donor_status=donor_status,
        evidence_status=bundle.status,
        governance_risk=handoff.risk,
        review_confidence=BoundedScore(
            min(handoff.trust_score.value, 1.0 if manifest.is_review_ready else 0.75)
        ),
        summary=(
            "IX-IntentRealityLoop donor packet for IX-CognitionKernel Wave 6. "
            "It supports bounded agency-grounding review only and does not claim AGI."
        ),
        supported_capabilities=_supported_capabilities(),
        rejected_claims=_required_rejected_claims(),
        blocker_codes=(*blocker_codes, *handoff.blocker_codes),
        warning_codes=(*warning_codes, *handoff.warning_codes),
        doctrine_rule_codes=(
            "evidence_before_claim",
            "human_authority_persists",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        required_next_steps=next_steps,
    )


def validate_kernel_wave6_donor_packet(
    packet: KernelWave6DonorPacket,
) -> tuple[ValidationFinding, ...]:
    """Validate Kernel Wave 6 donor packet before Kernel import."""

    findings: list[ValidationFinding] = []

    if "evidence_before_claim" not in packet.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "kernel_donor_missing_evidence_doctrine",
                "Kernel donor packet must cite evidence_before_claim doctrine.",
            )
        )

    if "human_authority_persists" not in packet.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "kernel_donor_missing_authority_doctrine",
                "Kernel donor packet must preserve human authority.",
            )
        )

    if "no_agi_overclaim" not in packet.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "kernel_donor_missing_no_agi_doctrine",
                "Kernel donor packet must cite no_agi_overclaim doctrine.",
            )
        )

    if not packet.supported_capabilities:
        findings.append(
            blocker_finding(
                "kernel_donor_missing_supported_capabilities",
                "Kernel donor packet must list bounded supported capabilities.",
            )
        )

    if "does not claim AGI" not in packet.rejected_claims:
        findings.append(
            blocker_finding(
                "kernel_donor_missing_agi_rejection",
                "Kernel donor packet must explicitly reject AGI claim.",
            )
        )

    if packet.is_review_ready and packet.blocker_codes:
        findings.append(
            blocker_finding(
                "kernel_donor_ready_with_blockers",
                "Ready donor packet cannot preserve blocker codes.",
            )
        )

    if packet.is_review_ready and packet.governance_risk is not GovernanceRisk.LOW:
        findings.append(
            blocker_finding(
                "kernel_donor_ready_with_non_low_risk",
                "Ready donor packet must preserve low governance risk.",
            )
        )

    if packet.is_blocked:
        findings.append(
            warning_finding(
                "kernel_donor_blocked",
                "Kernel donor packet is blocked.",
            )
        )

    if packet.donor_status is KernelDonorStatus.DEGRADED_REVIEW_REQUIRED:
        findings.append(
            warning_finding(
                "kernel_donor_degraded_review_required",
                "Kernel donor packet requires degraded-evidence review.",
            )
        )

    if packet.review_confidence.is_below(0.5):
        findings.append(
            warning_finding(
                "kernel_donor_confidence_below_target",
                "Kernel donor packet review confidence is below target threshold.",
            )
        )

    return tuple(findings)
