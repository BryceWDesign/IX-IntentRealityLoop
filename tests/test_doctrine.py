import pytest

from ix_intent_reality_loop.doctrine import (
    DoctrineSeverity,
    assert_no_prohibited_claims,
    doctrine_catalog,
    doctrine_index,
    find_prohibited_claims,
    missing_required_rules,
)


def test_doctrine_catalog_contains_core_wave6_boundaries() -> None:
    rule_codes = {rule.code for rule in doctrine_catalog()}

    assert "thought_not_action" in rule_codes
    assert "intent_not_permission" in rule_codes
    assert "interpretation_not_truth" in rule_codes
    assert "completion_not_output" in rule_codes
    assert "surpass_first_pass_not_user_authority" in rule_codes
    assert "reality_gets_vote" in rule_codes
    assert "evidence_before_claim" in rule_codes
    assert "human_authority_persists" in rule_codes
    assert "no_agi_overclaim" in rule_codes


def test_doctrine_index_is_read_only() -> None:
    index = doctrine_index()

    assert index["intent_not_permission"].severity is DoctrineSeverity.INVARIANT
    with pytest.raises(TypeError):
        index["new_rule"] = index["intent_not_permission"]  # type: ignore[index]


def test_missing_required_rules_detects_omitted_doctrine() -> None:
    supplied = {"thought_not_action", "intent_not_permission"}

    missing = missing_required_rules(supplied)

    assert "completion_not_output" in missing
    assert "no_agi_overclaim" in missing


def test_prohibited_claim_scanner_detects_overclaim_fragments() -> None:
    text = "This runtime is not certified AGI or production-ready autonomy."

    prohibited = find_prohibited_claims(text)

    assert prohibited == ("certified agi", "production-ready autonomy")


def test_assert_no_prohibited_claims_allows_bounded_language() -> None:
    assert_no_prohibited_claims(
        "This is a source-available evaluation runtime for governed agency loops."
    )


def test_assert_no_prohibited_claims_rejects_unsafe_claims() -> None:
    with pytest.raises(ValueError, match="certified agi"):
        assert_no_prohibited_claims("This is certified AGI.")
