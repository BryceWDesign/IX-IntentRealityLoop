"""Core primitives for governed agency-loop records.

These primitives are intentionally small and strict. They prevent later layers
from treating empty text, invalid confidence, unsafe timestamps, or ambiguous
decision labels as acceptable evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ValidationSeverity(StrEnum):
    """Severity of a validation finding."""

    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class AuthorityState(StrEnum):
    """Human-authority state for a runtime decision."""

    HUMAN_REVIEW_REQUIRED = "human_review_required"
    HUMAN_ACCEPTED = "human_accepted"
    HUMAN_REJECTED = "human_rejected"
    SYSTEM_RECOMMENDATION_ONLY = "system_recommendation_only"


class DecisionDisposition(StrEnum):
    """Canonical disposition emitted by gates and arbiters."""

    ALLOW = "allow"
    CLAMP = "clamp"
    DEFER = "defer"
    REFUSE = "refuse"
    ESCALATE = "escalate"
    SAFE_HOLD = "safe_hold"
    QUARANTINE = "quarantine"


class EvidenceStatus(StrEnum):
    """Evidence status for replayable artifacts."""

    DRAFT = "draft"
    COMPLETE = "complete"
    DEGRADED = "degraded"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class BoundedScore:
    """A normalized score constrained to the closed interval [0.0, 1.0]."""

    value: float

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise TypeError("bounded score must be numeric")
        normalized_value = float(self.value)
        if not 0.0 <= normalized_value <= 1.0:
            raise ValueError("bounded score must be between 0.0 and 1.0")
        object.__setattr__(self, "value", normalized_value)

    def is_at_least(self, threshold: float) -> bool:
        """Return whether this score is greater than or equal to a threshold."""

        return self.value >= BoundedScore(threshold).value

    def is_below(self, threshold: float) -> bool:
        """Return whether this score is below a threshold."""

        return self.value < BoundedScore(threshold).value


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """A structured validation finding suitable for evidence records."""

    code: str
    message: str
    severity: ValidationSeverity

    def __post_init__(self) -> None:
        require_non_empty_text(self.code, "code")
        require_non_empty_text(self.message, "message")


def require_non_empty_text(value: str, field_name: str) -> str:
    """Return stripped text or raise when a required string is empty."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    stripped_value = value.strip()
    if not stripped_value:
        raise ValueError(f"{field_name} must not be empty")
    return stripped_value


def require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    """Return a shallow dict copy when value is a string-keyed mapping."""

    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dictionary")
    invalid_keys = [key for key in value if not isinstance(key, str)]
    if invalid_keys:
        raise TypeError(f"{field_name} must use string keys")
    return dict(value)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def require_aware_utc(timestamp: datetime, field_name: str) -> datetime:
    """Require a timezone-aware UTC datetime."""

    if not isinstance(timestamp, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    normalized = timestamp.astimezone(UTC)
    if normalized.tzinfo is not UTC:
        raise ValueError(f"{field_name} must normalize to UTC")
    return normalized


def clamp_score(value: float) -> BoundedScore:
    """Clamp a numeric value into a BoundedScore."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("score value must be numeric")
    return BoundedScore(max(0.0, min(1.0, float(value))))


def blocker_finding(code: str, message: str) -> ValidationFinding:
    """Build a blocker validation finding."""

    return ValidationFinding(
        code=code,
        message=message,
        severity=ValidationSeverity.BLOCKER,
    )


def warning_finding(code: str, message: str) -> ValidationFinding:
    """Build a warning validation finding."""

    return ValidationFinding(
        code=code,
        message=message,
        severity=ValidationSeverity.WARNING,
    )
