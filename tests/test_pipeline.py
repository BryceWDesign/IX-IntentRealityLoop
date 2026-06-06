from datetime import UTC, datetime

from ix_intent_reality_loop.benchmarks import (
    BenchmarkScenario,
    BenchmarkScenarioKind,
    benchmark_catalog,
    run_benchmark_scenario,
)
from ix_intent_reality_loop.core import ValidationSeverity
from ix_intent_reality_loop.kernel_handoff import KernelDonorStatus
from ix_intent_reality_loop.pipeline import (
    assemble_benchmark_evidence,
    build_replay_log_from_run_result,
    validate_assembly_links,
)
from ix_intent_reality_loop.replay import (
    ReplayEventType,
    validate_replay_event_log,
)


def _scenario(kind: BenchmarkScenarioKind) -> BenchmarkScenario:
    return next(scenario for scenario in benchmark_catalog() if scenario.kind is kind)


def test_build_replay_log_from_run_result_contains_full_event_sequence() -> None:
    run_result = run_benchmark_scenario(
        run_id="run-clear",
        scenario=_scenario(BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    replay_log = build_replay_log_from_run_result(
        log_id="replay-clear",
        run_result=run_result,
    )
    findings = validate_replay_event_log(replay_log)
    finding_codes = {finding.code for finding in findings}

    assert replay_log.event_types[:3] == (
        ReplayEventType.INTENT_PACKET,
        ReplayEventType.FOCUS_SPLIT,
        ReplayEventType.LITERAL_LANE,
    )
    assert ReplayEventType.MEMORY_LEDGER in replay_log.event_types
    assert "replay_log_missing_required_events" not in finding_codes
    assert "replay_log_required_order_broken" not in finding_codes


def test_assemble_benchmark_evidence_produces_kernel_ready_clear_case() -> None:
    assembly = assemble_benchmark_evidence(
        assembly_id="assembly-clear",
        scenario=_scenario(BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert assembly.run_result.passed_expectation
    assert assembly.replay_log.intent_id == assembly.run_result.intent_packet.intent_id
    assert assembly.memory_ledger.positive_update_count == 1
    assert assembly.evidence_bundle.blocker_count == 0
    assert assembly.kernel_donor_packet.donor_status is (
        KernelDonorStatus.READY_FOR_REVIEW
    )
    assert assembly.is_kernel_review_ready


def test_assemble_benchmark_evidence_blocks_unsafe_live_actuation_case() -> None:
    assembly = assemble_benchmark_evidence(
        assembly_id="assembly-unsafe",
        scenario=_scenario(BenchmarkScenarioKind.UNSAFE_LIVE_ACTUATION),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert assembly.run_result.passed_expectation
    assert assembly.run_result.permission_result.blocks_action
    assert assembly.memory_ledger.quarantine_count == 1
    assert assembly.kernel_donor_packet.donor_status is not (
        KernelDonorStatus.READY_FOR_REVIEW
    )


def test_assemble_benchmark_evidence_quarantines_contradiction_case() -> None:
    assembly = assemble_benchmark_evidence(
        assembly_id="assembly-contradiction",
        scenario=_scenario(BenchmarkScenarioKind.FEEDBACK_CONTRADICTION),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert assembly.run_result.passed_expectation
    assert assembly.run_result.memory_decision.quarantines_memory
    assert assembly.memory_ledger.quarantine_count == 1
    assert "prediction_contradicted" in assembly.memory_ledger.quarantine_tags()


def test_validate_assembly_links_detects_cross_artifact_mismatch() -> None:
    assembly = assemble_benchmark_evidence(
        assembly_id="assembly-mismatch-source",
        scenario=_scenario(BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION),
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    mismatched_findings = validate_assembly_links(
        run_result=assembly.run_result,
        replay_log=assembly.replay_log,
        memory_ledger=assembly.memory_ledger,
        evidence_bundle=assembly.evidence_bundle,
        replay_manifest=assembly.replay_manifest,
        blackfox_handoff=assembly.blackfox_handoff,
        kernel_donor_packet=assembly.kernel_donor_packet,
    )

    assert not any(
        finding.severity is ValidationSeverity.BLOCKER
        for finding in mismatched_findings
    )
