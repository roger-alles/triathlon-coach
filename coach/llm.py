"""Crida al model del coach, darrere d'una interfície pròpia.

Mateix patró que ActivityProvider amb Garmin (spec §2): si un dia canviem
d'API, de model o de via (claude -p headless), es toca aquest mòdul i prou.

La sortida estructurada es força amb output_config.format + JSON Schema
(contracts/coach-output.schema.json): l'API garanteix que la resposta és
JSON vàlid contra l'esquema — la validació de FONS (regles §8, contracte
de sessions §6) la fa igualment el bucle, que no es refia de ningú.

Model per defecte: claude-sonnet-5 (~1,6 $/mes al volum d'aquest sistema).
Es canvia amb COACH_MODEL al .env, i cada crida queda registrada amb el
model usat a coach_report.model.
"""

import json
import os
import re
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_MODEL = "claude-sonnet-5"
# els thinking tokens (adaptatius, activats per defecte) comparteixen aquest
# pressupost amb la resposta: curt de tokens = JSON tallat a mitges. El
# setmanal del 06/09 en va gastar 14.9k amb un sostre de 16k; per sobre de 16k
# l'SDK exigeix streaming (no costa res si no s'usa).
# 14/09: amb 64k, un setmanal es va quedar en bucle escrivint "\\n" dins d'un
# string JSON fins al sostre (0,64 € l'intent); una setmana sencera són ~10k.
MAX_TOKENS = {"daily": 16000, "weekly": 32000, "macro": 32000, "replan": 32000}
STREAM_ABOVE = 16000


class OutputCutOff(RuntimeError):
    """El model s'ha quedat sense tokens: el JSON no és de fiar, però el bucle
    pot demanar-li una resposta més compacta en lloc de morir."""

# claus de documentació ($schema, title...) fora: a l'API només hi va l'esquema
OUTPUT_SCHEMA = {
    k: v for k, v in json.loads(
        (ROOT / "contracts" / "coach-output.schema.json").read_text()).items()
    if not k.startswith("$") and k != "title"
}


def load_prompt(name: str) -> str:
    """Prompts versionats en fitxers (spec §11): el diff d'un prompt es veu."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


class CoachLLM:
    def __init__(self, client=None, model: str | None = None):
        self.model = model or os.getenv("COACH_MODEL", DEFAULT_MODEL)
        self.client = client or anthropic.Anthropic()

    def generate(self, system: str, messages: list[dict],
                 report_type: str = "daily") -> tuple[dict, dict]:
        """(informe parsejat, ús) — una crida amb sortida estructurada.

        messages és la conversa sencera: el bucle de correcció hi va afegint
        la resposta rebutjada i les infraccions del validador. El primer
        missatge (el context, ~10k tokens) es marca per a la cache: els intents
        2 i 3 el rellegeixen a una desena part del preu.
        """
        max_tokens = MAX_TOKENS.get(report_type, MAX_TOKENS["daily"])
        request = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=_with_cached_context(messages),
            output_config={"format": {"type": "json_schema",
                                      "schema": OUTPUT_SCHEMA},
                           # esforç del raonament adaptatiu. MAI "medium" amb
                           # sortida estructurada: sonda del 14/09 — text
                           # corromput i new_session omès. "high" és el que
                           # sempre ha funcionat.
                           "effort": os.getenv("COACH_EFFORT", "high")},
        )
        if max_tokens > STREAM_ABOVE:
            with self.client.messages.stream(**request) as stream:
                response = stream.get_final_message()
        else:
            response = self.client.messages.create(**request)
        if response.stop_reason == "max_tokens":
            text = "".join(b.text for b in response.content if b.type == "text")
            head, tail = text[:300].replace("\n", " "), text[-200:].replace("\n", " ")
            raise OutputCutOff(
                f"resposta tallada per longitud (sostre {max_tokens}; "
                f"{response.usage.output_tokens} tokens generats, {len(text)} caràcters de "
                f"JSON — la resta és raonament invisible). Cap: {head!r} … Cua: {tail!r}")
        if response.stop_reason != "end_turn":
            raise RuntimeError(
                f"resposta incompleta del model (stop_reason="
                f"{response.stop_reason}): no es pot confiar en el JSON")
        text = next(b.text for b in response.content if b.type == "text")
        usage = {"model": response.model,
                 "input_tokens": response.usage.input_tokens,
                 "output_tokens": response.usage.output_tokens}
        return unescape_unicode(json.loads(text)), usage


# Des del 04/10 (OpenRouter, respostes llargues per streaming) el model escriu
# de vegades els accents com a escapes dins del text JSON ("recuperaci\\u00f3"):
# un cop parsejat queda la seqüència literal \u00f3 en lloc de "ó", i arribava
# així a l'app (títols de sessions, blocs, informes). Es decodifica aquí, que
# és per on passa tota resposta del model. scripts/fix_unicode_escapes.py
# repara el que ja s'havia desat.
_ESCAPED = re.compile(r"\\u([0-9a-fA-F]{4})")


def unescape_unicode(value):
    """Converteix les seqüències literals \\uXXXX de tots els textos (recursiu).
    Els parells subrogats (emojis, \\ud83d\\udeb4) es tornen a unir."""
    if isinstance(value, str):
        if "\\u" not in value:
            return value
        out = _ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), value)
        return out.encode("utf-16", "surrogatepass").decode("utf-16")
    if isinstance(value, list):
        return [unescape_unicode(v) for v in value]
    if isinstance(value, dict):
        return {k: unescape_unicode(v) for k, v in value.items()}
    return value


def _with_cached_context(messages: list[dict]) -> list[dict]:
    first = messages[0]
    if not isinstance(first.get("content"), str):
        return messages
    cached = {"role": first["role"],
              "content": [{"type": "text", "text": first["content"],
                           "cache_control": {"type": "ephemeral"}}]}
    return [cached] + messages[1:]
