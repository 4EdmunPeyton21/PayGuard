import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent.fallback_loop import investigate_fallback
from app.schemas.case import NormalisedCase


def _fake_tool_call_response(tool_name: str, args: dict):
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name=tool_name, arguments=json.dumps(args)),
    )
    message = SimpleNamespace(content="", tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_on_event_emits_tool_start_then_tool_result():
    """D19: on_event must fire tool_start before tool_result, live per tool call."""
    case = NormalisedCase(
        case_id="c_test_stream",
        input_types=["text"],
        text="Your account is blocked today, verify now.",
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _fake_tool_call_response(
        "signal_scan", {"text": case.text}
    )

    events = []

    with patch("app.agent.fallback_loop.OpenAI", return_value=mock_client):
        result = investigate_fallback(
            case,
            max_tool_calls=1,
            on_event=lambda etype, payload: events.append((etype, payload)),
        )

    assert result.tool_calls == 1
    assert [e[0] for e in events] == ["tool_start", "tool_result"]
    assert events[0][1]["tool"] == "signal_scan"
    assert events[1][1]["tool"] == "signal_scan"
    assert events[1][1]["result_type"] == "ok"
