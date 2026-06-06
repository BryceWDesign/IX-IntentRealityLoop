from datetime import UTC, datetime
from pathlib import Path

import pytest

from ix_intent_reality_loop.benchmarks import (
    BenchmarkScenarioKind,
    benchmark_catalog,
)
from ix_intent_reality_loop.core import (
    BoundedScore,
    ValidationFinding,
    ValidationSeverity,
)
from ix_intent_reality_loop.export import (
    ArtifactExport,
    canonical_json,
    export_artifact,
    export_artifact_json,
    export_many_artifacts,
    sha256_hex_for_payload,
    to_primitive,
    validate_artifact_export,
    write_artifact_export,
)
from ix_intent_reality_loop.pipeline import assemble_benchmark_evidence


def _clear_assembly():
    scenario = next(
        scenario
        for scenario in benchmark_catalog()
        if scenario.kind is BenchmarkScenarioKind.CLEAR_BOUNDED_ACTION
    )
    return assemble_benchmark_evidence(
        assembly_id="assembly-clear",
        scenario=scenario,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_to_primitive_converts_dataclasses_enums_and_datetimes() -> None:
    finding = ValidationFinding(
        code="finding",
        message="Finding message.",
        severity=ValidationSeverity.WARNING,
    )

    primitive = to_primitive(
        {
            "finding": finding,
            "score": BoundedScore(0.9),
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
    )

    assert primitive["finding"]["severity"] == "warning"
    assert primitive["score"]["value"] == 0.9
    assert primitive["created_at"] == "2026-01-01T00:00:00+00:00"


def test_to_primitive_rejects_unsupported_values() -> None:
    class Unsupported:
        pass

    with pytest.raises(TypeError, match="unsupported export value type"):
        to_primitive(Unsupported())


def test_canonical_json_is_stable_for_mapping_order() -> None:
    first = canonical_json({"b": 2, "a": 1})
    second = canonical_json({"a": 1, "b": 2})

    assert first == second
    assert first == '{"a":1,"b":2}'


def test_sha256_hex_for_payload_is_stable() -> None:
    first = sha256_hex_for_payload({"b": 2, "a": 1})
    second = sha256_hex_for_payload({"a": 1, "b": 2})

    assert first == second
    assert len(first) == 64


def test_export_artifact_wraps_kernel_donor_packet_with_digest() -> None:
    assembly = _clear_assembly()

    export = export_artifact(
        artifact_id="export-kernel-donor",
        artifact_kind="kernel_wave6_donor_packet",
        artifact=assembly.kernel_donor_packet,
    )
    findings = validate_artifact_export(export)

    assert export.artifact_id == "export-kernel-donor"
    assert export.artifact_kind == "kernel_wave6_donor_packet"
    assert export.payload["packet_id"] == (
        "benchmark-clear-bounded-action-kernel-donor"
    )
    assert len(export.digest_hex) == 64
    assert not findings


def test_export_artifact_json_is_canonical() -> None:
    assembly = _clear_assembly()

    exported_json = export_artifact_json(
        artifact_id="export-manifest",
        artifact_kind="replay_manifest",
        artifact=assembly.replay_manifest,
    )

    assert '"artifact_id":"export-manifest"' in exported_json
    assert '"artifact_kind":"replay_manifest"' in exported_json
    assert exported_json == canonical_json(
        export_artifact(
            artifact_id="export-manifest",
            artifact_kind="replay_manifest",
            artifact=assembly.replay_manifest,
        ).__dict__
    )


def test_write_artifact_export_creates_parent_directory(tmp_path: Path) -> None:
    assembly = _clear_assembly()
    export = export_artifact(
        artifact_id="export-bundle",
        artifact_kind="evidence_bundle",
        artifact=assembly.evidence_bundle,
    )
    output_path = tmp_path / "evidence" / "bundle.json"

    written_path = write_artifact_export(export=export, output_path=output_path)

    assert written_path == output_path
    assert output_path.read_text(encoding="utf-8").endswith("\n")
    assert '"artifact_kind":"evidence_bundle"' in output_path.read_text(
        encoding="utf-8"
    )


def test_validate_artifact_export_blocks_digest_mismatch() -> None:
    export = ArtifactExport(
        artifact_id="export-invalid",
        artifact_kind="evidence_bundle",
        payload={"valid": "payload"},
        digest_hex="a" * 64,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_artifact_export(export)
    finding_codes = {finding.code for finding in findings}

    assert "artifact_export_digest_mismatch" in finding_codes


def test_validate_artifact_export_blocks_agi_kind_overclaim() -> None:
    export = ArtifactExport(
        artifact_id="export-invalid-agi",
        artifact_kind="agi_proof",
        payload={"valid": "payload"},
        digest_hex=sha256_hex_for_payload({"valid": "payload"}),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    findings = validate_artifact_export(export)
    finding_codes = {finding.code for finding in findings}

    assert "artifact_export_kind_overclaims_agi" in finding_codes


def test_export_many_artifacts_preserves_input_order() -> None:
    assembly = _clear_assembly()

    exports = export_many_artifacts(
        (
            ("export-bundle", "evidence_bundle", assembly.evidence_bundle),
            ("export-manifest", "replay_manifest", assembly.replay_manifest),
            (
                "export-kernel-donor",
                "kernel_wave6_donor_packet",
                assembly.kernel_donor_packet,
            ),
        )
    )

    assert tuple(export.artifact_id for export in exports) == (
        "export-bundle",
        "export-manifest",
        "export-kernel-donor",
    )
