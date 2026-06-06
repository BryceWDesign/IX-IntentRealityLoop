from pathlib import Path

from ix_intent_reality_loop.benchmarks import BenchmarkScenarioKind
from ix_intent_reality_loop.cli import (
    build_parser,
    main,
    run_benchmarks_to_exports,
)


def test_build_parser_accepts_run_benchmarks_command() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "run-benchmarks",
            "--scenario",
            BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION.value,
            "--include-negative-controls",
        ]
    )

    assert args.command == "run-benchmarks"
    assert args.scenario == BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION.value
    assert args.include_negative_controls


def test_run_benchmarks_to_exports_writes_clear_case_artifacts(tmp_path: Path) -> None:
    summary = run_benchmarks_to_exports(
        output_dir=tmp_path,
        scenario_kind=BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION,
        include_negative_controls=False,
    )

    assert summary.passed
    assert summary.benchmark_count == 1
    assert summary.negative_control_count == 0
    assert len(summary.exported_paths) == 4
    assert all(path.exists() for path in summary.exported_paths)
    assert (tmp_path / "benchmark-clear-bounded-action").exists()


def test_run_benchmarks_to_exports_writes_negative_control_report(
    tmp_path: Path,
) -> None:
    summary = run_benchmarks_to_exports(
        output_dir=tmp_path,
        scenario_kind=BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION,
        include_negative_controls=True,
    )

    report_path = tmp_path / "negative_controls" / "report.json"

    assert summary.passed
    assert summary.negative_control_count == 6
    assert report_path.exists()
    assert '"artifact_kind":"negative_control_report"' in report_path.read_text(
        encoding="utf-8"
    )


def test_main_returns_success_for_clear_case(tmp_path: Path) -> None:
    exit_code = main(
        [
            "run-benchmarks",
            "--output-dir",
            str(tmp_path),
            "--scenario",
            BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION.value,
            "--include-negative-controls",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "benchmark-clear-bounded-action").exists()
    assert (tmp_path / "negative_controls" / "report.json").exists()
