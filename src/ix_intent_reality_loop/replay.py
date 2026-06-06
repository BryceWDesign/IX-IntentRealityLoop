"""Replay event log.

Replay is the audit spine for IX-IntentRealityLoop. It records the ordered
agency-loop events that later evidence bundles and digest manifests can verify.
The log is immutable, deterministic, and explicit about missing or invalid event
ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from ix_intent_reality_loop.core import (
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)


class ReplayEventType(StrEnum):
    """Canonical replay event types for the agency loop."""

    INTENT_PACKET = "intent_packet"
    FOCUS_SPLIT = "focus_split"
    LITERAL_LANE = "literal_lane"
    INTERPRETED_LANE = "interpreted_lane"
    SELF_SURPASS_LANE = "self_surpass_lane"
    LANE_COMPARISON = "lane_comparison"
    FOURTH_EYE_DECISION = "fourth_eye_decision"
    PERMISSION_GATE = "permission_gate"
    SAFETY_GATE = "safety_gate"
    BOUNDED_ACTION = "bounded_action"
    REALITY_FEEDBACK = "reality_feedback"
    OUTCOME_DELTA = "outcome_delta"
    MEMORY_BINDING = "memory_binding"
    MEMORY_LEDGER = "memory_ledger"


_REQUIRED_EVENT_SEQUENCE: tuple[ReplayEventType, ...] = (
    ReplayEventType.INTENT_PACKET,
    ReplayEventType.FOCUS_SPLIT,
    ReplayEventType.LITERAL_LANE,
    ReplayEventType.INTERPRETED_LANE,
    ReplayEventType.SELF_SURPASS_LANE,
    ReplayEventType.LANE_COMPARISON,
    ReplayEventType.FOURTH_EYE_DECISION,
    ReplayEventType.PERMISSION_GATE,
    ReplayEventType.SAFETY_GATE,
    ReplayEventType.BOUNDED_ACTION,
    ReplayEventType.REALITY_FEEDBACK,
    ReplayEventType.OUTCOME_DELTA,
    ReplayEventType.MEMORY_BINDING,
)


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    """One replayable agency-loop event."""

    event_id: str
    intent_id: str
    event_type: ReplayEventType
    subject_id: str
    summary: str
    payload: Mapping[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_id",
            require_non_empty_text(self.event_id, "event_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
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
            "payload",
            MappingProxyType(_validated_payload(self.payload)),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )


@dataclass(frozen=True, slots=True)
class ReplayEventLog:
    """Immutable ordered replay log for one intent loop."""

    log_id: str
    intent_id: str
    events: tuple[ReplayEvent, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "log_id",
            require_non_empty_text(self.log_id, "log_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("replay events must use unique event_id values")

        mismatched_intents = [
            event.intent_id
            for event in self.events
            if event.intent_id != self.intent_id
        ]
        if mismatched_intents:
            raise ValueError("all replay events must match log intent_id")

    @property
    def event_types(self) -> tuple[ReplayEventType, ...]:
        """Return event types in recorded order."""

        return tuple(event.event_type for event in self.events)

    @property
    def is_empty(self) -> bool:
        """Return whether the replay log has no events."""

        return not self.events

    def append(self, event: ReplayEvent) -> ReplayEventLog:
        """Return a new replay log with one appended event."""

        return ReplayEventLog(
            log_id=self.log_id,
            intent_id=self.intent_id,
            events=(*self.events, event),
            created_at=self.created_at,
        )


def _validated_payload(payload: Mapping[str, str]) -> dict[str, str]:
    """Return a validated string-keyed, string-valued payload dictionary."""

    if not isinstance(payload, dict | MappingProxyType):
        raise TypeError("payload must be a mapping")

    validated: dict[str, str] = {}
    for key, value in payload.items():
        validated_key = require_non_empty_text(key, "payload key")
        validated_value = require_non_empty_text(value, "payload value")
        validated[validated_key] = validated_value

    return validated


def required_replay_event_sequence() -> tuple[ReplayEventType, ...]:
    """Return the required core event sequence."""

    return _REQUIRED_EVENT_SEQUENCE


def build_replay_event(
    *,
    event_id: str,
    intent_id: str,
    event_type: ReplayEventType,
    subject_id: str,
    summary: str,
    payload: Mapping[str, str] | None = None,
) -> ReplayEvent:
    """Build one replay event with a validated payload."""

    return ReplayEvent(
        event_id=event_id,
        intent_id=intent_id,
        event_type=event_type,
        subject_id=subject_id,
        summary=summary,
        payload={} if payload is None else payload,
    )


def missing_required_event_types(
    event_types: tuple[ReplayEventType, ...],
) -> tuple[ReplayEventType, ...]:
    """Return required event types absent from a replay log."""

    present = set(event_types)
    return tuple(
        event_type
        for event_type in _REQUIRED_EVENT_SEQUENCE
        if event_type not in present
    )


def has_required_order(event_types: tuple[ReplayEventType, ...]) -> bool:
    """Return whether required event types appear in required relative order."""

    cursor = 0
    for event_type in event_types:
        if cursor >= len(_REQUIRED_EVENT_SEQUENCE):
            break
        if event_type is _REQUIRED_EVENT_SEQUENCE[cursor]:
            cursor += 1

    return cursor == len(_REQUIRED_EVENT_SEQUENCE)


def validate_replay_event_log(log: ReplayEventLog) -> tuple[ValidationFinding, ...]:
    """Validate replay log completeness and ordering before evidence bundling."""

    findings: list[ValidationFinding] = []

    if log.is_empty:
        findings.append(
            blocker_finding(
                "replay_log_empty",
                "Replay event log must contain agency-loop events.",
            )
        )
        return tuple(findings)

    missing_event_types = missing_required_event_types(log.event_types)
    if missing_event_types:
        missing = ", ".join(event_type.value for event_type in missing_event_types)
        findings.append(
            blocker_finding(
                "replay_log_missing_required_events",
                f"Replay log is missing required event type(s): {missing}.",
            )
        )

    if not has_required_order(log.event_types):
        findings.append(
            blocker_finding(
                "replay_log_required_order_broken",
                "Replay log does not preserve required agency-loop event order.",
            )
        )

    if log.event_types.count(ReplayEventType.MEMORY_BINDING) > 1:
        findings.append(
            warning_finding(
                "replay_log_multiple_memory_bindings",
                "Replay log contains multiple memory binding events.",
            )
        )

    if ReplayEventType.MEMORY_LEDGER not in log.event_types:
        findings.append(
            warning_finding(
                "replay_log_missing_memory_ledger_snapshot",
                "Replay log has no memory ledger snapshot event.",
            )
        )

    return tuple(findings)
