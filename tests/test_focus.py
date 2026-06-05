from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import BoundedScore, ValidationSeverity
from ix_intent_reality_loop.focus import (
    FocusRequirement,
    FocusRisk,
    FocusSignal,
    FocusSplitRecord,
    build_focus_split_record,
    validate_focus_split_record,
)


def test_focus_requirement_rejects_empty_code() -> None:
    with pytest.raises(ValueError, match="code must not be empty"):
        FocusRequirement(
            code=" ",
            description="User requested evidence.",
            signal=FocusSignal.EVIDENCE_REQUIREMENT,
        )


def test_focus_split_record_preserves_attended_and_omitted_requirements() -> None:
    record = FocusSplitRecord(
        record_id="focus-001",
        intent_id="intent-001",
        attended_requirement_codes=("summarize",),
        omitted_requirement_codes=("cite_evidence",),
        attention_score=BoundedScore(0.5),
        risk=FocusRisk.SPLIT,
        notes=("evidence citation was skipped",),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert record.has_omissions
    assert not record.blocks_action
    assert record.created_at.tzinfo is UTC


def test_focus_split_record_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        FocusSplitRecord(
            record_id="focus-002",
            intent_id="intent-002",
            attended_requirement_codes=("summarize",),
            omitted_requirement_codes=(),
            attention_score=BoundedScore(1.0),
            risk=FocusRisk.CLEAR,
            created_at=datetime(2026, 1, 1),
        )


def test_build_focus_split_record_marks_clear_when_all_requirements_attended() -> None:
    requirements = (
        FocusRequirement(
            code="summarize",
            description="Summarize the packet.",
            signal=FocusSignal.REQUEST_TERM,
        ),
        FocusRequirement(
            code="cite_evidence",
            description="Cite evidence lines.",
            signal=FocusSignal.EVIDENCE_REQUIREMENT,
        ),
    )

    record = build_focus_split_record(
        record_id="focus-003",
        intent_id="intent-003",
        requirements=requirements,
        attended_requirement_codes=("summarize", "cite_evidence"),
    )

    assert record.risk is FocusRisk.CLEAR
    assert record.attention_score.value == 1.0
    assert not validate_focus_split_record(record)


def test_build_focus_split_record_marks_split_when_nonblocking_item_is_omitted() -> None:
    requirements = (
        FocusRequirement(
            code="summarize",
            description="Summarize the packet.",
            signal=FocusSignal.REQUEST_TERM,
        ),
        FocusRequirement(
            code="mention_limits",
            description="Mention uncertainty limits.",
            signal=FocusSignal.OUTCOME_REQUIREMENT,
        ),
    )

    record = build_focus_split_record(
        record_id="focus-004",
        intent_id="intent-004",
        requirements=requirements,
        attended_requirement_codes=("summarize",),
    )

    findings = validate_focus_split_record(record)
    finding_codes = {finding.code for finding in findings}

    assert record.risk is FocusRisk.SPLIT
    assert "focus_split_detected" in finding_codes


def test_build_focus_split_record_blocks_when_blocking_requirement_is_omitted() -> None:
    requirements = (
        FocusRequirement(
            code="confirm_permission",
            description="Confirm human permission before action.",
            signal=FocusSignal.PERMISSION_BOUNDARY,
            is_blocking=True,
        ),
        FocusRequirement(
            code="describe_action",
            description="Describe the bounded action.",
            signal=FocusSignal.REQUEST_TERM,
        ),
    )

    record = build_focus_split_record(
        record_id="focus-005",
        intent_id="intent-005",
        requirements=requirements,
        attended_requirement_codes=("describe_action",),
    )

    findings = validate_focus_split_record(record)

    assert record.risk is FocusRisk.BLOCKED
    assert record.blocks_action
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )


def test_build_focus_split_record_marks_glossed_over_when_most_items_are_omitted() -> None:
    requirements = (
        FocusRequirement(
            code="literal_request",
            description="Attend to literal request.",
            signal=FocusSignal.REQUEST_TERM,
        ),
        FocusRequirement(
            code="constraint",
            description="Attend to user constraint.",
            signal=FocusSignal.CONSTRAINT,
        ),
        FocusRequirement(
            code="outcome",
            description="Attend to expected outcome.",
            signal=FocusSignal.OUTCOME_REQUIREMENT,
        ),
    )

    record = build_focus_split_record(
        record_id="focus-006",
        intent_id="intent-006",
        requirements=requirements,
        attended_requirement_codes=("literal_request",),
    )

    findings = validate_focus_split_record(record)
    finding_codes = {finding.code for finding in findings}

    assert record.risk is FocusRisk.GLOSSED_OVER
    assert record.blocks_action
    assert "focus_glossed_over_request" in finding_codes


def test_build_focus_split_record_rejects_unknown_attended_codes() -> None:
    requirements = (
        FocusRequirement(
            code="known",
            description="Known requirement.",
            signal=FocusSignal.REQUEST_TERM,
        ),
    )

    with pytest.raises(ValueError, match="attended requirement code"):
        build_focus_split_record(
            record_id="focus-007",
            intent_id="intent-007",
            requirements=requirements,
            attended_requirement_codes=("unknown",),
        )


def test_build_focus_split_record_rejects_empty_requirements() -> None:
    with pytest.raises(ValueError, match="requirements must not be empty"):
        build_focus_split_record(
            record_id="focus-008",
            intent_id="intent-008",
            requirements=(),
            attended_requirement_codes=(),
        )
