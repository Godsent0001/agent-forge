from app.core.tool_outcomes import classify_tool_outcome


def test_classifies_empty_and_explicit_failure_as_no_progress():
    assert not classify_tool_outcome("").succeeded
    assert not classify_tool_outcome("ERROR: network unavailable").succeeded
    assert not classify_tool_outcome("No results found.").succeeded
    assert not classify_tool_outcome("The requested file was not found.").succeeded


def test_does_not_treat_clean_diagnostics_as_failures():
    assert classify_tool_outcome("Validation completed without errors.").succeeded
    assert classify_tool_outcome("Found 3 matching records.").succeeded


def test_outcome_policy_is_independent_of_tool_names():
    for result in ("No results found.", "ERROR: operation failed", "unavailable"):
        assert not classify_tool_outcome(result).succeeded
