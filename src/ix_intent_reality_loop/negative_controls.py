"""Negative controls and anti-theater checks.

Negative controls prove the runtime is willing to fail closed. These checks are
not decorative tests. They exercise known bad patterns: AGI overclaims, missing
replay events, false completion, memory promotion from contradiction, missing
consent, and live physical actuation attempts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ix_intent_reality_loop.action import ActionMode, BoundedActionDecision
from ix_intent_reality_loop.core import (
    AuthorityState,
    BoundedScore,
    DecisionDisposition,
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
    warning_finding,
)
from ix_intent_reality_loop.doctrine import find_prohibited_claims
from ix_intent_reality_loop.memory import (
    MemoryBindingAction,
    MemoryBindingDecision,
    MemoryBindingReason,
    validate_memory_binding_decision,
)
from ix_intent_reality_loop.permission import (
    ConsentStatus,
    PermissionGateResult,
    PermissionScope,
    validate_permission_gate_result,
)
from ix_intent_reality_loop.replay import (
    ReplayEventLog,
    ReplayEventType,
    build_replay_event,
    validate_replay_event_log,
)


class NegativeControlKind(StrEnum):
    """Canonical negative control kinds."""

    AGI_OVERCLAIM = "agi_overclaim"
    MISSING_REPLAY_EVENTS = "missing_replay_events"
    FALSE_COMPLETION = "false_completion"
    CONTRADICTION_MEMORY_PROMOTION = "contradiction_memory_promotion"
    MISSING_CONSENT_ALLOW = "missing_consent_allow"
    LIVE_ACTUATION_ALLOW = "live_actuation_allow"


class NegativeControlOutcome(StrEnum):
    """Expected outcome of a negative control."""

    BLOCKED_AS_EXPECTED = "blocked_as_expected"
    FAILED_TO_BLOCK = "failed_to_block"


@dataclass(frozen=True, slots=True)
class NegativeControlResult:
    """Result of one negative control run."""

    control_id: str
    kind: NegativeControlKind
    outcome: NegativeControlOutcome
    finding_codes: tuple[str, ...]
    summary: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "control_id",
            require_non_empty_text(self.control_id, "control_id"),
        )
        object.__setattr__(
            self,
            "finding_codes",
            tuple(
                require_non_empty_text(code, "finding_code")
                for code in self.finding_codes
            ),
        )
        object.__setattr__(
            self,
            "summary",
            require_non_empty_text(self.summary, "summary"),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def passed(self) -> bool:
        """Return whether the negative control blocked the bad pattern."""

        return self.outcome is NegativeControlOutcome.BLOCKED_AS_EXPECTED


@dataclass(frozen=True, slots=True)
class NegativeControlReport:
    """Aggregated negative-control report."""

    report_id: str
    results: tuple[NegativeControlResult, ...]
    doctrine_rule_codes: tuple[str, ...]
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "report_id",
            require_non_empty_text(self.report_id, "report_id"),
        )
        if not self.results:
            raise ValueError("negative control report requires at least one result")
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

        control_ids = [result.control_id for result in self.results]
        if len(control_ids) != len(set(control_ids)):
            raise ValueError(
                "negative control results must use unique control_id values"
            )

    @property
    def passed_count(self) -> int:
        """Return count of negative controls that blocked as expected."""

        return sum(1 for result in self.results if result.passed)

    @property
    def failed_count(self) -> int:
        """Return count of negative controls that failed to block."""

        return len(self.results) - self.passed_count

    @property
    def passed(self) -> bool:
        """Return whether all negative controls blocked as expected."""

        return self.failed_count == 0


def run_agi_overclaim_negative_control(*, control_id: str) -> NegativeControlResult:
    """Verify prohibited AGI claims are detected."""

    claims = find_prohibited_claims(
        "This system has true AGI achieved and is certified AGI."
    )
    return _result_from_block_condition(
        control_id=control_id,
        kind=NegativeControlKind.AGI_OVERCLAIM,
        blocked=bool(claims),
        finding_codes=tuple(f"prohibited_claim:{claim}" for claim in claims),
        summary="AGI overclaim negative control.",
    )


def run_missing_replay_events_negative_control(
    *,
    control_id: str,
) -> NegativeControlResult:
    """Verify incomplete replay logs are blocked."""

    log = ReplayEventLog(
        log_id="negative-replay-log",
        intent_id="negative-intent",
        events=(
            build_replay_event(
                event_id="negative-event-001",
                intent_id="negative-intent",
                event_type=ReplayEventType.INTENT_PACKET,
                subject_id="negative-intent",
                summary="Only intent packet was recorded.",
            ),
        ),
    )
    findings = validate_replay_event_log(log)
    blocker_codes = _blocker_codes(findings)
    return _result_from_block_condition(
        control_id=control_id,
        kind=NegativeControlKind.MISSING_REPLAY_EVENTS,
        blocked=bool(blocker_codes),
        finding_codes=blocker_codes,
        summary="Missing replay events negative control.",
    )


def run_false_completion_negative_control(*, control_id: str) -> NegativeControlResult:
    """Verify output-only completion is blocked as an action decision."""

    decision = BoundedActionDecision(
        action_id="negative-action",
        intent_id="negative-intent",
        safety_gate_id="negative-safety",
        mode=ActionMode.TEXT_RESPONSE,
        disposition=DecisionDisposition.ALLOW,
        selected_action="Treat generated text as completion.",
        predicted_outcome="The task is complete because output exists.",
        confidence=BoundedScore(0.95),
        doctrine_rule_codes=("thought_not_action",),
        preserved_safety_signals=(),
        execution_limits=(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    findings = _validate_false_completion_action(decision)
    blocker_codes = _blocker_codes(findings)
    return _result_from_block_condition(
        control_id=control_id,
        kind=NegativeControlKind.FALSE_COMPLETION,
        blocked=bool(blocker_codes),
        finding_codes=blocker_codes,
        summary="False completion negative control.",
    )


def run_contradiction_memory_promotion_negative_control(
    *,
    control_id: str,
) -> NegativeControlResult:
    """Verify contradicted outcomes cannot be promoted as positive memory."""

    decision = MemoryBindingDecision(
        memory_decision_id="negative-memory",
        intent_id="negative-intent",
        delta_id="negative-delta",
        action=MemoryBindingAction.UPDATE,
        reason=MemoryBindingReason.CONTRADICTED_OUTCOME,
        evidence_status=EvidenceStatus.REJECTED,
        confidence_after_binding=BoundedScore(0.95),
        rationale="Invalidly promote contradicted memory.",
        doctrine_rule_codes=(
            "reality_gets_vote",
            "evidence_before_claim",
            "completion_not_output",
        ),
        memory_keys=("contradicted_memory",),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    findings = (
        *validate_memory_binding_decision(decision),
        *_contradiction_promotion_findings(decision),
    )
    blocker_codes = _blocker_codes(findings)
    return _result_from_block_condition(
        control_id=control_id,
        kind=NegativeControlKind.CONTRADICTION_MEMORY_PROMOTION,
        blocked=bool(blocker_codes),
        finding_codes=blocker_codes,
        summary="Contradiction memory promotion negative control.",
    )


def run_missing_consent_allow_negative_control(
    *,
    control_id: str,
) -> NegativeControlResult:
    """Verify allow decisions without fresh consent are blocked."""

    result = PermissionGateResult(
        gate_id="negative-permission",
        intent_id="negative-intent",
        decision_id="negative-arbiter",
        requested_scope=PermissionScope.SIMULATED_ACTION,
        consent_status=ConsentStatus.ABSENT,
        disposition=DecisionDisposition.ALLOW,
        authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
        confidence=BoundedScore(0.9),
        rationale="Invalidly allow without consent.",
        doctrine_rule_codes=("intent_not_permission", "human_authority_persists"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    findings = validate_permission_gate_result(result)
    blocker_codes = _blocker_codes(findings)
    return _result_from_block_condition(
        control_id=control_id,
        kind=NegativeControlKind.MISSING_CONSENT_ALLOW,
        blocked=bool(blocker_codes),
        finding_codes=blocker_codes,
        summary="Missing consent allow negative control.",
    )


def run_live_actuation_allow_negative_control(
    *,
    control_id: str,
) -> NegativeControlResult:
    """Verify live physical actuation requests are blocked."""

    result = PermissionGateResult(
        gate_id="negative-live-permission",
        intent_id="negative-intent",
        decision_id="negative-arbiter",
        requested_scope=PermissionScope.LIVE_PHYSICAL_ACTUATION,
        consent_status=ConsentStatus.FRESH,
        disposition=DecisionDisposition.ALLOW,
        authority_state=AuthorityState.SYSTEM_RECOMMENDATION_ONLY,
        confidence=BoundedScore(0.9),
        rationale="Invalidly allow live physical actuation.",
        doctrine_rule_codes=("intent_not_permission", "human_authority_persists"),
        consent_id="negative-consent",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    findings = validate_permission_gate_result(result)
    blocker_codes = _blocker_codes(findings)
    return _result_from_block_condition(
        control_id=control_id,
        kind=NegativeControlKind.LIVE_ACTUATION_ALLOW,
        blocked=bool(blocker_codes),
        finding_codes=blocker_codes,
        summary="Live physical actuation allow negative control.",
    )


def run_negative_control_suite(*, report_id: str) -> NegativeControlReport:
    """Run all deterministic negative controls."""

    return NegativeControlReport(
        report_id=report_id,
        results=(
            run_agi_overclaim_negative_control(control_id="negative-agi-overclaim"),
            run_missing_replay_events_negative_control(
                control_id="negative-missing-replay-events",
            ),
            run_false_completion_negative_control(
                control_id="negative-false-completion",
            ),
            run_contradiction_memory_promotion_negative_control(
                control_id="negative-contradiction-memory-promotion",
            ),
            run_missing_consent_allow_negative_control(
                control_id="negative-missing-consent-allow",
            ),
            run_live_actuation_allow_negative_control(
                control_id="negative-live-actuation-allow",
            ),
        ),
        doctrine_rule_codes=(
            "thought_not_action",
            "intent_not_permission",
            "completion_not_output",
            "evidence_before_claim",
            "no_agi_overclaim",
        ),
    )


def validate_negative_control_report(
    report: NegativeControlReport,
) -> tuple[ValidationFinding, ...]:
    """Validate a negative-control report before downstream evidence handoff."""

    findings: list[ValidationFinding] = []

    if "no_agi_overclaim" not in report.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "negative_controls_missing_no_agi_doctrine",
                "Negative controls must cite no_agi_overclaim doctrine.",
            )
        )

    if "completion_not_output" not in report.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "negative_controls_missing_completion_doctrine",
                "Negative controls must cite completion_not_output doctrine.",
            )
        )

    expected_kinds = set(NegativeControlKind)
    present_kinds = {result.kind for result in report.results}
    missing_kinds = expected_kinds.difference(present_kinds)
    if missing_kinds:
        joined = ", ".join(kind.value for kind in sorted(missing_kinds))
        findings.append(
            blocker_finding(
                "negative_controls_missing_required_kind",
                f"Negative controls missing required kind(s): {joined}.",
            )
        )

    failed_results = tuple(result for result in report.results if not result.passed)
    if failed_results:
        joined = ", ".join(result.control_id for result in failed_results)
        findings.append(
            blocker_finding(
                "negative_controls_failed_to_block",
                f"Negative controls failed to block: {joined}.",
            )
        )

    if report.passed:
        findings.append(
            warning_finding(
                "negative_controls_all_blocked_as_expected",
                "All negative controls blocked known-bad patterns as expected.",
            )
        )

    return tuple(findings)


def _result_from_block_condition(
    *,
    control_id: str,
    kind: NegativeControlKind,
    blocked: bool,
    finding_codes: tuple[str, ...],
    summary: str,
) -> NegativeControlResult:
    """Build a negative-control result from a block condition."""

    return NegativeControlResult(
        control_id=control_id,
        kind=kind,
        outcome=(
            NegativeControlOutcome.BLOCKED_AS_EXPECTED
            if blocked
            else NegativeControlOutcome.FAILED_TO_BLOCK
        ),
        finding_codes=finding_codes,
        summary=summary,
    )


def _blocker_codes(findings: tuple[ValidationFinding, ...]) -> tuple[str, ...]:
    """Return blocker finding codes."""

    return tuple(
        finding.code
        for finding in findings
        if finding.severity is ValidationSeverity.BLOCKER
    )


def _validate_false_completion_action(
    decision: BoundedActionDecision,
) -> tuple[ValidationFinding, ...]:
    """Validate an intentionally bad output-as-completion action decision."""

    findings: list[ValidationFinding] = []

    if "completion_not_output" not in decision.doctrine_rule_codes:
        findings.append(
            blocker_finding(
                "negative_false_completion_missing_doctrine",
                "Output-only completion must be blocked by completion doctrine.",
            )
        )

    if decision.can_enter_feedback_loop and not decision.preserved_safety_signals:
        findings.append(
            blocker_finding(
                "negative_false_completion_missing_safety_evidence",
                "Output-only completion lacks safety evidence.",
            )
        )

    if decision.can_enter_feedback_loop and "no live physical actuation" not in (
        decision.execution_limits
    ):
        findings.append(
            blocker_finding(
                "negative_false_completion_missing_execution_limits",
                "Output-only completion lacks execution limits.",
            )
        )

    return tuple(findings)


def _contradiction_promotion_findings(
    decision: MemoryBindingDecision,
) -> tuple[ValidationFinding, ...]:
    """Return findings when contradicted memory is invalidly promoted."""

    if (
        decision.action is MemoryBindingAction.UPDATE
        and decision.reason is MemoryBindingReason.CONTRADICTED_OUTCOME
    ):
        return (
            blocker_finding(
                "negative_contradiction_promoted_to_memory",
                "Contradicted outcome cannot be promoted as positive memory.",
            ),
        )

    return ()
