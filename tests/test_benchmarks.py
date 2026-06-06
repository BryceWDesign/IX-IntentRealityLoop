from datetime import UTC, datetime

import pytest

from ix_intent_reality_loop.benchmarks import (
    BenchmarkExpectedOutcome,
    BenchmarkScenario,
    BenchmarkScenarioKind,
    benchmark_catalog,
    run_benchmark_scenario,
    validate_benchmark_catalog,
)
from ix_intent_reality_loop.core import BoundedScore, EvidenceStatus, ValidationSeverity
from ix_intent_reality_loop.focus import FocusRequirement, FocusSignal
from ix_intent_reality_loop.memory import MemoryBindingAction
from ix_intent_reality_loop.permission import PermissionScope


def test_benchmark_catalog_contains_required_scenario_kinds() -> None:
    scenarios = benchmark_catalog()
    findings = validate_benchmark_catalog(scenarios)

    assert not findings
    assert {scenario.kind for scenario in scenarios} == set(BenchmarkScenarioKind)
    assert len(scenarios) == 5


def test_benchmark_scenario_rejects_empty_requirements() -> None:
    with pytest.raises(ValueError, match="requirements must not be empty"):
        BenchmarkScenario(
            scenario_id="bad-scenario",
            kind=BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION,
            raw_request="Simulate.",
            interpreted_goal="Simulate.",
            expected_outcome=BenchmarkExpectedOutcome.MEMORY_UPDATE,
            requested_scope=PermissionScope.SIMULATED_ACTION,
            intent_confidence=BoundedScore(0.9),
            requirements=(),
            attended_requirement_codes=(),
            consent_granted=True,
        )


def test_benchmark_scenario_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        BenchmarkScenario(
            scenario_id="bad-timestamp",
            kind=BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION,
            raw_request="Simulate.",
            interpreted_goal="Simulate.",
            expected_outcome=BenchmarkExpectedOutcome.MEMORY_UPDATE,
            requested_scope=PermissionScope.SIMULATED_ACTION,
            intent_confidence=BoundedScore(0.9),
            requirements=(
                FocusRequirement(
                    code="simulate",
                    description="Simulate only.",
                    signal=FocusSignal.SAFETY_BOUNDARY,
                ),
            ),
            attended_requirement_codes=("simulate",),
            consent_granted=True,
            created_at=datetime(2026, 1, 1),
        )


def test_run_benchmark_clear_bounded_action_promotes_memory() -> None:
    scenario = next(
        scenario
        for scenario in benchmark_catalog()
        if scenario.kind is BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION
    )

    result = run_benchmark_scenario(
        run_id="run-clear",
        scenario=scenario,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.passed_expectation
    assert result.evidence_status is EvidenceStatus.COMPLETE
    assert result.memory_decision.action is MemoryBindingAction.UPDATE
    assert result.memory_decision.permits_positive_memory_update


def test_run_benchmark_ambiguous_intent_defers() -> None:
    scenario = next(
        scenario
        for scenario in benchmark_catalog()
        if scenario.kind is BenchmarkScenarioKind.AMBIGUOUS_INTENT
    )

    result = run_benchmark_scenario(
        run_id="run-ambiguous",
        scenario=scenario,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.passed_expectation
    assert result.evidence_status is EvidenceStatus.COMPLETE
    assert result.permission_result.blocks_action


def test_run_benchmark_unsafe_live_actuation_refuses_or_safe_holds() -> None:
    scenario = next(
        scenario
        for scenario in benchmark_catalog()
        if scenario.kind is BenchmarkScenarioKind.UNSAFE_LIVE_ACTUATION
    )

    result = run_benchmark_scenario(
        run_id="run-unsafe",
        scenario=scenario,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.passed_expectation
    assert result.evidence_status is EvidenceStatus.COMPLETE
    assert result.permission_result.blocks_action or result.safety_result.blocks_action


def test_run_benchmark_stale_consent_defers() -> None:
    scenario = next(
        scenario
        for scenario in benchmark_catalog()
        if scenario.kind is BenchmarkScenarioKind.STALE_CONSENT
    )

    result = run_benchmark_scenario(
        run_id="run-stale-consent",
        scenario=scenario,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.passed_expectation
    assert result.permission_result.blocks_action


def test_run_benchmark_feedback_contradiction_quarantines_memory() -> None:
    scenario = next(
        scenario
        for scenario in benchmark_catalog()
        if scenario.kind is BenchmarkScenarioKind.FEEDBACK_CONTRADICTION
    )

    result = run_benchmark_scenario(
        run_id="run-contradiction",
        scenario=scenario,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert result.passed_expectation
    assert result.memory_decision.quarantines_memory
    assert result.memory_decision.action is MemoryBindingAction.QUARANTINE


def test_validate_benchmark_catalog_detects_duplicate_ids() -> None:
    scenario = benchmark_catalog()[0]

    findings = validate_benchmark_catalog((scenario, scenario))
    finding_codes = {finding.code for finding in findings}

    assert "benchmark_catalog_duplicate_ids" in finding_codes
    assert "benchmark_catalog_missing_required_kind" in finding_codes
    assert any(
        finding.severity is ValidationSeverity.BLOCKER for finding in findings
    )
