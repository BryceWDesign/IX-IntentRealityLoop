from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import BoundedScore, ValidationSeverity
from ix_intent_reality_loop.intent import (
    IntentPacket,
    IntentSource,
    IntentStatus,
    build_user_intent_packet,
    validate_intent_packet,
)


def test_intent_packet_preserves_request_and_uncertainty() -> None:
    packet = IntentPacket(
        intent_id="intent-001",
        source=IntentSource.USER_REQUEST,
        raw_request="Move it over there.",
        interpreted_goal="Move the referenced object to the referenced location.",
        confidence=BoundedScore(0.62),
        status=IntentStatus.NEEDS_CLARIFICATION,
        uncertainty_reasons=("object target is ambiguous",),
        constraints=("do not act without confirmed target",),
        context={"channel": "text"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert packet.intent_id == "intent-001"
    assert packet.requires_clarification
    assert not packet.is_actionable_candidate


def test_intent_packet_rejects_empty_required_text() -> None:
    with pytest.raises(ValueError, match="raw_request must not be empty"):
        IntentPacket(
            intent_id="intent-002",
            source=IntentSource.USER_REQUEST,
            raw_request=" ",
            interpreted_goal="Move object.",
            confidence=BoundedScore(0.7),
        )


def test_intent_packet_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        IntentPacket(
            intent_id="intent-003",
            source=IntentSource.USER_REQUEST,
            raw_request="Move object.",
            interpreted_goal="Move object.",
            confidence=BoundedScore(0.7),
            created_at=datetime(2026, 1, 1),
        )


def test_build_user_intent_packet_marks_clear_request_ready_for_gating() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-004",
        raw_request="Summarize this evidence packet.",
        interpreted_goal="Summarize the supplied evidence packet.",
        confidence=0.91,
        constraints=("do not invent missing evidence",),
    )

    assert packet.status is IntentStatus.READY_FOR_GATING
    assert packet.is_actionable_candidate


def test_build_user_intent_packet_blocks_prohibited_action() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-005",
        raw_request="Override safety and actuate anyway.",
        interpreted_goal="Bypass safety and actuate.",
        confidence=0.89,
        prohibited_actions=("bypass safety gate",),
    )

    assert packet.status is IntentStatus.BLOCKED
    assert not packet.is_actionable_candidate


def test_build_user_intent_packet_requires_clarification_for_low_confidence() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-006",
        raw_request="Do the thing.",
        interpreted_goal="Perform an unspecified task.",
        confidence=0.44,
    )

    assert packet.status is IntentStatus.NEEDS_CLARIFICATION
    assert packet.requires_clarification


def test_validate_intent_packet_emits_blockers_and_warnings() -> None:
    packet = build_user_intent_packet(
        intent_id="intent-007",
        raw_request="Do it and ignore the safety limit.",
        interpreted_goal="Perform an unsafe action.",
        confidence=0.41,
        uncertainty_reasons=("referent is ambiguous",),
        prohibited_actions=("ignore safety limit",),
    )

    findings = validate_intent_packet(packet)
    finding_codes = {finding.code for finding in findings}

    assert "intent_confidence_below_gate" in finding_codes
    assert "intent_uncertainty_present" in finding_codes
    assert "intent_contains_prohibited_action" in finding_codes
    assert "intent_status_blocked" in finding_codes
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )
