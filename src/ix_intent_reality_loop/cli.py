"""Command-line interface for IX-IntentRealityLoop.

The CLI runs deterministic non-actuating benchmarks and writes canonical JSON
exports. It is intentionally small: no network access, no live actuation, no
model calls, and no hidden state.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ix_intent_reality_loop.benchmarks import (
    BenchmarkScenario,
    BenchmarkScenarioKind,
    benchmark_catalog,
    validate_benchmark_catalog,
)
from ix_intent_reality_loop.core import ValidationSeverity, require_non_empty_text
from ix_intent_reality_loop.export import (
    export_artifact,
    write_artifact_export,
)
from ix_intent_reality_loop.negative_controls import (
    NegativeControlReport,
    run_negative_control_suite,
    validate_negative_control_report,
)
from ix_intent_reality_loop.pipeline import (
    IntentRealityLoopAssembly,
    assemble_benchmark_evidence,
)


@dataclass(frozen=True, slots=True)
class CliRunSummary:
    """Summary returned by CLI runner functions for tests and shell output."""

    exported_paths: tuple[Path, ...]
    benchmark_count: int
    negative_control_count: int
    blocker_count: int
    warning_count: int

    @property
    def passed(self) -> bool:
        """Return whether the CLI run has no blockers."""

        return self.blocker_count == 0


def build_parser() -> argparse.ArgumentParser:
    """Build the IX-IntentRealityLoop CLI parser."""

    parser = argparse.ArgumentParser(
        prog="ix-intent-reality-loop",
        description=(
            "Run non-actuating IX-IntentRealityLoop benchmarks and export "
            "digest-bound review artifacts."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run-benchmarks",
        help="Run deterministic benchmarks and write canonical JSON artifacts.",
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory where benchmark artifacts are written.",
    )
    run_parser.add_argument(
        "--scenario",
        choices=[kind.value for kind in BenchmarkScenarioKind],
        default=None,
        help="Optional single benchmark scenario kind to run.",
    )
    run_parser.add_argument(
        "--include-negative-controls",
        action="store_true",
        help="Also run and export the deterministic negative-control report.",
    )

    return parser


def run_benchmarks_to_exports(
    *,
    output_dir: Path,
    scenario_kind: BenchmarkScenarioKind | None = None,
    include_negative_controls: bool = False,
) -> CliRunSummary:
    """Run benchmark assemblies and write canonical exports."""

    scenarios = _selected_scenarios(scenario_kind)
    catalog_findings = validate_benchmark_catalog(benchmark_catalog())
    blocker_count = _count_blockers(catalog_findings)
    warning_count = _count_warnings(catalog_findings)
    exported_paths: list[Path] = []

    for scenario in scenarios:
        assembly = assemble_benchmark_evidence(
            assembly_id=f"{scenario.scenario_id}-assembly",
            scenario=scenario,
        )
        blocker_count += assembly.blocker_count
        warning_count += assembly.warning_count
        exported_paths.extend(
            _write_assembly_exports(output_dir=output_dir, assembly=assembly)
        )

    negative_control_count = 0
    if include_negative_controls:
        report = run_negative_control_suite(report_id="negative-control-report")
        negative_findings = validate_negative_control_report(report)
        blocker_count += _count_blockers(negative_findings)
        warning_count += _count_warnings(negative_findings)
        negative_control_count = len(report.results)
        exported_paths.append(
            _write_negative_control_export(output_dir=output_dir, report=report)
        )

    return CliRunSummary(
        exported_paths=tuple(exported_paths),
        benchmark_count=len(scenarios),
        negative_control_count=negative_control_count,
        blocker_count=blocker_count,
        warning_count=warning_count,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-benchmarks":
        scenario_kind = (
            None
            if args.scenario is None
            else BenchmarkScenarioKind(
                require_non_empty_text(args.scenario, "scenario")
            )
        )
        summary = run_benchmarks_to_exports(
            output_dir=args.output_dir,
            scenario_kind=scenario_kind,
            include_negative_controls=args.include_negative_controls,
        )
        print(_format_summary(summary))
        return 0 if summary.passed else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


def _selected_scenarios(
    scenario_kind: BenchmarkScenarioKind | None,
) -> tuple[BenchmarkScenario, ...]:
    """Return selected benchmark scenarios."""

    scenarios = benchmark_catalog()
    if scenario_kind is None:
        return scenarios

    return tuple(scenario for scenario in scenarios if scenario.kind is scenario_kind)


def _write_assembly_exports(
    *,
    output_dir: Path,
    assembly: IntentRealityLoopAssembly,
) -> tuple[Path, ...]:
    """Write canonical exports for one assembled benchmark."""

    scenario_dir = output_dir / assembly.run_result.scenario_id
    exports = (
        export_artifact(
            artifact_id=f"{assembly.assembly_id}-evidence-bundle",
            artifact_kind="evidence_bundle",
            artifact=assembly.evidence_bundle,
        ),
        export_artifact(
            artifact_id=f"{assembly.assembly_id}-replay-manifest",
            artifact_kind="replay_manifest",
            artifact=assembly.replay_manifest,
        ),
        export_artifact(
            artifact_id=f"{assembly.assembly_id}-blackfox-handoff",
            artifact_kind="blackfox_governance_handoff",
            artifact=assembly.blackfox_handoff,
        ),
        export_artifact(
            artifact_id=f"{assembly.assembly_id}-kernel-donor",
            artifact_kind="kernel_wave6_donor_packet",
            artifact=assembly.kernel_donor_packet,
        ),
    )

    return tuple(
        write_artifact_export(
            export=export,
            output_path=scenario_dir / f"{export.artifact_kind}.json",
        )
        for export in exports
    )


def _write_negative_control_export(
    *,
    output_dir: Path,
    report: NegativeControlReport,
) -> Path:
    """Write canonical negative-control report export."""

    export = export_artifact(
        artifact_id=report.report_id,
        artifact_kind="negative_control_report",
        artifact=report,
    )
    return write_artifact_export(
        export=export,
        output_path=output_dir / "negative_controls" / "report.json",
    )


def _count_blockers(findings: Sequence[object]) -> int:
    """Return blocker count for validation findings."""

    return sum(
        1
        for finding in findings
        if getattr(finding, "severity", None) is ValidationSeverity.BLOCKER
    )


def _count_warnings(findings: Sequence[object]) -> int:
    """Return warning count for validation findings."""

    return sum(
        1
        for finding in findings
        if getattr(finding, "severity", None) is ValidationSeverity.WARNING
    )


def _format_summary(summary: CliRunSummary) -> str:
    """Return human-readable CLI summary."""

    status = "PASS" if summary.passed else "BLOCKED"
    return (
        f"{status}: exported {len(summary.exported_paths)} artifact(s), "
        f"benchmarks={summary.benchmark_count}, "
        f"negative_controls={summary.negative_control_count}, "
        f"blockers={summary.blocker_count}, warnings={summary.warning_count}"
    )


__all__ = [
    "CliRunSummary",
    "build_parser",
    "main",
    "run_benchmarks_to_exports",
]
