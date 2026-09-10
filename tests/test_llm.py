"""Tests de l'embolcall del model del coach, amb client fals (sense API)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from coach.llm import MAX_TOKENS, OUTPUT_SCHEMA, CoachLLM, OutputCutOff, load_prompt

VALID_OUTPUT = {
    "schema_version": "1.0", "report_type": "daily",
    "readiness": {"verdict": "green", "drivers": [], "confidence": "medium"},
    "summary": "Dia verd.", "rationale": "TSB en recuperació.",
    "session_changes": [], "flags": [], "questions_for_athlete": [],
}


def _response(kwargs, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(VALID_OUTPUT))],
        model=kwargs["model"], stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=9000, output_tokens=700),
    )


class _FakeClient:
    def __init__(self, stop_reason="end_turn"):
        self.kwargs = None
        self.via = None
        self.stop_reason = stop_reason
        self.messages = self

    def create(self, **kwargs):
        self.kwargs, self.via = kwargs, "create"
        return _response(kwargs, self.stop_reason)

    def stream(self, **kwargs):
        self.kwargs, self.via = kwargs, "stream"
        client = self
        class _Stream:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
            def get_final_message(self_inner):
                return _response(kwargs, client.stop_reason)
        return _Stream()


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
    assert sent["messages"][0]["role"] == "user"
    # el context es marca per a la cache: els intents 2 i 3 rellegeixen el prefix
    first = sent["messages"][0]["content"][0]
    assert first["text"] == '{"today":"x"}'
    assert first["cache_control"] == {"type": "ephemeral"}
    assert sent["max_tokens"] == MAX_TOKENS["daily"] == 16000
    assert fake.via == "create"


def test_weekly_gets_a_bigger_budget_through_streaming():
    # 06/09: el setmanal va gastar 14.9k tokens de sortida amb 16k de sostre.
    fake = _FakeClient()
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    llm.generate(system="s", messages=[{"role": "user", "content": "{}"}],
                 report_type="weekly")
    assert fake.kwargs["max_tokens"] == MAX_TOKENS["weekly"] == 64000
    assert fake.via == "stream"


def test_cut_off_output_is_a_specific_error_the_loop_can_feed_back():
    fake = _FakeClient(stop_reason="max_tokens")
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    with pytest.raises(OutputCutOff):
        llm.generate(system="s", messages=[{"role": "user", "content": "{}"}])


def test_other_incomplete_stops_still_raise():
    fake = _FakeClient(stop_reason="refusal")
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    with pytest.raises(RuntimeError):
        llm.generate(system="s", messages=[{"role": "user", "content": "{}"}])


def test_follow_up_messages_are_not_marked_for_cache():
    fake = _FakeClient()
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    llm.generate(system="s", messages=[
        {"role": "user", "content": "{}"},
        {"role": "assistant", "content": "{...}"},
        {"role": "user", "content": "corregeix"}])
    sent = fake.kwargs["messages"]
    assert sent[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent[1] == {"role": "assistant", "content": "{...}"}
    assert sent[2] == {"role": "user", "content": "corregeix"}


def test_output_schema_has_no_meta_keys():
    # les claus $schema/$id/title són per a humans; a l'API no s'envien
    assert not any(k.startswith("$") or k == "title" for k in OUTPUT_SCHEMA)


def test_load_prompt_reads_versioned_file():
    text = load_prompt("daily-v1")
    assert "entrenador" in text and "rationale" in text
