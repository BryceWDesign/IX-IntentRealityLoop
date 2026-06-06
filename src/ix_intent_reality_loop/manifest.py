"""Digest-bound replay manifest.

The manifest gives evidence bundles tamper-evident structure. It does not claim
truth by itself. It records canonical hashes for the evidence bundle, bundle
items, validation findings, replay log reference, and memory ledger reference so
downstream Kernel and BlackFox handoffs can bind to stable review artifacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.core import (
    EvidenceStatus,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.evidence import EvidenceBundle, EvidenceItem


class DigestAlgorithm(StrEnum):
    """Supported digest algorithms."""

    SHA256 = "sha256"


@dataclass(frozen=True, slots=True)
class DigestRecord:
    """Digest record for one manifest subject."""

    subject_id: str
    subject_kind: str
    algorithm: DigestAlgorithm
    digest_hex: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject_id",
            require_non_empty_text(self.subject_id, "subject_id"),
        )
        object.__setattr__(
            self,
            "subject_kind",
            require_non_empty_text(self.subject_kind, "subject_kind"),
        )
        object.__setattr__(
            self,
            "digest_hex",
            require_non_empty_text(self.digest_hex, "digest_hex"),
        )
        if len(self.digest_hex) != 64:
            raise ValueError("sha256 digest_hex must be 64 hexadecimal characters")
        try:
            int(self.digest_hex, 16)
        except ValueError as exc:
            raise ValueError("digest_hex must be hexadecimal") from exc


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    """Digest-bound manifest for one evidence bundle."""

    manifest_id: str
    bundle_id: str
    intent_id: str
    replay_log_id: str
    memory_ledger_id: str
    bundle_status: EvidenceStatus
    bundle_digest: DigestRecord
    item_digests: tuple[DigestRecord, ...]
    finding_digests: tuple[DigestRecord, ...]
    doctrine_rule_codes: tuple[str, ...]
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "manifest_id",
            require_non_empty_text(self.manifest_id, "manifest_id"),
        )
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
            "doctrine_rule_codes",
            tuple(
                require_non_empty_text(code, "doctrine_rule_code")
                for code in self.doctrine_rule_codes
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

        item_subject_ids = [digest.subject_id for digest in self.item_digests]
        if len(item_subject_ids) != len(set(item_subject_ids)):
            raise ValueError("item digests must use unique subject_id values")

        finding_subject_ids = [digest.subject_id for digest in self.finding_digests]
        if len(finding_subject_ids) != len(set(finding_subject_ids)):
            raise ValueError("finding digests must use unique subject_id values")

    @property
    def is_review_ready(self) -> bool:
        """Return whether manifest represents complete bundle evidence."""

        return self.bundle_status is EvidenceStatus.COMPLETE

    @property
    def digest_count(self) -> int:
        """Return total number of digest records in this manifest."""

        return 1 + len(self.item_digests) + len(self.finding_digests)


def _canonical_json(data: dict[str, object]) -> str:
    """Return stable canonical JSON for digesting."""

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha256_hex(data: dict[str, object]) -> str:
    """Return SHA-256 digest for canonical JSON data."""

    canonical = _canonical_json(data)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _finding_payload(finding: ValidationFinding) -> dict[str, object]:
    """Return canonical payload for a validation finding."""

    return {
        "code": finding.code,
        "message": finding.message,
        "severity": finding.severity.value,
    }


def _item_payload(item: EvidenceItem) -> dict[str, object]:
    """Return canonical payload for an evidence item."""

    return {
        "item_id": item.item_id,
        "kind": item.kind.value,
        "subject_id": item.subject_id,
        "summary": item.summary,
        "status": item.status.value,
        "finding_codes": list(item.finding_codes),
        "created_at": item.created_at.isoformat(),
    }


def _bundle_payload(bundle: EvidenceBundle) -> dict[str, object]:
    """Return canonical payload for bundle-level digesting."""

    return {
        "bundle_id": bundle.bundle_id,
        "intent_id": bundle.intent_id,
        "replay_log_id": bundle.replay_log_id,
        "memory_ledger_id": bundle.memory_ledger_id,
        "narrative_summary": bundle.narrative_summary,
        "status": bundle.status.value,
        "item_ids": [item.item_id for item in bundle.items],
        "finding_codes": [finding.code for finding in bundle.findings],
        "doctrine_rule_codes": list(bundle.doctrine_rule_codes),
        "required_next_steps": list(bundle.required_next_steps),
        "created_at": bundle.created_at.isoformat(),
    }


def build_digest_record(
    *,
    subject_id: str,
    subject_kind: str,
    payload: dict[str, object],
) -> DigestRecord:
    """Build a SHA-256 digest record from canonical payload data."""

    return DigestRecord(
        subject_id=subject_id,
        subject_kind=subject_kind,
        algorithm=DigestAlgorithm.SHA256,
        digest_hex=_sha256_hex(payload),
    )


def build_replay_manifest(
    *,
    manifest_id: str,
    bundle: EvidenceBundle,
) -> ReplayManifest:
    """Build a digest-bound manifest from an evidence bundle."""

    bundle_digest = build_digest_record(
        subject_id=bundle.bundle_id,
        subject_kind="evidence_bundle",
        payload=_bundle_payload(bundle),
    )
    item_digests = tuple(
        build_digest_record(
            subject_id=item.item_id,
            subject_kind=f"evidence_item:{item.kind.value}",
            payload=_item_payload(item),
        )
        for item in bundle.items
    )
    finding_digests = tuple(
        build_digest_record(
            subject_id=f"finding:{index:03d}:{finding.code}",
            subject_kind="validation_finding",
            payload=_finding_payload(finding),
        )
        for index, finding in enumerate(bundle.findings, start=1)
    )

    return ReplayManifest(
        manifest_id=manifest_id,
        bundle_id=bundle.bundle_id,
        intent_id=bundle.intent_id,
        replay_log_id=bundle.replay_log_id,
        memory_ledger_id=bundle.memory_ledger_id,
        bundle_status=bundle.status,
        bundle_digest=bundle_digest,
        item_digests=item_digests,
        finding_digests=finding_digests,
        doctrine_rule_codes=(
            "evidence_before_claim",
            "completion_not_output",
            "no_agi_overclaim",
        ),
    )


def validate_replay_manifest(
    manifest: ReplayManifest,
) -> tuple[ValidationFinding, ...]:
    """Validate replay manifest before downstream handoff."""

    findings: list[ValidationFinding] = []

    if "evidence_before_claim" not in manifest.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "manifest_missing_evidence_doctrine",
                "Replay manifest must cite evidence_before_claim doctrine.",
            )
        )

    if "completion_not_output" not in manifest.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "manifest_missing_completion_doctrine",
                "Replay manifest must not treat digest binding as completion.",
            )
        )

    if "no_agi_overclaim" not in manifest.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "manifest_missing_no_agi_doctrine",
                "Replay manifest must cite no_agi_overclaim doctrine.",
            )
        )

    if manifest.bundle_digest.subject_id != manifest.bundle_id:
        findings.append(
            blocker_finding(
                "manifest_bundle_digest_subject_mismatch",
                "Bundle digest subject_id must match manifest bundle_id.",
            )
        )

    if not manifest.item_digests:
        findings.append(
            blocker_finding(
                "manifest_missing_item_digests",
                "Replay manifest must contain evidence item digests.",
            )
        )

    if manifest.bundle_status is EvidenceStatus.REJECTED:
        findings.append(
            warning_finding(
                "manifest_rejected_bundle",
                "Replay manifest references rejected evidence.",
            )
        )

    if manifest.bundle_status is EvidenceStatus.DEGRADED:
        findings.append(
            warning_finding(
                "manifest_degraded_bundle",
                "Replay manifest references degraded evidence requiring review.",
            )
        )

    if not manifest.is_review_ready:
        findings.append(
            warning_finding(
                "manifest_not_review_ready",
                "Replay manifest is not review-ready until bundle status is complete.",
            )
        )

    return tuple(findings)
