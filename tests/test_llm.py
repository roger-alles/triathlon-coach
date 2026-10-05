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


def _response(kwargs, stop_reason="end_turn", text=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text or json.dumps(VALID_OUTPUT))],
        model=kwargs["model"], stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=9000, output_tokens=700),
    )


class _FakeClient:
    def __init__(self, stop_reason="end_turn", text=None):
        self.text = text
        self.kwargs = None
        self.via = None
        self.stop_reason = stop_reason
        self.messages = self

    def create(self, **kwargs):
        self.kwargs, self.via = kwargs, "create"
        return _response(kwargs, self.stop_reason, self.text)

    def stream(self, **kwargs):
        self.kwargs, self.via = kwargs, "stream"
        client = self
        class _Stream:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
            def get_final_message(self_inner):
                return _response(kwargs, client.stop_reason, client.text)
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
    # el raonament adaptatiu comparteix el sostre de tokens: esforç acotat
    assert sent["output_config"]["effort"] == "high"


def test_weekly_gets_a_bigger_budget_through_streaming():
    # 06/09: el setmanal va gastar 14.9k tokens de sortida amb 16k de sostre.
    fake = _FakeClient()
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    llm.generate(system="s", messages=[{"role": "user", "content": "{}"}],
                 report_type="weekly")
    assert fake.kwargs["max_tokens"] == MAX_TOKENS["weekly"] == 32000
    assert fake.via == "stream"


def test_cut_off_output_is_a_specific_error_the_loop_can_feed_back():
    fake = _FakeClient(stop_reason="max_tokens")
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    with pytest.raises(OutputCutOff) as e:
        llm.generate(system="s", messages=[{"role": "user", "content": "{}"}])
    # el missatge diu què s'ha gastat: tokens generats i caràcters de JSON vs raonament
    msg = str(e.value)
    assert "700 tokens generats" in msg and "caràcters de JSON" in msg
    assert '"schema_version"' in msg   # el cap del text tallat, per diagnosticar


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


def test_output_schema_v12_allows_add_without_plan_session_id():
    # S4a: el coach pot crear sessions (add) dins d'un bloc existent. Un add
    # no té sessió d'origen, així que plan_session_id és opcional al schema
    # (el codi l'exigeix per a la resta d'accions) i new_session porta la data.
    from coach.llm import OUTPUT_SCHEMA
    item = OUTPUT_SCHEMA["properties"]["session_changes"]["items"]
    assert "add" in item["properties"]["action"]["enum"]
    # v1.4: obligatoris però nullables (null explícit als keep/move/cancel):
    # amb camps opcionals el model ometia new_session als add
    assert set(item["required"]) == {"plan_session_id", "action", "new_session", "new_date", "reason"}
    assert item["properties"]["plan_session_id"]["type"] == ["integer", "null"]
    ns = item["properties"]["new_session"]["anyOf"][0]
    assert "local_date" in ns["required"] and "priority" in ns["required"]
    props = ns["properties"]
    assert props["local_date"]["type"] == ["string", "null"]
    assert set(props["parent_of_day"]["anyOf"][0]["enum"]) == {"swim", "bike", "run"}
    assert "macro" in OUTPUT_SCHEMA["properties"]["report_type"]["enum"]


def test_output_schema_v13_has_block_changes_for_the_macro():
    # S3: el macro proposa blocs (fase, dates, hores), mai sessions.
    from coach.llm import MAX_TOKENS, OUTPUT_SCHEMA
    assert "block_changes" not in OUTPUT_SCHEMA["required"]
    bc = OUTPUT_SCHEMA["properties"]["block_changes"]["items"]
    assert set(bc["properties"]["action"]["enum"]) == {"add", "modify", "cancel"}
    assert set(bc["required"]) == {"action", "block_id", "new_block", "reason"}
    nb = bc["properties"]["new_block"]["anyOf"][0]["properties"]
    assert {"phase", "name", "start_date", "end_date", "intent", "target_weekly_hours", "fallback"} <= set(nb)
    assert set(nb["phase"]["enum"]) == {"base", "build", "peak", "taper", "race", "recovery", "transition"}
    assert MAX_TOKENS["macro"] == 32000   # 14/09: acota el cost d'un bucle (abans 64k)


def test_effort_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("COACH_EFFORT", "xhigh")
    fake = _FakeClient()
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    llm.generate(system="s", messages=[{"role": "user", "content": "{}"}])
    assert fake.kwargs["output_config"]["effort"] == "xhigh"


def test_accents_written_as_escapes_by_the_model_arrive_as_real_letters():
    # 04/10, macro i setmanal per OpenRouter: "recuperaci\\u00f3" dins del JSON
    escaped = dict(VALID_OUTPUT, summary="Setmana de recuperaci\\u00f3 \\u00b7 tot suau",
                   flags=["el genoll va b\\u00e9 \\ud83d\\udeb4"])
    fake = _FakeClient(text=json.dumps(escaped))
    llm = CoachLLM(client=fake, model="claude-sonnet-5")
    output, _ = llm.generate(system="s", messages=[{"role": "user", "content": "{}"}],
                             report_type="weekly")
    assert output["summary"] == "Setmana de recuperació · tot suau"
    assert output["flags"] == ["el genoll va bé 🚴"]
    # un text normal no canvia
    assert output["rationale"] == VALID_OUTPUT["rationale"]
