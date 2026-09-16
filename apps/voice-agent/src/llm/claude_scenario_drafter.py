"""Adaptador de redacción de borradores de escenario — ver ADR-0014.

Implementa `ScenarioDraftingPort` (`core/ports.py`). Mismo cliente/patrón de reintentos que
`llm/claude.py::ClaudeDispatcher` y `llm/metrics_judge.py::ClaudeMetricsJudge` — reusa la misma
dependencia (`anthropic.Anthropic`), no una nueva.
"""

import json
import time

from anthropic import (
    Anthropic,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
)

from core.ports import (
    CriticalDataPoint,
    IncidentOutcome,
    ScenarioDraftContent,
    ScenarioDraftingError,
    ScenarioDraftingPort,
)

RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    OverloadedError,
)

_VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}

_SYSTEM_PROMPT = """You are helping a training-scenario author turn a real incident's post-mortem \
notes into a draft training scenario for a police-dispatch call simulator. You are NOT approving \
anything — a human reviewer will edit and approve or reject your draft before it is ever used in \
training.

You will receive the post-mortem notes of a real incident. Propose a training scenario based on \
those notes.

Rules:
- Only mark something as a confirmed fact if it is actually stated in the notes. Anything you add \
to make the scenario playable (additional dialogue, a plausible detail) is fictional training \
material, not a record of what really happened — never present it as verified fact.
- Never invent real police protocol, legal procedure, or a specific vehicle identifier (VIN or \
license plate) that was not in the notes.
- If the notes do not mention something a scenario normally needs (e.g. no location, no vehicle \
description), add a short description of that gap to "missing_information" instead of inventing a \
value for it.
- `critical_data_points` are the pieces of information a trainee must report during the call — \
each needs a short snake_case `key`, a human-readable `label`, and 2-5 `match_hints` (real \
phrases a trainee might actually say, not just the label reworded).

Respond with ONLY valid JSON, no other text, in exactly this shape:
{
  "title": "<short scenario title>",
  "category": "<incident category>",
  "difficulty": "Easy" | "Medium" | "Hard",
  "language": "English" | "Spanish",
  "description": "<one-sentence summary for the scenario library>",
  "briefing": "<the narrative a trainee reads before the call>",
  "critical_data_points": [
    {"key": "<snake_case_id>", "label": "<UI label>", "match_hints": ["<phrase>", "..."]}
  ],
  "missing_information": ["<short description of what the notes did not cover>"]
}"""


class ClaudeScenarioDrafter(ScenarioDraftingPort):

    def __init__(
        self,
        api_key: str,
        model: str,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.5,
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def draft(self, incident: IncidentOutcome) -> ScenarioDraftContent:
        user_prompt = self._build_user_prompt(incident)

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw_text = response.content[0].text
                return self._parse(raw_text)

            except RETRYABLE_ERRORS as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))

            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as error:
                # Malformado/incompleto no es transitorio de red — no vale la pena reintentar con
                # el mismo prompt (mismo criterio que `ClaudeMetricsJudge._parse`). `TypeError`
                # cubre un JSON bien formado pero con la forma equivocada (p.ej.
                # `critical_data_points` como string en vez de lista de objetos), que revienta en
                # `point["key"]` más abajo en `_parse`.
                raise ScenarioDraftingError(
                    f"Drafter returned an unparseable response: {error}"
                ) from error

        raise ScenarioDraftingError(
            f"Scenario drafter unavailable after {self.max_retries + 1} attempts"
        ) from last_error

    @staticmethod
    def _build_user_prompt(incident: IncidentOutcome) -> str:
        return f"""Incident category: {incident.category or "(not categorized)"}
Outcome rating (1-5, as logged by the reviewer): {incident.outcome_rating}
Critical data captured during the real call: {incident.critical_data_captured}
Protocol followed: {incident.protocol_followed}

Post-mortem notes:
{incident.notes or "(no post-mortem notes were recorded for this incident)"}
"""

    @staticmethod
    def _parse(raw_text: str) -> ScenarioDraftContent:
        payload = json.loads(raw_text)

        difficulty = payload["difficulty"]
        if difficulty not in _VALID_DIFFICULTIES:
            raise ValueError(f"unexpected difficulty value in drafter response: {payload!r}")

        return ScenarioDraftContent(
            title=payload["title"],
            category=payload["category"],
            difficulty=difficulty,
            language=payload["language"],
            description=payload["description"],
            briefing=payload["briefing"],
            critical_data_points=[
                CriticalDataPoint(
                    key=point["key"],
                    label=point["label"],
                    match_hints=point.get("match_hints", []),
                )
                for point in payload["critical_data_points"]
            ],
            missing_information=payload.get("missing_information", []),
            raw_response=raw_text,
        )
