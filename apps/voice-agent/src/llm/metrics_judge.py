"""Adaptador del juez de métricas (ver ADR-0006) — implementa `MetricsJudgePort`.

Motor de métricas, docs/designs/motor-de-metricas.md (T3/T13/T16). Mismo cliente/patrón de
reintentos que `llm/claude.py::ClaudeDispatcher` (reusa la misma dependencia, no una nueva) —
la voz independiente de ingeniería en la revisión de `/autoplan` encontró que la ubicación
original propuesta para esto (`core/metrics_judge.py`) violaba el límite hexagonal de
`core/ports.py`: "el dominio depende únicamente de estas interfaces, nunca de las
implementaciones concretas... ahí viven las preocupaciones de resiliencia — nunca en el
dominio." Este archivo es esa implementación concreta.

Corre SIEMPRE post-llamada (`server/app.py::finish_call`), nunca en el loop de turno en vivo — el
presupuesto de latencia en tiempo real (NFR-01, TODO-08) ya está en 5622ms contra un target de
1500ms; agregar el juez ahí lo empeoraría sin necesidad (ver 0A/0C-bis de la revisión). El
llamador es responsable de invocar `judge()` dentro de `asyncio.to_thread` + un timeout (mismo
patrón que `ClaudeDispatcher.respond` en `server/app.py::get_dispatcher_reply`) — este adaptador
no lo hace por sí mismo porque es una llamada síncrona (como todos los adaptadores de este repo).
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

from core.ports import CriticalDataPoint, MetricsJudgeError, MetricsJudgePort, MetricsJudgment

# Mismos errores transitorios que `ClaudeDispatcher` considera dignos de reintento — ver ese
# archivo para la razón de por qué AuthenticationError/BadRequestError no están acá.
RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    OverloadedError,
)

_VALID_RATINGS = {"good", "improve", "critical"}

_SYSTEM_PROMPT = """You are an evaluator scoring a trainee's radio communication in a police \
dispatch training call. You are NOT scoring the dispatcher's performance, only the trainee \
(the "operator" role in the transcript).

Score two dimensions:

1. Coherence: was the trainee's report logically consistent and easy to follow? Did later \
statements contradict earlier ones? Was information organized in a way a real dispatcher could \
act on?
2. English quality: grammar, vocabulary, and fluency of the trainee's spoken English. Do NOT \
score accent or pronunciation — you only have a text transcript, not audio, and accent is not \
something this system measures (a transcript gives you no signal about pronunciation).

Also check: does the list of "collected" critical data points below look complete given what \
the trainee actually said, or does the transcript contain information that was missed by literal \
keyword matching (e.g. the trainee described something in different words)? Answer only from what \
is in the transcript — do not guess.

Respond with ONLY valid JSON, no other text, in exactly this shape:
{
  "coherence_rating": "good" | "improve" | "critical",
  "coherence_tip": "<one or two sentences of specific, actionable coaching, addressed to the trainee as \\"you\\">",
  "english_quality_rating": "good" | "improve" | "critical",
  "english_quality_tip": "<one or two sentences of specific, actionable coaching, addressed to the trainee as \\"you\\">",
  "completeness_agrees_with_keyword_match": true | false | null
}
Use null for completeness_agrees_with_keyword_match only if there were no critical data points \
to check against."""


class ClaudeMetricsJudge(MetricsJudgePort):

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

    def judge(
        self,
        transcript: list[dict],
        critical_data_points: list[CriticalDataPoint],
        collected: list[str],
        missing: list[str],
    ) -> MetricsJudgment:
        user_prompt = self._build_user_prompt(transcript, critical_data_points, collected, missing)

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=400,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw_text = response.content[0].text
                return self._parse(raw_text)

            except RETRYABLE_ERRORS as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))

            except (json.JSONDecodeError, KeyError, ValueError) as error:
                # Malformado/incompleto no es transitorio de red — no vale la pena reintentar
                # con el mismo prompt, se degrada directamente (ver Fase 1 Sección 2 del plan).
                raise MetricsJudgeError(f"Judge returned an unparseable response: {error}") from error

        raise MetricsJudgeError(
            f"Metrics judge unavailable after {self.max_retries + 1} attempts"
        ) from last_error

    @staticmethod
    def _build_user_prompt(
        transcript: list[dict],
        critical_data_points: list[CriticalDataPoint],
        collected: list[str],
        missing: list[str],
    ) -> str:
        operator_lines = "\n".join(
            f"- {turn.get('text', '')}" for turn in transcript if turn.get("role") == "operator"
        )
        points_desc = ", ".join(point.label for point in critical_data_points) or "(none defined)"

        return f"""Critical data points expected for this scenario: {points_desc}
Already matched by keyword search — collected: {collected or "(none)"}, missing: {missing or "(none)"}

Trainee's statements (in order):
{operator_lines or "(the trainee said nothing)"}
"""

    @staticmethod
    def _parse(raw_text: str) -> MetricsJudgment:
        payload = json.loads(raw_text)

        coherence_rating = payload["coherence_rating"]
        english_quality_rating = payload["english_quality_rating"]
        if coherence_rating not in _VALID_RATINGS or english_quality_rating not in _VALID_RATINGS:
            raise ValueError(f"unexpected rating value in judge response: {payload!r}")

        return MetricsJudgment(
            coherence_rating=coherence_rating,
            coherence_tip=payload["coherence_tip"],
            english_quality_rating=english_quality_rating,
            english_quality_tip=payload["english_quality_tip"],
            completeness_agrees_with_keyword_match=payload.get("completeness_agrees_with_keyword_match"),
            raw_response=raw_text,
        )
