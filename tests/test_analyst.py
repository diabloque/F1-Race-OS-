from copy import deepcopy
from datetime import datetime, timezone
import pytest
from raceos import analyst
from raceos.data import DataError

AT = datetime(2025, 1, 1, tzinfo=timezone.utc)


class Analysis:
    def session_at(self, sid, at):
        return {
            "year": 2025,
            "location": "Monza",
            "name": "Race",
            "drivers": [{"number": 4}],
            "end": AT,
        }, at

    def choices(self, sid, at):
        return {"drivers": [{"number": 4, "laps": []}]}

    def compare(self, sid, at, *args):
        raise DataError("Choose a timed lap completed by the replay clock.")


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def test_agent_calls_tools_and_returns_evidence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []

    def send(url, **kwargs):
        requests.append(deepcopy(kwargs["json"]))
        if len(requests) == 1:
            return Response(
                {
                    "steps": [
                        {
                            "type": "function_call",
                            "name": "completed_laps",
                            "id": "one",
                            "arguments": {},
                        }
                    ]
                }
            )
        return Response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "No laps completed yet."}],
                    }
                ]
            }
        )

    result = analyst.ask(
        None, None, Analysis(), "ti-test", AT, 4, "Which laps?", send=send
    )
    assert result["answer"] == "No laps completed yet."
    assert result["evidence"][0]["data"]["drivers"][0]["laps"] == []
    assert requests[1]["input"][-1]["type"] == "function_result"
    assert requests[0]["store"] is False


def test_agent_rejects_nonexistent_laps(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = []

    def send(url, **kwargs):
        calls.append(deepcopy(kwargs["json"]))
        if len(calls) == 1:
            return Response(
                {
                    "steps": [
                        {
                            "type": "function_call",
                            "name": "compare_laps",
                            "id": "one",
                            "arguments": {
                                "driver_a": 4,
                                "lap_a": 99,
                                "driver_b": 4,
                                "lap_b": 99,
                            },
                        }
                    ]
                }
            )
        return Response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {"type": "text", "text": "That lap is not complete."}
                        ],
                    }
                ]
            }
        )

    result = analyst.ask(
        None, None, Analysis(), "ti-test", AT, 4, "Compare future laps", send=send
    )
    assert result["evidence"] == []
    assert "completed" in calls[1]["input"][-1]["result"][0]["text"]


def test_missing_key_is_explained(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(analyst, "KEY_FILE", tmp_path / "missing")
    with pytest.raises(DataError, match="gemini-key.txt"):
        analyst.ask(None, None, Analysis(), "ti-test", AT, 4, "Hello")


def test_full_session_tools_use_end_even_when_replay_is_earlier(monkeypatch):
    from datetime import timedelta

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    end = AT + timedelta(hours=2)
    observed = []

    class FullSessionAnalysis(Analysis):
        def session_at(self, sid, at):
            session, at = super().session_at(sid, at)
            session["end"] = end
            return session, at

        def choices(self, sid, at):
            observed.append(at)
            return {"drivers": [{"number": 4, "laps": [{"lap_number": 50}]}]}

    def send(url, **kwargs):
        if not observed:
            return Response(
                {
                    "steps": [
                        {
                            "type": "function_call",
                            "name": "completed_laps",
                            "id": "one",
                            "arguments": {},
                        }
                    ]
                }
            )
        return Response(
            {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "Lap 50 was completed."}],
                    }
                ]
            }
        )

    result = analyst.ask(
        None,
        None,
        FullSessionAnalysis(),
        "ti-test",
        AT,
        4,
        "How did the race finish?",
        send=send,
    )
    assert observed == [end]
    assert result["evidence"][0]["data"]["drivers"][0]["laps"][0]["lap_number"] == 50
    assert result["scope"] == "full_session"
