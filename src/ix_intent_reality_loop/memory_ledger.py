"""Memory quarantine and update ledger.

The ledger is an in-memory evaluation artifact used to prove that matched
outcomes, degraded outcomes, contradictions, and blocked no-action states are
handled differently. It is intentionally deterministic and side-effect free so
later replay and evidence layers can hash its records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.memory import (
    MemoryBindingAction,
    MemoryBindingDecision,
)


@dataclass(frozen=True, slots=True)
class MemoryLedgerEntry:
    """One memory update, downgrade, quarantine, or rejection record."""

    entry_id: str
    memory_decision_id: str
    intent_id: str
    action: MemoryBindingAction
    memory_keys: tuple[str, ...]
    confidence_after_binding: BoundedScore
    summary: str
    quarantine_tags: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entry_id",
            require_non_empty_text(self.entry_id, "entry_id"),
        )
        object.__setattr__(
            self,
            "memory_decision_id",
            require_non_empty_text(
                self.memory_decision_id,
                "memory_decision_id",
            ),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "memory_keys",
            tuple(
                require_non_empty_text(key, "memory_key")
                for key in self.memory_keys
            ),
        )
        object.__setattr__(
            self,
            "summary",
            require_non_empty_text(self.summary, "summary"),
        )
        object.__setattr__(
            self,
            "quarantine_tags",
            tuple(
                require_non_empty_text(tag, "quarantine_tag")
                for tag in self.quarantine_tags
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def is_quarantined(self) -> bool:
        """Return whether this ledger entry represents quarantined memory."""

        return self.action is MemoryBindingAction.QUARANTINE

    @property
    def is_positive_update(self) -> bool:
        """Return whether this ledger entry represents positive memory promotion."""

        return self.action is MemoryBindingAction.UPDATE


@dataclass(frozen=True, slots=True)
class MemoryLedger:
    """Deterministic immutable memory ledger snapshot."""

    ledger_id: str
    entries: tuple[MemoryLedgerEntry, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ledger_id",
            require_non_empty_text(self.ledger_id, "ledger_id"),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )
        entry_ids = [entry.entry_id for entry in self.entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("ledger entries must use unique entry_id values")

    @property
    def positive_update_count(self) -> int:
        """Return count of positive update entries."""

        return sum(1 for entry in self.entries if entry.is_positive_update)

    @property
    def quarantine_count(self) -> int:
        """Return count of quarantine entries."""

        return sum(1 for entry in self.entries if entry.is_quarantined)

    @property
    def downgraded_count(self) -> int:
        """Return count of downgraded entries."""

        return sum(
            1
            for entry in self.entries
            if entry.action is MemoryBindingAction.DOWNGRADE
        )

    def by_memory_key(self) -> Mapping[str, tuple[MemoryLedgerEntry, ...]]:
        """Return ledger entries grouped by memory key."""

        grouped: dict[str, list[MemoryLedgerEntry]] = {}
        for entry in self.entries:
            for memory_key in entry.memory_keys:
                grouped.setdefault(memory_key, []).append(entry)

        return MappingProxyType(
            {
                memory_key: tuple(entries)
                for memory_key, entries in grouped.items()
            }
        )

    def quarantine_tags(self) -> frozenset[str]:
        """Return all quarantine tags present in the ledger."""

        return frozenset(
            tag
            for entry in self.entries
            for tag in entry.quarantine_tags
        )

    def append(self, entry: MemoryLedgerEntry) -> MemoryLedger:
        """Return a new ledger snapshot with one appended entry."""

        return MemoryLedger(
            ledger_id=self.ledger_id,
            entries=(*self.entries, entry),
            created_at=self.created_at,
        )


def build_memory_ledger_entry(
    *,
    entry_id: str,
    decision: MemoryBindingDecision,
) -> MemoryLedgerEntry:
    """Build a ledger entry from a memory binding decision."""

    return MemoryLedgerEntry(
        entry_id=entry_id,
        memory_decision_id=decision.memory_decision_id,
        intent_id=decision.intent_id,
        action=decision.action,
        memory_keys=decision.memory_keys,
        confidence_after_binding=decision.confidence_after_binding,
        summary=decision.rationale,
        quarantine_tags=decision.quarantine_tags,
    )


def apply_memory_binding_decision(
    *,
    ledger: MemoryLedger,
    entry_id: str,
    decision: MemoryBindingDecision,
) -> MemoryLedger:
    """Return a new ledger with a memory binding decision applied."""

    entry = build_memory_ledger_entry(entry_id=entry_id, decision=decision)
    return ledger.append(entry)


def validate_memory_ledger(ledger: MemoryLedger) -> tuple[ValidationFinding, ...]:
    """Validate memory ledger state before replay evidence bundling."""

    findings: list[ValidationFinding] = []

    if not ledger.entries:
        findings.append(
            warning_finding(
                "memory_ledger_empty",
                "Memory ledger has no entries.",
            )
        )
        return tuple(findings)

    for entry in ledger.entries:
        if entry.action is MemoryBindingAction.UPDATE and not entry.memory_keys:
            findings.append(
                blocker_finding(
                    "memory_ledger_update_missing_keys",
                    "Positive memory ledger entry requires memory keys.",
                )
            )

        if entry.action is MemoryBindingAction.UPDATE and (
            entry.confidence_after_binding.is_below(0.75)
        ):
            findings.append(
                blocker_finding(
                    "memory_ledger_update_below_confidence_threshold",
                    "Positive memory ledger entry is below confidence threshold.",
                )
            )

        if entry.action is MemoryBindingAction.QUARANTINE and not (
            entry.quarantine_tags
        ):
            findings.append(
                blocker_finding(
                    "memory_ledger_quarantine_missing_tags",
                    "Quarantine ledger entry requires quarantine tags.",
                )
            )

        if entry.action is MemoryBindingAction.REJECT and (
            entry.confidence_after_binding.value != 0.0
        ):
            findings.append(
                blocker_finding(
                    "memory_ledger_reject_nonzero_confidence",
                    "Rejected memory ledger entry must preserve zero confidence.",
                )
            )

    if ledger.quarantine_count:
        findings.append(
            warning_finding(
                "memory_ledger_contains_quarantine",
                "Ledger contains quarantined memory that must not be reused as truth.",
            )
        )

    if ledger.downgraded_count:
        findings.append(
            warning_finding(
                "memory_ledger_contains_downgrade",
                "Ledger contains downgraded memory evidence.",
            )
        )

    return tuple(findings)
