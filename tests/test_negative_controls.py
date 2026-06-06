from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import ValidationSeverity
from ix_intent_reality_loop.negative_controls import (
    NegativeControlKind,
    NegativeControlOutcome,
    NegativeControlReport,
    NegativeControlResult,
    run_agi_overclaim_negative_control,
    run_contradiction_memory_promotion_negative_control,
    run_false_completion_negative_control,
    run_live_actuation_allow_negative_control,
    run_missing_consent_allow_negative_control,
    run_missing_replay_events_negative_control,
    run_negative_control_suite,
    validate_negative_control_report,
)


def test_agi_overclaim_negative_control_blocks_prohibited_claim() -> None:
    result = run_agi_overclaim_negative_control(control_id="negative-001")

    assert result.kind is NegativeControlKind.AGI_OVERCLAIM
    assert result.outcome is NegativeControlOutcome.BLOCKED_AS_EXPECTED
    assert result.passed
    assert any("certified agi" in code for code in result.finding_codes)


def test_missing_replay_events_negative_control_blocks_incomplete_log() -> None:
    result = run_missing_replay_events_negative_control(control_id="negative-002")

    assert result.kind is NegativeControlKind.MISSING_REPLAY_EVENTS
    assert result.passed
    assert "replay_log_missing_required_events" in result.finding_codes


def test_false_completion_negative_control_blocks_output_only_completion() -> None:
    result = run_false_completion_negative_control(control_id="negative-003")

    assert result.kind is NegativeControlKind.FALSE_COMPLETION
    assert result.passed
    assert "negative_false_completion_missing_doctrine" in result.finding_codes
    assert "negative_false_completion_missing_safety_evidence" in (
        result.finding_codes
    )


def test_contradiction_memory_promotion_negative_control_blocks_update() -> None:
    result = run_contradiction_memory_promotion_negative_control(
        control_id="negative-004",
    )

    assert result.kind is NegativeControlKind.CONTRADICTION_MEMORY_PROMOTION
    assert result.passed
    assert "memory_update_without_complete_evidence" in result.finding_codes
    assert "negative_contradiction_promoted_to_memory" in result.finding_codes


def test_missing_consent_allow_negative_control_blocks_allow() -> None:
    result = run_missing_consent_allow_negative_control(control_id="negative-005")

    assert result.kind is NegativeControlKind.MISSING_CONSENT_ALLOW
    assert result.passed
    assert "permission_gate_allowed_without_fresh_consent" in result.finding_codes


def test_live_actuation_allow_negative_control_blocks_allow() -> None:
    result = run_live_actuation_allow_negative_control(control_id="negative-006")

    assert result.kind is NegativeControlKind.LIVE_ACTUATION_ALLOW
    assert result.passed
    assert "permission_gate_live_actuation_requested" in result.finding_codes


def test_negative_control_suite_runs_all_required_controls() -> None:
    report = run_negative_control_suite(report_id="negative-report-001")
    findings = validate_negative_control_report(report)
    finding_codes = {finding.code for finding in findings}

    assert report.passed
    assert report.passed_count == len(NegativeControlKind)
    assert report.failed_count == 0
    assert {result.kind for result in report.results} == set(NegativeControlKind)
    assert "negative_controls_all_blocked_as_expected" in finding_codes


def test_negative_control_report_rejects_empty_results() -> None:
    with pytest.raises(ValueError, match="at least one result"):
        NegativeControlReport(
            report_id="negative-report-002",
            results=(),
            doctrine_rule_codes=("no_agi_overclaim",),
        )


def test_negative_control_report_rejects_duplicate_control_ids() -> None:
    result = NegativeControlResult(
        control_id="duplicate",
        kind=NegativeControlKind.AGI_OVERCLAIM,
        outcome=NegativeControlOutcome.BLOCKED_AS_EXPECTED,
        finding_codes=("prohibited_claim:certified agi",),
        summary="Duplicate result.",
    )

    with pytest.raises(ValueError, match="unique control_id"):
        NegativeControlReport(
            report_id="negative-report-003",
            results=(result, result),
            doctrine_rule_codes=("no_agi_overclaim",),
        )


def test_negative_control_result_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        NegativeControlResult(
            control_id="negative-007",
            kind=NegativeControlKind.AGI_OVERCLAIM,
            outcome=NegativeControlOutcome.BLOCKED_AS_EXPECTED,
            finding_codes=("prohibited_claim:certified agi",),
            summary="Naive timestamp result.",
            created_at=datetime(2026, 1, 1),
        )


def test_validate_negative_control_report_blocks_failed_control() -> None:
    result = NegativeControlResult(
        control_id="failed-control",
        kind=NegativeControlKind.AGI_OVERCLAIM,
        outcome=NegativeControlOutcome.FAILED_TO_BLOCK,
        finding_codes=(),
        summary="Failed to block prohibited claim.",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    report = NegativeControlReport(
        report_id="negative-report-004",
        results=(result,),
        doctrine_rule_codes=(),
    )

    findings = validate_negative_control_report(report)
    finding_codes = {finding.code for finding in findings}

    assert "negative_controls_missing_no_agi_doctrine" in finding_codes
    assert "negative_controls_missing_completion_doctrine" in finding_codes
    assert "negative_controls_missing_required_kind" in finding_codes
    assert "negative_controls_failed_to_block" in finding_codes
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )
