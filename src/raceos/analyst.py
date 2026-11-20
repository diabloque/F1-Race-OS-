"""Gemini race analyst using the current replay clock and RaceOS tools."""

import json
import os
from pathlib import Path
import requests
import truststore
from raceos.data import DataError
from raceos.engineering import environment

KEY_FILE = Path(__file__).resolve().parents[2] / "data" / "gemini-key.txt"
MODEL = os.environ.get("RACEOS_GEMINI_MODEL", "gemini-3.5-flash-lite")
TOOLS = [
    {
        "type": "function",
        "name": "completed_laps",
        "description": "List drivers and laps completed by the current replay time.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "compare_laps",
        "description": "Compare two completed laps, including sector times and input coverage.",
        "parameters": {
            "type": "object",
            "properties": {
                name: {"type": "integer"}
                for name in ("driver_a", "lap_a", "driver_b", "lap_b")
            },
            "required": ["driver_a", "lap_a", "driver_b", "lap_b"],
        },
    },
    {
        "type": "function",
        "name": "race_context",
        "description": "Get current race timing, tyres, weather and race-control messages.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def configured():
    return bool(
        os.environ.get("GEMINI_API_KEY", "").strip()
        or (KEY_FILE.is_file() and KEY_FILE.stat().st_size > 0)
    )


def api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and KEY_FILE.is_file():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise DataError("Add your Gemini API key in data/gemini-key.txt and try again.")
    return key


def ask(provider, remote, analysis, sid, at, driver, question, send=None):
    session, at = analysis.session_at(sid, at)
    if driver not in [item["number"] for item in session["drivers"]]:
        raise DataError("Choose a driver in this session.")
    key = api_key()
    history = [{"type": "user_input", "content": question}]
    system = (
        "You are a concise F1 race analyst. Use the available tools before making claims about this session. "
        "Only use observations at the selected replay clock. Do not invent causes, corner names, positions, or future results. "
        "Mention missing data and coverage. Lap deltas are B minus A. Prepared positions are approximate. "
        f"Session: {session['year']} {session['location']} {session['name']}; replay time: {at.isoformat()}; followed driver number: {driver}."
    )
    evidence = []
    truststore.inject_into_ssl()
    send = send or requests.post
    for turn in range(5):
        payload = {
            "model": MODEL,
            "store": False,
            "system_instruction": system,
            "input": history,
            "tools": TOOLS,
            "generation_config": {
                "max_output_tokens": 2048,
                "tool_choice": "any" if turn == 0 else "auto",
            },
        }
        try:
            response = send(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key},
                json=payload,
                timeout=(10, 60),
            )
            if response.status_code in (400, 401, 403):
                raise DataError(
                    "Gemini rejected the request. Check your API key and model access."
                )
            if response.status_code == 429:
                raise DataError("Gemini quota or rate limit reached. Try again later.")
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as error:
            raise DataError(
                "Could not reach Gemini. Check your connection and try again."
            ) from error
        steps = result.get("steps", [])
        if not isinstance(steps, list):
            raise DataError("Gemini returned an unexpected response.")
        history.extend(steps)
        calls = [step for step in steps if step.get("type") == "function_call"]
        if not calls:
            answers = [
                step.get("content", "")
                for step in steps
                if step.get("type") == "model_output"
            ]
            text = []
            for content in answers:
                if isinstance(content, str):
                    text.append(content)
                elif isinstance(content, list):
                    text.extend(
                        part.get("text", "")
                        for part in content
                        if part.get("type") == "text"
                    )
            answer = "\n".join(text).strip()
            if not answer:
                raise DataError("Gemini did not return an answer. Try again.")
            return {"answer": answer, "evidence": evidence, "at_utc": at.isoformat()}
        if len(calls) > 4:
            raise DataError(
                "The analyst requested too many data checks. Try a narrower question."
            )
        for call in calls:
            name = call.get("name", "")
            args = call.get("arguments") or {}
            try:
                if not isinstance(args, dict):
                    raise ValueError("Invalid tool arguments.")
                if name == "completed_laps":
                    data = analysis.choices(sid, at)
                elif name == "compare_laps":
                    keys = ("driver_a", "lap_a", "driver_b", "lap_b")
                    if any(type(args.get(k)) is not int or args[k] <= 0 for k in keys):
                        raise ValueError("Select valid driver and lap numbers.")
                    data = analysis.compare(sid, at, *(args[k] for k in keys))
                    alignment = data.pop("alignment", {})
                    data["distance_alignment"] = {
                        k: v for k, v in alignment.items() if k != "points"
                    }
                elif name == "race_context":
                    frame = remote.snapshot(sid, at, driver)
                    data = {
                        k: frame.get(k)
                        for k in (
                            "race_timing",
                            "weather",
                            "weather_status",
                            "race_control",
                            "race_control_status",
                        )
                    }
                    data["drivers"] = [
                        {
                            k: car.get(k)
                            for k in (
                                "number",
                                "code",
                                "name",
                                "tyres",
                                "current_lap_number",
                            )
                        }
                        for car in frame["drivers"]
                    ]
                else:
                    raise ValueError("Unknown tool.")
                evidence.append({"tool": name, "arguments": args, "data": data})
                output = data
            except (DataError, ValueError, KeyError) as error:
                output = {"error": str(error)}
            history.append(
                {
                    "type": "function_result",
                    "name": name,
                    "call_id": call.get("id"),
                    "result": [
                        {"type": "text", "text": json.dumps(output, default=str)}
                    ],
                }
            )
    raise DataError(
        "The analyst reached its data-check limit. Try a narrower question."
    )
