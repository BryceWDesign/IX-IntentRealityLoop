"""End-to-end evidence assembly pipeline.

The pipeline assembles benchmark runtime artifacts into replay logs, memory
ledgers, evidence bundles, digest manifests, BlackFox handoffs, and Kernel Wave 6
donor packets. It exists so the repo can prove the whole agency loop is wired
together rather than only exposing isolated data models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ix_intent_reality_loop.benchmarks import (
    BenchmarkRunResult,
    BenchmarkScenario,
    run_benchmark_scenario,
)
from ix_intent_reality_loop.blackfox_handoff import (
    BlackFoxGovernanceHandoff,
    build_blackfox_governance_handoff,
)
from ix_intent_reality_loop.core import (
    EvidenceStatus,
    ValidationFinding,
    ValidationSeverity,
    blocker_finding,
    require_aware_utc,
    require_non_empty_text,
    utc_now,
)
from ix_intent_reality_loop.evidence import EvidenceBundle, build_evidence_bundle
from ix_intent_reality_loop.kernel_handoff import (
    KernelWave6DonorPacket,
    build_kernel_wave6_donor_packet,
)
from ix_intent_reality_loop.manifest import ReplayManifest, build_replay_manifest
from ix_intent_reality_loop.memory_ledger import (
    MemoryLedger,
    apply_memory_binding_decision,
)
from ix_intent_reality_loop.replay import (
    ReplayEvent,
    ReplayEventLog,
    ReplayEventType,
    build_replay_event,
    validate_replay_event_log,
)


@dataclass(frozen=True, slots=True)
class IntentRealityLoopAssembly:
    """Complete assembled evidence packet for one agency-loop run."""

    assembly_id: str
    run_result: BenchmarkRunResult
    replay_log: ReplayEventLog
    memory_ledger: MemoryLedger
    evidence_bundle: EvidenceBundle
    replay_manifest: ReplayManifest
    blackfox_handoff: BlackFoxGovernanceHandoff
    kernel_donor_packet: KernelWave6DonorPacket
    findings: tuple[ValidationFinding, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assembly_id",
            require_non_empty_text(self.assembly_id, "assembly_id"),
        )
        object.__setattr__(
            self,
            "created_at",
            require_aware_utc(self.created_at, "created_at"),
        )

    @property
    def blocker_count(self) -> int:
        """Return blocker count across assembly-level findings."""

        return sum(
            1
            for finding in self.findings
            if finding.severity is ValidationSeverity.BLOCKER
        )

    @property
    def warning_count(self) -> int:
        """Return warning count across assembly-level findings."""

        return sum(
            1
            for finding in self.findings
            if finding.severity is ValidationSeverity.WARNING
        )

    @property
    def is_kernel_review_ready(self) -> bool:
        """Return whether the assembly can be reviewed as Kernel donor evidence."""

        return self.blocker_count == 0 and self.kernel_donor_packet.is_review_ready


def assemble_benchmark_evidence(
    *,
    assembly_id: str,
    scenario: BenchmarkScenario,
    checked_at: datetime | None = None,
) -> IntentRealityLoopAssembly:
    """Run one benchmark scenario and assemble all downstream evidence artifacts."""

    check_time = utc_now() if checked_at is None else require_aware_utc(
        checked_at,
        "checked_at",
    )
    run_result = run_benchmark_scenario(
        run_id=f"{scenario.scenario_id}-run",
        scenario=scenario,
        checked_at=check_time,
    )
    replay_log = build_replay_log_from_run_result(
        log_id=f"{scenario.scenario_id}-replay",
        run_result=run_result,
    )
    memory_ledger = apply_memory_binding_decision(
        ledger=MemoryLedger(ledger_id=f"{scenario.scenario_id}-ledger"),
        entry_id=f"{scenario.scenario_id}-ledger-entry",
        decision=run_result.memory_decision,
    )
    evidence_bundle = build_evidence_bundle(
        bundle_id=f"{scenario.scenario_id}-bundle",
        replay_log=replay_log,
        memory_ledger=memory_ledger,
        narrative_summary=(
            "Bounded IX-IntentRealityLoop evidence assembly. "
            "This artifact does not claim AGI, certification, or deployment."
        ),
    )
    replay_manifest = build_replay_manifest(
        manifest_id=f"{scenario.scenario_id}-manifest",
        bundle=evidence_bundle,
    )
    blackfox_handoff = build_blackfox_governance_handoff(
        handoff_id=f"{scenario.scenario_id}-blackfox-handoff",
        bundle=evidence_bundle,
        manifest=replay_manifest,
    )
    kernel_donor_packet = build_kernel_wave6_donor_packet(
        packet_id=f"{scenario.scenario_id}-kernel-donor",
        bundle=evidence_bundle,
        manifest=replay_manifest,
        handoff=blackfox_handoff,
    )
    findings = validate_assembly_links(
        run_result=run_result,
        replay_log=replay_log,
        memory_ledger=memory_ledger,
        evidence_bundle=evidence_bundle,
        replay_manifest=replay_manifest,
        blackfox_handoff=blackfox_handoff,
        kernel_donor_packet=kernel_donor_packet,
    )

    return IntentRealityLoopAssembly(
        assembly_id=assembly_id,
        run_result=run_result,
        replay_log=replay_log,
        memory_ledger=memory_ledger,
        evidence_bundle=evidence_bundle,
        replay_manifest=replay_manifest,
        blackfox_handoff=blackfox_handoff,
        kernel_donor_packet=kernel_donor_packet,
        findings=findings,
        created_at=check_time,
    )


def build_replay_log_from_run_result(
    *,
    log_id: str,
    run_result: BenchmarkRunResult,
) -> ReplayEventLog:
    """Build an ordered replay log from benchmark run artifacts."""

    events = (
        _event(
            event_id=f"{run_result.scenario_id}-event-001-intent",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.INTENT_PACKET,
            subject_id=run_result.intent_packet.intent_id,
            summary="Intent packet captured before permission or action.",
            payload={"confidence": str(run_result.intent_packet.confidence.value)},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-002-focus",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.FOCUS_SPLIT,
            subject_id=run_result.focus_record.record_id,
            summary="Focus split record captured attended and omitted requirements.",
            payload={"risk": run_result.focus_record.risk.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-003-literal",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.LITERAL_LANE,
            subject_id=run_result.literal_lane.lane_id,
            summary="Literal execution lane preserved request-as-written.",
            payload={"status": run_result.literal_lane.status.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-004-interpreted",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.INTERPRETED_LANE,
            subject_id=run_result.interpreted_lane.lane_id,
            summary="Interpreted execution lane preserved inferred goal.",
            payload={"status": run_result.interpreted_lane.status.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-005-self-surpass",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.SELF_SURPASS_LANE,
            subject_id=run_result.self_surpass_lane.lane_id,
            summary="Self-surpass lane attempted bounded first-pass improvement.",
            payload={"status": run_result.self_surpass_lane.status.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-006-comparison",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.LANE_COMPARISON,
            subject_id=run_result.comparison.comparison_id,
            summary="Lane comparison recorded viable, blocked, and divergent lanes.",
            payload={"alignment": str(run_result.comparison.alignment_score.value)},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-007-arbiter",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.FOURTH_EYE_DECISION,
            subject_id=run_result.fourth_eye_decision.decision_id,
            summary="Fourth-eye arbiter selected, clamped, deferred, or safe-held.",
            payload={"disposition": run_result.fourth_eye_decision.disposition.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-008-permission",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.PERMISSION_GATE,
            subject_id=run_result.permission_result.gate_id,
            summary="Permission gate separated intent from scoped consent.",
            payload={"disposition": run_result.permission_result.disposition.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-009-safety",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.SAFETY_GATE,
            subject_id=run_result.safety_result.gate_id,
            summary="Safety gate evaluated risk state before bounded action.",
            payload={"interaction_state": run_result.safety_result.interaction_state.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-010-action",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.BOUNDED_ACTION,
            subject_id=run_result.action_decision.action_id,
            summary="Bounded action decision remained non-actuating.",
            payload={"mode": run_result.action_decision.mode.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-011-feedback",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.REALITY_FEEDBACK,
            subject_id=run_result.feedback_frame.frame_id,
            summary="Reality feedback frame compared observation against prediction.",
            payload={"outcome": run_result.feedback_frame.outcome.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-012-delta",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.OUTCOME_DELTA,
            subject_id=run_result.outcome_delta.delta_id,
            summary="Outcome delta scored prediction-versus-observation mismatch.",
            payload={"status": run_result.outcome_delta.status.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-013-memory-binding",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.MEMORY_BINDING,
            subject_id=run_result.memory_decision.memory_decision_id,
            summary="Memory binding decided update, downgrade, quarantine, or reject.",
            payload={"action": run_result.memory_decision.action.value},
        ),
        _event(
            event_id=f"{run_result.scenario_id}-event-014-memory-ledger",
            intent_id=run_result.intent_packet.intent_id,
            event_type=ReplayEventType.MEMORY_LEDGER,
            subject_id=f"{run_result.scenario_id}-ledger",
            summary="Memory ledger snapshot is expected after binding decision.",
            payload={"snapshot": "pending-ledger-assembly"},
        ),
    )

    return ReplayEventLog(
        log_id=log_id,
        intent_id=run_result.intent_packet.intent_id,
        events=events,
    )


def validate_assembly_links(
    *,
    run_result: BenchmarkRunResult,
    replay_log: ReplayEventLog,
    memory_ledger: MemoryLedger,
    evidence_bundle: EvidenceBundle,
    replay_manifest: ReplayManifest,
    blackfox_handoff: BlackFoxGovernanceHandoff,
    kernel_donor_packet: KernelWave6DonorPacket,
) -> tuple[ValidationFinding, ...]:
    """Validate cross-artifact links in an assembled evidence packet."""

    findings: list[ValidationFinding] = []
    findings.extend(validate_replay_event_log(replay_log))

    if replay_log.intent_id != run_result.intent_packet.intent_id:
        findings.append(
            blocker_finding(
                "assembly_replay_intent_mismatch",
                "Replay log intent_id must match run result intent_id.",
            )
        )

    if not memory_ledger.entries:
        findings.append(
            blocker_finding(
                "assembly_memory_ledger_empty",
                "Assembly memory ledger must contain a binding entry.",
            )
        )

    if evidence_bundle.replay_log_id != replay_log.log_id:
        findings.append(
            blocker_finding(
                "assembly_bundle_replay_log_mismatch",
                "Evidence bundle replay_log_id must match replay log.",
            )
        )

    if evidence_bundle.memory_ledger_id != memory_ledger.ledger_id:
        findings.append(
            blocker_finding(
                "assembly_bundle_memory_ledger_mismatch",
                "Evidence bundle memory_ledger_id must match memory ledger.",
            )
        )

    if replay_manifest.bundle_id != evidence_bundle.bundle_id:
        findings.append(
            blocker_finding(
                "assembly_manifest_bundle_mismatch",
                "Replay manifest must bind the evidence bundle.",
            )
        )

    if blackfox_handoff.bundle_id != evidence_bundle.bundle_id:
        findings.append(
            blocker_finding(
                "assembly_blackfox_bundle_mismatch",
                "BlackFox handoff must reference the evidence bundle.",
            )
        )

    if kernel_donor_packet.bundle_id != evidence_bundle.bundle_id:
        findings.append(
            blocker_finding(
                "assembly_kernel_bundle_mismatch",
                "Kernel donor packet must reference the evidence bundle.",
            )
        )

    return tuple(findings)


def _event(
    *,
    event_id: str,
    intent_id: str,
    event_type: ReplayEventType,
    subject_id: str,
    summary: str,
    payload: dict[str, str],
) -> ReplayEvent:
    """Build one replay event for pipeline assembly."""

    return build_replay_event(
        event_id=event_id,
        intent_id=intent_id,
        event_type=event_type,
        subject_id=subject_id,
        summary=summary,
        payload=payload,
    )
