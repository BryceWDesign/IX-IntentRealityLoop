import ix_intent_reality_loop as ix


def test_public_api_exposes_version() -> None:
    assert ix.__version__ == "0.1.0"


def test_public_api_exposes_core_loop_builders() -> None:
    assert ix.build_user_intent_packet is not None
    assert ix.build_focus_split_record is not None
    assert ix.build_literal_lane_result is not None
    assert ix.build_interpreted_lane_result is not None
    assert ix.build_self_surpass_lane_result is not None
    assert ix.build_lane_comparison_record is not None
    assert ix.arbitrate_fourth_eye_decision is not None
    assert ix.evaluate_permission_gate is not None
    assert ix.evaluate_safety_gate is not None
    assert ix.plan_bounded_action is not None
    assert ix.build_reality_feedback_frame is not None
    assert ix.build_outcome_delta is not None
    assert ix.build_memory_binding_decision is not None


def test_public_api_exposes_evidence_and_handoff_builders() -> None:
    assert ix.build_evidence_bundle is not None
    assert ix.build_replay_manifest is not None
    assert ix.build_blackfox_governance_handoff is not None
    assert ix.build_kernel_wave6_donor_packet is not None
    assert ix.assemble_benchmark_evidence is not None
    assert ix.export_artifact is not None


def test_public_api_exposes_benchmark_and_negative_control_suites() -> None:
    assert len(ix.benchmark_catalog()) == len(ix.BenchmarkScenarioKind)
    report = ix.run_negative_control_suite(report_id="api-negative-controls")

    assert report.passed
    assert report.passed_count == len(ix.NegativeControlKind)


def test_public_api_rejects_prohibited_claims() -> None:
    prohibited = ix.find_prohibited_claims("This is certified AGI.")

    assert prohibited == ("certified agi",)
