from datetime import datetime

import pytest

from ix_intent_reality_loop.core import ValidationSeverity
from ix_intent_reality_loop.replay import (
    ReplayEvent,
    ReplayEventLog,
    ReplayEventType,
    build_replay_event,
    has_required_order,
    missing_required_event_types,
    required_replay_event_sequence,
    validate_replay_event_log,
)


def _event(
    *,
    event_id: str,
    event_type: ReplayEventType,
    intent_id: str = "intent-001",
) -> ReplayEvent:
    return build_replay_event(
        event_id=event_id,
        intent_id=intent_id,
        event_type=event_type,
        subject_id=f"{event_type.value}-subject",
        summary=f"{event_type.value} summary.",
        payload={"event_type": event_type.value},
    )


def _complete_events() -> tuple[ReplayEvent, ...]:
    return tuple(
        _event(
            event_id=f"event-{index:03d}",
            event_type=event_type,
        )
        for index, event_type in enumerate(required_replay_event_sequence(), start=1)
    )


def test_replay_event_preserves_read_only_payload() -> None:
    event = build_replay_event(
        event_id="event-001",
        intent_id="intent-001",
        event_type=ReplayEventType.INTENT_PACKET,
        subject_id="intent-001",
        summary="Intent packet recorded.",
        payload={"confidence": "0.91"},
    )

    assert event.payload["confidence"] == "0.91"
    with pytest.raises(TypeError):
        event.payload["new"] = "value"  # type: ignore[index]


def test_replay_event_rejects_empty_payload_values() -> None:
    with pytest.raises(ValueError, match="payload value must not be empty"):
        build_replay_event(
            event_id="event-002",
            intent_id="intent-001",
            event_type=ReplayEventType.INTENT_PACKET,
            subject_id="intent-001",
            summary="Intent packet recorded.",
            payload={"confidence": " "},
        )


def test_replay_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        ReplayEvent(
            event_id="event-003",
            intent_id="intent-001",
            event_type=ReplayEventType.INTENT_PACKET,
            subject_id="intent-001",
            summary="Intent packet recorded.",
            created_at=datetime(2026, 1, 1),
        )


def test_replay_event_log_appends_immutably() -> None:
    log = ReplayEventLog(log_id="replay-001", intent_id="intent-001")
    event = _event(
        event_id="event-004",
        event_type=ReplayEventType.INTENT_PACKET,
    )

    updated = log.append(event)

    assert log.events == ()
    assert updated.events == (event,)
    assert updated.event_types == (ReplayEventType.INTENT_PACKET,)


def test_replay_event_log_rejects_duplicate_event_ids() -> None:
    event = _event(
        event_id="duplicate",
        event_type=ReplayEventType.INTENT_PACKET,
    )

    with pytest.raises(ValueError, match="unique event_id"):
        ReplayEventLog(
            log_id="replay-002",
            intent_id="intent-001",
            events=(event, event),
        )


def test_replay_event_log_rejects_mismatched_intent() -> None:
    event = _event(
        event_id="event-005",
        event_type=ReplayEventType.INTENT_PACKET,
        intent_id="intent-999",
    )

    with pytest.raises(ValueError, match="all replay events must match"):
        ReplayEventLog(
            log_id="replay-003",
            intent_id="intent-001",
            events=(event,),
        )


def test_missing_required_event_types_reports_absent_core_events() -> None:
    missing = missing_required_event_types(
        (
            ReplayEventType.INTENT_PACKET,
            ReplayEventType.FOCUS_SPLIT,
        )
    )

    assert ReplayEventType.LITERAL_LANE in missing
    assert ReplayEventType.MEMORY_BINDING in missing


def test_has_required_order_accepts_complete_ordered_sequence() -> None:
    assert has_required_order(required_replay_event_sequence())


def test_has_required_order_rejects_out_of_order_sequence() -> None:
    out_of_order = (
        ReplayEventType.INTENT_PACKET,
        ReplayEventType.FOCUS_SPLIT,
        ReplayEventType.INTERPRETED_LANE,
        ReplayEventType.LITERAL_LANE,
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

    assert not has_required_order(out_of_order)


def test_validate_replay_event_log_accepts_complete_ordered_log() -> None:
    log = ReplayEventLog(
        log_id="replay-004",
        intent_id="intent-001",
        events=_complete_events(),
    )

    findings = validate_replay_event_log(log)
    finding_codes = {finding.code for finding in findings}

    assert "replay_log_missing_required_events" not in finding_codes
    assert "replay_log_required_order_broken" not in finding_codes
    assert "replay_log_missing_memory_ledger_snapshot" in finding_codes


def test_validate_replay_event_log_blocks_empty_log() -> None:
    findings = validate_replay_event_log(
        ReplayEventLog(log_id="replay-005", intent_id="intent-001")
    )

    assert findings[0].code == "replay_log_empty"
    assert findings[0].severity is ValidationSeverity.BLOCKER


def test_validate_replay_event_log_blocks_missing_and_out_of_order_events() -> None:
    log = ReplayEventLog(
        log_id="replay-006",
        intent_id="intent-001",
        events=(
            _event(
                event_id="event-006",
                event_type=ReplayEventType.INTENT_PACKET,
            ),
            _event(
                event_id="event-007",
                event_type=ReplayEventType.INTERPRETED_LANE,
            ),
            _event(
                event_id="event-008",
                event_type=ReplayEventType.LITERAL_LANE,
            ),
        ),
    )

    findings = validate_replay_event_log(log)
    finding_codes = {finding.code for finding in findings}

    assert "replay_log_missing_required_events" in finding_codes
    assert "replay_log_required_order_broken" in finding_codes
    assert any(finding.severity is ValidationSeverity.BLOCKER for finding in findings)
