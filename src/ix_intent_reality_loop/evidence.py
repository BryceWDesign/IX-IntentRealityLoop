"""Evidence bundle builder.

Evidence bundles collect replay, memory-ledger, validation, doctrine, and
anti-overclaim signals into one reviewable artifact. A bundle is not completion
and is not proof of AGI. It is a structured record that later digest manifests,
Kernel donor packets, and BlackFox handoffs can reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.core import (
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.doctrine import find_prohibited_claims
from ix_intent_reality_loop.memory_ledger import (
    MemoryLedger,
    validate_memory_ledger,
)
from ix_intent_reality_loop.replay import ReplayEventLog, validate_replay_event_log


class EvidenceItemKind(StrEnum):
    """Canonical evidence item kinds."""

    REPLAY_EVENT = "replay_event"
    REPLAY_LOG = "replay_log"
    MEMORY_LEDGER = "memory_ledger"
    DOCTRINE_CHECK = "doctrine_check"
    VALIDATION_FINDING = "validation_finding"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One evidence item included in a bundle."""

    item_id: str
    kind: EvidenceItemKind
    subject_id: str
    summary: str
    status: EvidenceStatus
    finding_codes: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

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
        object.__setattr__(
            self,
            "finding_codes",
            tuple(
                require_non_empty_text(code, "finding_code")
                for code in self.finding_codes
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """Reviewable evidence bundle for one intent loop."""

    bundle_id: str
    intent_id: str
    replay_log_id: str
    memory_ledger_id: str
    narrative_summary: str
    status: EvidenceStatus
    items: tuple[EvidenceItem, ...]
    findings: tuple[ValidationFinding, ...]
    doctrine_rule_codes: tuple[str, ...]
    required_next_steps: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "bundle_id",
            require_non_empty_text(self.bundle_id, "bundle_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "replay_log_id",
            require_non_empty_text(self.replay_log_id, "replay_log_id"),
        )
        object.__setattr__(
            self,
            "memory_ledger_id",
            require_non_empty_text(self.memory_ledger_id, "memory_ledger_id"),
        )
        object.__setattr__(
            self,
            "narrative_summary",
            require_non_empty_text(self.narrative_summary, "narrative_summary"),
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

        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("evidence items must use unique item_id values")

    @property
    def blocker_count(self) -> int:
        """Return count of blocker findings in the bundle."""

        return sum(
            1
            for finding in self.findings
            if finding.severity is ValidationSeverity.BLOCKER
        )

    @property
    def warning_count(self) -> int:
        """Return count of warning findings in the bundle."""

        return sum(
            1
            for finding in self.findings
            if finding.severity is ValidationSeverity.WARNING
        )

    @property
    def is_review_ready(self) -> bool:
        """Return whether the bundle has complete evidence without blockers."""

        return self.status is EvidenceStatus.COMPLETE and self.blocker_count == 0


def _status_from_findings(findings: tuple[ValidationFinding, ...]) -> EvidenceStatus:
    """Return evidence status from validation findings."""

    if any(finding.severity is ValidationSeverity.BLOCKER for finding in findings):
        return EvidenceStatus.REJECTED
    if any(finding.severity is ValidationSeverity.WARNING for finding in findings):
        return EvidenceStatus.DEGRADED
    return EvidenceStatus.COMPLETE


def _validation_items(
    findings: tuple[ValidationFinding, ...],
) -> tuple[EvidenceItem, ...]:
    """Build evidence items for validation findings."""

    return tuple(
        EvidenceItem(
            item_id=f"finding-{index:03d}-{finding.code}",
            kind=EvidenceItemKind.VALIDATION_FINDING,
            subject_id=finding.code,
            summary=finding.message,
            status=(
                EvidenceStatus.REJECTED
                if finding.severity is ValidationSeverity.BLOCKER
                else EvidenceStatus.DEGRADED
            ),
            finding_codes=(finding.code,),
        )
        for index, finding in enumerate(findings, start=1)
    )


def _replay_items(replay_log: ReplayEventLog) -> tuple[EvidenceItem, ...]:
    """Build evidence items from replay events."""

    return tuple(
        EvidenceItem(
            item_id=f"replay-event-{index:03d}-{event.event_id}",
            kind=EvidenceItemKind.REPLAY_EVENT,
            subject_id=event.subject_id,
            summary=event.summary,
            status=EvidenceStatus.COMPLETE,
            finding_codes=(),
            created_at=event.created_at,
        )
        for index, event in enumerate(replay_log.events, start=1)
    )


def build_evidence_bundle(
    *,
    bundle_id: str,
    replay_log: ReplayEventLog,
    memory_ledger: MemoryLedger,
    narrative_summary: str,
) -> EvidenceBundle:
    """Build an evidence bundle from replay and memory-ledger artifacts."""

    if replay_log.intent_id != memory_ledger.ledger_id and not memory_ledger.entries:
        raise ValueError(
            "empty memory ledger must use the replay intent_id as ledger_id"
        )

    replay_findings = validate_replay_event_log(replay_log)
    memory_findings = validate_memory_ledger(memory_ledger)
    prohibited_claims = find_prohibited_claims(narrative_summary)
    doctrine_findings = tuple(
        blocker_finding(
            "evidence_bundle_prohibited_claim",
            f"Evidence summary contains prohibited claim fragment: {claim}.",
        )
        for claim in prohibited_claims
    )

    findings = (*replay_findings, *memory_findings, *doctrine_findings)
    status = _status_from_findings(findings)
    replay_log_item = EvidenceItem(
        item_id=f"replay-log-{replay_log.log_id}",
        kind=EvidenceItemKind.REPLAY_LOG,
        subject_id=replay_log.log_id,
        summary="Replay log included for ordered agency-loop review.",
        status=_status_from_findings(replay_findings),
        finding_codes=tuple(finding.code for finding in replay_findings),
        created_at=replay_log.created_at,
    )
    memory_ledger_item = EvidenceItem(
        item_id=f"memory-ledger-{memory_ledger.ledger_id}",
        kind=EvidenceItemKind.MEMORY_LEDGER,
        subject_id=memory_ledger.ledger_id,
        summary="Memory ledger included for update, downgrade, and quarantine review.",
        status=_status_from_findings(memory_findings),
        finding_codes=tuple(finding.code for finding in memory_findings),
        created_at=memory_ledger.created_at,
    )
    doctrine_item = EvidenceItem(
        item_id=f"doctrine-check-{bundle_id}",
        kind=EvidenceItemKind.DOCTRINE_CHECK,
        subject_id=bundle_id,
        summary="Narrative summary checked for prohibited capability claims.",
        status=(
            EvidenceStatus.REJECTED if prohibited_claims else EvidenceStatus.COMPLETE
        ),
        finding_codes=tuple(finding.code for finding in doctrine_findings),
    )

    required_next_steps: tuple[str, ...]
    if status is EvidenceStatus.COMPLETE:
        required_next_steps = ("prepare digest-bound replay manifest",)
    elif status is EvidenceStatus.DEGRADED:
        required_next_steps = ("review warnings before digest manifest",)
    else:
        required_next_steps = ("resolve blocker findings before downstream handoff",)

    return EvidenceBundle(
        bundle_id=bundle_id,
        intent_id=replay_log.intent_id,
        replay_log_id=replay_log.log_id,
        memory_ledger_id=memory_ledger.ledger_id,
        narrative_summary=narrative_summary,
        status=status,
        items=(
            replay_log_item,
            memory_ledger_item,
            doctrine_item,
            *_replay_items(replay_log),
            *_validation_items(findings),
        ),
        findings=findings,
        doctrine_rule_codes=(
            "evidence_before_claim",
            "completion_not_output",
            "no_agi_overclaim",
        ),
        required_next_steps=required_next_steps,
    )


def validate_evidence_bundle(bundle: EvidenceBundle) -> tuple[ValidationFinding, ...]:
    """Validate an evidence bundle before digest manifest construction."""

    findings: list[ValidationFinding] = []

    if "evidence_before_claim" not in bundle.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "evidence_bundle_missing_evidence_doctrine",
                "Evidence bundle must cite evidence_before_claim doctrine.",
            )
        )

    if "completion_not_output" not in bundle.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "evidence_bundle_missing_completion_doctrine",
                "Evidence bundle must not treat bundled evidence as completion.",
            )
        )

    if "no_agi_overclaim" not in bundle.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "evidence_bundle_missing_no_agi_doctrine",
                "Evidence bundle must cite no_agi_overclaim doctrine.",
            )
        )

    if not bundle.items:
        findings.append(
            blocker_finding(
                "evidence_bundle_missing_items",
                "Evidence bundle must contain evidence items.",
            )
        )

    if bundle.status is EvidenceStatus.COMPLETE and bundle.blocker_count:
        findings.append(
            blocker_finding(
                "evidence_bundle_complete_with_blockers",
                "Complete evidence bundle cannot contain blocker findings.",
            )
        )

    if bundle.status is EvidenceStatus.REJECTED:
        findings.append(
            warning_finding(
                "evidence_bundle_rejected",
                "Evidence bundle is rejected and cannot be handed off downstream.",
            )
        )

    if bundle.status is EvidenceStatus.DEGRADED:
        findings.append(
            warning_finding(
                "evidence_bundle_degraded",
                "Evidence bundle is degraded and requires review before handoff.",
            )
        )

    return tuple(findings)
