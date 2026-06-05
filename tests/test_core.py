from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    EvidenceStatus,
    ValidationSeverity,
    blocker_finding,
    clamp_score,
    require_aware_utc,
    require_mapping,
    require_non_empty_text,
    utc_now,
    warning_finding,
)


def test_core_enums_preserve_governed_decision_vocabulary() -> None:
    assert DecisionDisposition.ALLOW == "allow"
    assert DecisionDisposition.SAFE_HOLD == "safe_hold"
    assert AuthorityState.SYSTEM_RECOMMENDATION_ONLY == (
        "system_recommendation_only"
    )
    assert EvidenceStatus.COMPLETE == "complete"
    assert ValidationSeverity.BLOCKER == "blocker"


def test_bounded_score_accepts_closed_interval() -> None:
    assert BoundedScore(0).value == 0.0
    assert BoundedScore(0.5).value == 0.5
    assert BoundedScore(1).value == 1.0


def test_bounded_score_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        BoundedScore(-0.01)

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        BoundedScore(1.01)

    with pytest.raises(TypeError, match="numeric"):
        BoundedScore(True)


def test_bounded_score_threshold_helpers_validate_thresholds() -> None:
    score = BoundedScore(0.75)

    assert score.is_at_least(0.75)
    assert score.is_below(0.9)

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        score.is_at_least(2.0)


def test_require_non_empty_text_strips_valid_text() -> None:
    assert require_non_empty_text("  valid  ", "field") == "valid"


def test_require_non_empty_text_rejects_invalid_text() -> None:
    with pytest.raises(TypeError, match="field must be a string"):
        require_non_empty_text(123, "field")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="field must not be empty"):
        require_non_empty_text("   ", "field")


def test_require_mapping_returns_string_keyed_copy() -> None:
    source = {"intent": "move", "confidence": 0.8}

    result = require_mapping(source, "payload")

    assert result == source
    assert result is not source


def test_require_mapping_rejects_non_mapping_or_non_string_keys() -> None:
    with pytest.raises(TypeError, match="payload must be a dictionary"):
        require_mapping([], "payload")

    with pytest.raises(TypeError, match="payload must use string keys"):
        require_mapping({1: "bad"}, "payload")


def test_utc_now_returns_aware_utc_timestamp() -> None:
    timestamp = utc_now()

    assert timestamp.tzinfo is UTC


def test_require_aware_utc_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        require_aware_utc(datetime(2026, 1, 1), "created_at")


def test_require_aware_utc_accepts_aware_datetime() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    assert require_aware_utc(timestamp, "created_at") == timestamp


def test_validation_finding_builders_create_expected_severity() -> None:
    blocker = blocker_finding("unsafe_intent", "Intent requires review.")
    warning = warning_finding("low_confidence", "Confidence is below target.")

    assert blocker.severity is ValidationSeverity.BLOCKER
    assert warning.severity is ValidationSeverity.WARNING
