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
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 8000

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

    def generate(self, system: str, messages: list[dict]) -> tuple[dict, dict]:
        """(informe parsejat, ús) — una crida amb sortida estructurada.

        messages és la conversa sencera: el bucle de correcció hi va afegint
        la resposta rebutjada i les infraccions del validador.
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            output_config={"format": {"type": "json_schema",
                                      "schema": OUTPUT_SCHEMA}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        usage = {"model": response.model,
                 "input_tokens": response.usage.input_tokens,
                 "output_tokens": response.usage.output_tokens}
        return json.loads(text), usage
