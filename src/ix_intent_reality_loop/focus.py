"""Focus split and gloss-over detection.

This layer records whether an execution path is attending to the whole request
or silently dropping constraints. It exists because a governed agency loop must
not treat partial attention as successful interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)


class FocusRisk(StrEnum):
    """Risk classification for request attention."""

    CLEAR = "clear"
    SPLIT = "split"
    GLOSSED_OVER = "glossed_over"
    BLOCKED = "blocked"


class FocusSignal(StrEnum):
    """Canonical focus signals used by attention records."""

    REQUEST_TERM = "request_term"
    CONSTRAINT = "constraint"
    SAFETY_BOUNDARY = "safety_boundary"
    PERMISSION_BOUNDARY = "permission_boundary"
    OUTCOME_REQUIREMENT = "outcome_requirement"
    EVIDENCE_REQUIREMENT = "evidence_requirement"


@dataclass(frozen=True, slots=True)
class FocusRequirement:
    """A required element that an execution path must attend to."""

    code: str
    description: str
    signal: FocusSignal
    is_blocking: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_non_empty_text(self.code, "code"))
        object.__setattr__(
            self,
            "description",
            require_non_empty_text(self.description, "description"),
        )


@dataclass(frozen=True, slots=True)
class FocusSplitRecord:
    """Record showing which request requirements were or were not attended."""

    record_id: str
    intent_id: str
    attended_requirement_codes: tuple[str, ...]
    omitted_requirement_codes: tuple[str, ...]
    attention_score: BoundedScore
    risk: FocusRisk
    notes: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            require_non_empty_text(self.record_id, "record_id"),
        )
        object.__setattr__(
            self,
            "intent_id",
            require_non_empty_text(self.intent_id, "intent_id"),
        )
        object.__setattr__(
            self,
            "attended_requirement_codes",
            tuple(
                require_non_empty_text(code, "attended_requirement_code")
                for code in self.attended_requirement_codes
            ),
        )
        object.__setattr__(
            self,
            "omitted_requirement_codes",
            tuple(
                require_non_empty_text(code, "omitted_requirement_code")
                for code in self.omitted_requirement_codes
            ),
        )
        object.__setattr__(
            self,
            "notes",
            tuple(require_non_empty_text(note, "note") for note in self.notes),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def has_omissions(self) -> bool:
        """Return whether required request elements were omitted."""

        return bool(self.omitted_requirement_codes)

    @property
    def blocks_action(self) -> bool:
        """Return whether focus risk blocks permission or action gating."""

        return self.risk in {FocusRisk.GLOSSED_OVER, FocusRisk.BLOCKED}


def build_focus_split_record(
    *,
    record_id: str,
    intent_id: str,
    requirements: tuple[FocusRequirement, ...],
    attended_requirement_codes: tuple[str, ...],
    notes: tuple[str, ...] = (),
) -> FocusSplitRecord:
    """Build a focus split record from required and attended request elements."""

    if not requirements:
        raise ValueError("requirements must not be empty")

    requirement_codes = tuple(requirement.code for requirement in requirements)
    requirement_code_set = set(requirement_codes)
    attended_code_set = set(attended_requirement_codes)
    unknown_attended_codes = attended_code_set.difference(requirement_code_set)
    if unknown_attended_codes:
        joined_codes = ", ".join(sorted(unknown_attended_codes))
        raise ValueError(f"attended requirement code(s) not required: {joined_codes}")

    omitted_codes = tuple(
        code for code in requirement_codes if code not in attended_code_set
    )
    attended_codes = tuple(
        code for code in requirement_codes if code in attended_code_set
    )
    attention_score = BoundedScore(len(attended_codes) / len(requirement_codes))

    omitted_blocking_codes = {
        requirement.code
        for requirement in requirements
        if requirement.is_blocking and requirement.code in omitted_codes
    }

    if omitted_blocking_codes:
        risk = FocusRisk.BLOCKED
    elif attention_score.value < 0.5:
        risk = FocusRisk.GLOSSED_OVER
    elif omitted_codes:
        risk = FocusRisk.SPLIT
    else:
        risk = FocusRisk.CLEAR

    return FocusSplitRecord(
        record_id=record_id,
        intent_id=intent_id,
        attended_requirement_codes=attended_codes,
        omitted_requirement_codes=omitted_codes,
        attention_score=attention_score,
        risk=risk,
        notes=notes,
    )


def validate_focus_split_record(
    record: FocusSplitRecord,
) -> tuple[ValidationFinding, ...]:
    """Validate whether focus attention can proceed toward arbitration."""

    findings: list[ValidationFinding] = []

    if record.risk is FocusRisk.BLOCKED:
        findings.append(
            blocker_finding(
                "focus_blocking_requirement_omitted",
                "A blocking request, safety, permission, or evidence boundary "
                "was omitted.",
            )
        )

    if record.risk is FocusRisk.GLOSSED_OVER:
        findings.append(
            blocker_finding(
                "focus_glossed_over_request",
                "The execution path omitted most required request elements.",
            )
        )

    if record.risk is FocusRisk.SPLIT:
        findings.append(
            warning_finding(
                "focus_split_detected",
                "The execution path attended to only part of the request.",
            )
        )

    if record.attention_score.is_below(0.75):
        findings.append(
            warning_finding(
                "focus_attention_below_target",
                "Attention score is below the target threshold for confident "
                "execution.",
            )
        )

    return tuple(findings)
