from app.core.runner import _find_recovered_tool_error


def test_recovery_signal_requires_error_then_successful_tool_result():
    assert _find_recovered_tool_error([
        {"role": "tool", "content": "ERROR: missing parameter"},
        {"role": "tool", "content": "completed successfully"},
    ]) == ("missing parameter", "completed successfully")

    assert _find_recovered_tool_error([
        {"role": "tool", "content": "ERROR: missing parameter"},
        {"role": "tool", "content": "ERROR: still failing"},
    ]) is None
