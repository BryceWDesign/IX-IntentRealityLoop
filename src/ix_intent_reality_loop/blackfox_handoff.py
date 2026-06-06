"""BlackFox governance handoff packet.

The BlackFox handoff packages IX-IntentRealityLoop evidence for a governed
review/control-plane consumer. It does not approve action, certify readiness,
or claim AGI. It states what evidence exists, what is degraded or rejected, what
policy gates remain, and whether human review is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
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


class GovernanceRisk(StrEnum):
    """Governance risk level for downstream review."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    BLOCKED = "blocked"


class GovernanceGate(StrEnum):
    """BlackFox-style governance gate labels."""

    POLICY_REVIEW = "policy_review"
    EVIDENCE_REVIEW = "evidence_review"
    HUMAN_REVIEW = "human_review"
    NEGATIVE_CONTROL_REVIEW = "negative_control_review"
    NO_AGI_OVERCLAIM_REVIEW = "no_agi_overclaim_review"


@dataclass(frozen=True, slots=True)
class GovernanceReviewItem:
    """One item that a governance reviewer must inspect."""

    item_id: str
    gate: GovernanceGate
    subject_id: str
    summary: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "item_id",
            require_non_empty_text(self.item_id, "item_id"),
        )
        object.__setattr__(
            self,
            "subject_id",
            require_non_empty_text(self.subject_id, "subject_id"),
        )
        object.__setattr__(
            self,
            "summary",
            require_non_empty_text(self.summary, "summary"),
        )


@dataclass(frozen=True, slots=True)
class BlackFoxGovernanceHandoff:
    """Governance handoff for digest-bound agency-loop evidence."""

    handoff_id: str
    intent_id: str
    bundle_id: str
    manifest_id: str
    disposition: DecisionDisposition
    risk: GovernanceRisk
    authority_state: AuthorityState
    trust_score: BoundedScore
    summary: str
    doctrine_rule_codes: tuple[str, ...]
    review_items: tuple[GovernanceReviewItem, ...]
    blocker_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    required_next_steps: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "handoff_id",
            require_non_empty_text(self.handoff_id, "handoff_id"),
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
            "summary",
            require_non_empty_text(self.summary, "summary"),
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

        review_item_ids = [item.item_id for item in self.review_items]
        if len(review_item_ids) != len(set(review_item_ids)):
            raise ValueError("review items must use unique item_id values")

    @property
    def requires_human_review(self) -> bool:
        """Return whether downstream human review is required."""

        return self.authority_state is AuthorityState.HUMAN_REVIEW_REQUIRED

    @property
    def is_blocked(self) -> bool:
        """Return whether handoff blocks downstream use."""

        return self.disposition in {
            DecisionDisposition.REFUSE,
            DecisionDisposition.SAFE_HOLD,
            DecisionDisposition.ESCALATE,
        }


def _risk_from_bundle_and_manifest(
    *,
    bundle: EvidenceBundle,
    manifest: ReplayManifest,
) -> GovernanceRisk:
    """Return governance risk from evidence status and finding counts."""

    if bundle.blocker_count or bundle.status is EvidenceStatus.REJECTED:
        return GovernanceRisk.BLOCKED
    if manifest.bundle_status is EvidenceStatus.REJECTED:
        return GovernanceRisk.BLOCKED
    if bundle.status is EvidenceStatus.DEGRADED or bundle.warning_count >= 3:
        return GovernanceRisk.HIGH
    if bundle.warning_count or manifest.bundle_status is EvidenceStatus.DEGRADED:
        return GovernanceRisk.MODERATE
    return GovernanceRisk.LOW


def _trust_score_from_bundle_and_manifest(
    *,
    bundle: EvidenceBundle,
    manifest: ReplayManifest,
) -> BoundedScore:
    """Return conservative trust score for governance handoff."""

    if bundle.blocker_count or bundle.status is EvidenceStatus.REJECTED:
        return BoundedScore(0.0)

    base_score = 1.0
    base_score -= min(bundle.warning_count * 0.15, 0.6)
    if not manifest.is_review_ready:
        base_score -= 0.2

    return BoundedScore(max(0.0, base_score))


def _review_items(
    *,
    bundle: EvidenceBundle,
    manifest: ReplayManifest,
    risk: GovernanceRisk,
) -> tuple[GovernanceReviewItem, ...]:
    """Build required governance review items."""

    items = [
        GovernanceReviewItem(
            item_id="review-evidence-bundle",
            gate=GovernanceGate.EVIDENCE_REVIEW,
            subject_id=bundle.bundle_id,
            summary="Review evidence bundle status, blockers, warnings, and items.",
        ),
        GovernanceReviewItem(
            item_id="review-digest-manifest",
            gate=GovernanceGate.EVIDENCE_REVIEW,
            subject_id=manifest.manifest_id,
            summary="Review digest-bound manifest and item digests.",
        ),
        GovernanceReviewItem(
            item_id="review-human-authority",
            gate=GovernanceGate.HUMAN_REVIEW,
            subject_id=bundle.intent_id,
            summary="Confirm system recommendation does not replace human authority.",
        ),
        GovernanceReviewItem(
            item_id="review-no-agi-overclaim",
            gate=GovernanceGate.NO_AGI_OVERCLAIM_REVIEW,
            subject_id=bundle.bundle_id,
            summary="Confirm handoff does not claim AGI, certification, or deployment.",
        ),
    ]

    if risk in {GovernanceRisk.HIGH, GovernanceRisk.BLOCKED}:
        items.append(
            GovernanceReviewItem(
                item_id="review-negative-controls",
                gate=GovernanceGate.NEGATIVE_CONTROL_REVIEW,
                subject_id=bundle.bundle_id,
                summary="Review degraded, rejected, or blocked evidence paths.",
            )
        )

    return tuple(items)


