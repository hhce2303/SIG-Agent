"""Unit tests de `ClaudeMetricsJudge` (T13/T16, docs/designs/motor-de-metricas.md), con el
cliente de Anthropic mockeado — mismo patrón que `test_claude_dispatcher.py`.

**Límite de estos tests (hallazgo de la voz independiente de ingeniería, ya anotado en la
revisión de `/autoplan`, Fase 3 Sección 3):** mockear una respuesta JSON fija prueba la
mecánica (parseo, reintentos, degradación) — NO prueba que el juicio real de Claude sobre
coherencia/inglés sea bueno. Este repo no tenía, hasta ahora, ningún precedente de testear
calidad de output no-determinista de un LLM (`core/scoring.py` evita explícitamente una segunda
llamada a Claude por esta razón). Un eval real (contra la API real, no mockeada, comparando
contra el caso base de TODO-17) es trabajo separado, fuera del alcance de un unit test — ver
`docs/architecture/TODOS.md` y la nota al final de este archivo.
"""

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from anthropic import APIConnectionError, RateLimitError

from core.ports import CriticalDataPoint, MetricsJudgeError
from llm.metrics_judge import ClaudeMetricsJudge

VEHICLE_THEFT_POINTS = [
    CriticalDataPoint(key="vehicle_description", label="Vehicle description"),
    CriticalDataPoint(key="license_plate", label="License plate"),
]

# El reporte "perfecto" real de TODO-17 (docs/architecture/TODOS.md) — lenguaje natural, sin
# repetir los labels de UI literalmente. Caso base de regresión: el judge debe seguir marcando
# esto como coherente/completo aunque `_completeness` (keyword-matching) lo puntúe bajo sin
# `match_hints`.
TODO_17_TRANSCRIPT = [
    {
        "role": "operator",
        "text": (
            "Someone broke into my white Toyota Camry and stole it, plate ABC123, it happened "
            "about ten minutes ago near the shopping center on 5th street."
        ),
    }
]


def _response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _fake_request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


_VALID_JSON = (
    '{"coherence_rating": "good", "coherence_tip": "Clear and well organized.", '
    '"english_quality_rating": "good", "english_quality_tip": "Fluent, no notable errors.", '
    '"completeness_agrees_with_keyword_match": true}'
)


@pytest.fixture
def judge():
    with patch("llm.metrics_judge.Anthropic"):
        return ClaudeMetricsJudge(
            api_key="test-key",
            model="claude-test",
            max_retries=2,
            retry_delay_seconds=0,
        )


def test_judge_parses_a_valid_response(judge):
    judge.client.messages.create.return_value = _response(_VALID_JSON)

    result = judge.judge(TODO_17_TRANSCRIPT, VEHICLE_THEFT_POINTS, collected=[], missing=["Vehicle description", "License plate"])

    assert result.coherence_rating == "good"
    assert result.english_quality_rating == "good"
    assert result.completeness_agrees_with_keyword_match is True
    assert result.raw_response == _VALID_JSON


def test_judge_disagrees_with_keyword_match_on_the_todo_17_case():
    """Caso base de TODO-17: el keyword-matching marca "missing" ambos puntos porque el reporte
    no repite los labels literalmente, pero un juicio semántico real los encuentra presentes —
    el judge debe poder señalar esa discrepancia (`completeness_agrees_with_keyword_match=False`)
    en vez de estar forzado a coincidir con el heurístico que ya se sabe insuficiente."""

    disagreement_json = _VALID_JSON.replace('"completeness_agrees_with_keyword_match": true', '"completeness_agrees_with_keyword_match": false')

    with patch("llm.metrics_judge.Anthropic"):
        judge = ClaudeMetricsJudge(api_key="k", model="m", retry_delay_seconds=0)
    judge.client.messages.create.return_value = _response(disagreement_json)

    result = judge.judge(TODO_17_TRANSCRIPT, VEHICLE_THEFT_POINTS, collected=[], missing=["Vehicle description", "License plate"])

    assert result.completeness_agrees_with_keyword_match is False


def test_judge_retries_on_transient_error_then_succeeds(judge):
    judge.client.messages.create.side_effect = [
        APIConnectionError(request=_fake_request()),
        _response(_VALID_JSON),
    ]

    result = judge.judge([], [], collected=[], missing=[])

    assert result.coherence_rating == "good"
    assert judge.client.messages.create.call_count == 2


def test_judge_raises_metrics_judge_error_after_exhausting_retries(judge):
    judge.client.messages.create.side_effect = RateLimitError(
        message="rate limited",
        response=httpx.Response(429, request=_fake_request()),
        body=None,
    )

    with pytest.raises(MetricsJudgeError):
        judge.judge([], [], collected=[], missing=[])

    assert judge.client.messages.create.call_count == 3  # max_retries=2 -> 3 intentos


def test_judge_raises_metrics_judge_error_on_malformed_json(judge):
    judge.client.messages.create.return_value = _response("not valid json at all")

    with pytest.raises(MetricsJudgeError):
        judge.judge([], [], collected=[], missing=[])

    # JSON malformado no es transitorio — no vale la pena reintentar con el mismo prompt.
    judge.client.messages.create.assert_called_once()


def test_judge_raises_metrics_judge_error_on_missing_expected_keys(judge):
    judge.client.messages.create.return_value = _response('{"coherence_rating": "good"}')

    with pytest.raises(MetricsJudgeError):
        judge.judge([], [], collected=[], missing=[])


def test_judge_raises_metrics_judge_error_on_unexpected_rating_value(judge):
    bad_rating_json = _VALID_JSON.replace('"coherence_rating": "good"', '"coherence_rating": "excellent"')
    judge.client.messages.create.return_value = _response(bad_rating_json)

    with pytest.raises(MetricsJudgeError):
        judge.judge([], [], collected=[], missing=[])


def test_judge_prompt_explicitly_forbids_scoring_accent():
    """Fase 1 0A punto 1 de la revisión: el prompt debe decir explícitamente que NO se puntúa
    acento/pronunciación (el texto de la transcripción no da esa señal) — no basta con que el
    prompt no lo pida, tiene que prohibirlo activamente para que el modelo no lo infiera solo."""

    from llm.metrics_judge import _SYSTEM_PROMPT

    lowered = _SYSTEM_PROMPT.lower()
    assert "do not score accent" in lowered or "not score accent" in lowered
    assert "pronunciation" in lowered


# NOTA (T16, no automatizado acá): un eval real de calidad de juicio —¿el judge realmente
# califica bien la coherencia/inglés, no solo devuelve JSON válido?— requiere correr contra la
# API real de Claude con un set de transcripts curados (empezando por TODO_17_TRANSCRIPT arriba
# como caso base) y comparar contra un baseline humano. Eso queda registrado como TODO P1 en
# docs/designs/motor-de-metricas.md (Fase 3, TODOS.md #3) — no se puede mockear sin perder
# exactamente la señal que se quiere medir.
