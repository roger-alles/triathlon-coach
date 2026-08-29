"""Tests de l'embolcall del model del coach, amb client fals (sense API)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from coach.llm import OUTPUT_SCHEMA, CoachLLM, load_prompt

VALID_OUTPUT = {
    "schema_version": "1.0", "report_type": "daily",
    "readiness": {"verdict": "green", "drivers": [], "confidence": "medium"},
    "summary": "Dia verd.", "rationale": "TSB en recuperació.",
    "session_changes": [], "flags": [], "questions_for_athlete": [],
}


class _FakeClient:
    def __init__(self):
        self.kwargs = None
        self.messages = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(VALID_OUTPUT))],
            model=kwargs["model"], stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=9000, output_tokens=700),
        )


def test_generate_passes_schema_and_system_and_parses():
    fake = _FakeClient()
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    conversation = [{"role": "user", "content": '{"today":"x"}'}]
    output, usage = llm.generate(system="ets el coach", messages=conversation)

    assert output == VALID_OUTPUT
    assert usage == {"model": "claude-sonnet-5", "input_tokens": 9000,
                     "output_tokens": 700}
    sent = fake.kwargs
    assert sent["system"] == "ets el coach"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"] == OUTPUT_SCHEMA
    assert sent["messages"] == conversation


def test_output_schema_has_no_meta_keys():
    # les claus $schema/$id/title són per a humans; a l'API no s'envien
    assert not any(k.startswith("$") or k == "title" for k in OUTPUT_SCHEMA)


def test_load_prompt_reads_versioned_file():
    text = load_prompt("daily-v1")
    assert "entrenador" in text and "rationale" in text