def build_blackfox_governance_handoff(
    *,
    handoff_id: str,
    bundle: EvidenceBundle,
    manifest: ReplayManifest,
) -> BlackFoxGovernanceHandoff:
    """Build a BlackFox-style governance handoff from evidence artifacts."""

    if manifest.bundle_id != bundle.bundle_id:
        raise ValueError("manifest bundle_id must match evidence bundle bundle_id")
    if manifest.intent_id != bundle.intent_id:
        raise ValueError("manifest intent_id must match evidence bundle intent_id")

    risk = _risk_from_bundle_and_manifest(bundle=bundle, manifest=manifest)
    trust_score = _trust_score_from_bundle_and_manifest(
        bundle=bundle,
        manifest=manifest,
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

    if risk is GovernanceRisk.BLOCKED:
        disposition = DecisionDisposition.SAFE_HOLD
        authority_state = AuthorityState.HUMAN_REVIEW_REQUIRED
        required_next_steps = ("resolve blocker findings before downstream use",)
    elif risk is GovernanceRisk.HIGH:
        disposition = DecisionDisposition.DEFER
        authority_state = AuthorityState.HUMAN_REVIEW_REQUIRED
        required_next_steps = ("complete human review before downstream use",)
    elif risk is GovernanceRisk.MODERATE:
        disposition = DecisionDisposition.CLAMP
        authority_state = AuthorityState.HUMAN_REVIEW_REQUIRED
        required_next_steps = ("review warnings before accepting handoff",)
    else:
        disposition = DecisionDisposition.ALLOW
        authority_state = AuthorityState.SYSTEM_RECOMMENDATION_ONLY
        required_next_steps = ("human reviewer may accept or reject recommendation",)

    return BlackFoxGovernanceHandoff(
        handoff_id=handoff_id,
        intent_id=bundle.intent_id,
        bundle_id=bundle.bundle_id,
        manifest_id=manifest.manifest_id,
        disposition=disposition,
        risk=risk,
        authority_state=authority_state,
        trust_score=trust_score,
        summary=(
            "BlackFox governance handoff for IX-IntentRealityLoop evidence. "
            "This is a review packet, not approval, certification, or AGI proof."
        ),
        doctrine_rule_codes=(
            "evidence_before_claim",
            "human_authority_persists",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        review_items=_review_items(bundle=bundle, manifest=manifest, risk=risk),
        blocker_codes=blocker_codes,
        warning_codes=warning_codes,
        required_next_steps=required_next_steps,
    )


def validate_blackfox_governance_handoff(
    handoff: BlackFoxGovernanceHandoff,
) -> tuple[ValidationFinding, ...]:
    """Validate BlackFox governance handoff before external review."""

    findings: list[ValidationFinding] = []

    if "human_authority_persists" not in handoff.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "blackfox_handoff_missing_authority_doctrine",
                "Governance handoff must preserve human authority.",
            )
        )

    if "evidence_before_claim" not in handoff.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "blackfox_handoff_missing_evidence_doctrine",
                "Governance handoff must cite evidence_before_claim doctrine.",
            )
        )

    if "no_agi_overclaim" not in handoff.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "blackfox_handoff_missing_no_agi_doctrine",
                "Governance handoff must cite no_agi_overclaim doctrine.",
            )
        )

    if handoff.disposition is DecisionDisposition.ALLOW and (
        handoff.risk is not GovernanceRisk.LOW
    ):
        findings.append(
            blocker_finding(
                "blackfox_handoff_allows_non_low_risk",
                "Governance handoff cannot allow non-low risk evidence.",
            )
        )

    if handoff.disposition is DecisionDisposition.ALLOW and handoff.blocker_codes:
        findings.append(
            blocker_finding(
                "blackfox_handoff_allows_blockers",
                "Governance handoff cannot allow evidence with blockers.",
            )
        )

    if not handoff.review_items:
        findings.append(
            blocker_finding(
                "blackfox_handoff_missing_review_items",
                "Governance handoff must include review items.",
            )
        )

    if handoff.is_blocked:
        findings.append(
            warning_finding(
                "blackfox_handoff_blocked",
                "Governance handoff is blocked and cannot be used downstream.",
            )
        )

    if handoff.requires_human_review:
        findings.append(
            warning_finding(
                "blackfox_handoff_requires_human_review",
                "Governance handoff requires human review.",
            )
        )

    if handoff.trust_score.is_below(0.5):
        findings.append(
            warning_finding(
                "blackfox_handoff_trust_below_target",
                "Governance handoff trust score is below target threshold.",
            )
        )

    return tuple(findings)
