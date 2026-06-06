"""Canonical JSON export helpers.

Exports are review artifacts, not proof of AGI or completion. This module turns
runtime records, evidence bundles, manifests, governance handoffs, Kernel donor
packets, and full assemblies into deterministic JSON payloads with stable
SHA-256 digests.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ix_intent_reality_loop.core import (
    ValidationFinding,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
)


@dataclass(frozen=True, slots=True)
class ArtifactExport:
    """Canonical export wrapper for one review artifact."""

    artifact_id: str
    artifact_kind: str
    payload: Mapping[str, Any]
    digest_hex: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            require_non_empty_text(self.artifact_id, "artifact_id"),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            require_non_empty_text(self.artifact_kind, "artifact_kind"),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

        if len(self.digest_hex) != 64:
            raise ValueError("digest_hex must be 64 hexadecimal characters")
        try:
            int(self.digest_hex, 16)
        except ValueError as exc:
            raise ValueError("digest_hex must be hexadecimal") from exc

    @property
    def canonical_json(self) -> str:
        """Return canonical JSON for the exported artifact wrapper."""

        return canonical_json(
            {
                "artifact_id": self.artifact_id,
                "artifact_kind": self.artifact_kind,
                "payload": self.payload,
                "digest_hex": self.digest_hex,
                "created_at": self.created_at.isoformat(),
            }
        )


def to_primitive(value: Any) -> Any:
    """Convert supported runtime values into JSON-compatible primitives."""

    if is_dataclass(value) and not isinstance(value, type):
        return {str(key): to_primitive(item) for key, item in asdict(value).items()}

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime | date):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            str(key): to_primitive(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }

    if isinstance(value, tuple | list):
        return [to_primitive(item) for item in value]

    if isinstance(value, set | frozenset):
        return sorted(to_primitive(item) for item in value)

    if isinstance(value, str | int | float | bool) or value is None:
        return value

    raise TypeError(f"unsupported export value type: {type(value).__name__}")


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Return deterministic canonical JSON for a mapping payload."""

    primitive_payload = to_primitive(payload)
    if not isinstance(primitive_payload, dict):
        raise TypeError("canonical_json payload must encode to a dictionary")

    return json.dumps(
        primitive_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def sha256_hex_for_payload(payload: Mapping[str, Any]) -> str:
    """Return SHA-256 digest for a canonical JSON mapping payload."""

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def export_artifact(
    *,
    artifact_id: str,
    artifact_kind: str,
    artifact: Any,
) -> ArtifactExport:
    """Build a canonical export wrapper for a runtime artifact."""

    payload = to_primitive(artifact)
    if not isinstance(payload, dict):
        raise TypeError("exported artifact must encode to a dictionary")

    return ArtifactExport(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        payload=payload,
        digest_hex=sha256_hex_for_payload(payload),
    )


def export_artifact_json(
    *,
    artifact_id: str,
    artifact_kind: str,
    artifact: Any,
) -> str:
    """Return canonical JSON for an exported runtime artifact."""

    return export_artifact(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        artifact=artifact,
    ).canonical_json


def write_artifact_export(
    *,
    export: ArtifactExport,
    output_path: Path,
) -> Path:
    """Write an artifact export to disk and return the path.

    The caller chooses the path. Parent directories are created because exported
    evidence is often placed under artifacts, replay, or evidence folders.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{export.canonical_json}\n", encoding="utf-8")
    return output_path


def validate_artifact_export(export: ArtifactExport) -> tuple[ValidationFinding, ...]:
    """Validate exported artifact wrapper before sharing or handoff."""

    findings: list[ValidationFinding] = []

    if not export.payload:
        findings.append(
            blocker_finding(
                "artifact_export_empty_payload",
                "Artifact export payload must not be empty.",
            )
        )

    recalculated_digest = sha256_hex_for_payload(export.payload)
    if recalculated_digest != export.digest_hex:
        findings.append(
            blocker_finding(
                "artifact_export_digest_mismatch",
                "Artifact export digest does not match canonical payload.",
            )
        )

    if "agi" in export.artifact_kind.lower() and "donor" not in (
        export.artifact_kind.lower()
    ):
        findings.append(
            blocker_finding(
                "artifact_export_kind_overclaims_agi",
                "Artifact export kind must not imply AGI status.",
            )
        )

    return tuple(findings)


def export_many_artifacts(
    artifacts: Sequence[tuple[str, str, Any]],
) -> tuple[ArtifactExport, ...]:
    """Export multiple artifacts in deterministic input order."""

    return tuple(
        export_artifact(
            artifact_id=artifact_id,
            artifact_kind=artifact_kind,
            artifact=artifact,
        )
        for artifact_id, artifact_kind, artifact in artifacts
    )
