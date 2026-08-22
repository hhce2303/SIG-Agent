"""Latencia de respuesta del entrenando — motor de métricas, docs/designs/motor-de-metricas.md (T1).

Dominio puro (ADR-0006): opera sobre `TurnTransition.at` (ya sellado por el reloj del servidor,
`core/turn_state.py`), nunca llama a un reloj propio.

El dato ya existe en `TurnStateMachine.history` desde Fase 1 — este módulo solo le agrega el
cálculo que faltaba (ver 0B de la revisión de `/autoplan`: "el dato ya existe, solo no se
calcula la resta"). Mide el tiempo entre que el dispatcher termina de hablar
(`dispatcher_finished_speaking`, transición a `LISTENING`) y el entrenando empieza a responder
(`supervisor_started_speaking`, transición a `SUPERVISOR_SPEAKING`) — un turno sin respuesta
(la llamada termina mientras el dispatcher todavía habla, o mientras se espera al entrenando) no
aporta una muestra, no se inventa un valor.
"""

from dataclasses import dataclass

from core.turn_state import TurnTransition

_DISPATCHER_FINISHED_EVENT = "dispatcher_finished_speaking"
_SUPERVISOR_STARTED_EVENT = "supervisor_started_speaking"


@dataclass(frozen=True)
class ResponseLatency:
    """Resultado agregado de una sesión completa — no solo un promedio, para que el panel de
    coaching pueda ser descriptivo (ver pedido original: "mucho más descriptivo... más
    información") en vez de un solo número sin contexto.
    """

    average_ms: int
    sample_count: int
    fastest_ms: int
    slowest_ms: int
    clamped_negative_count: int


def compute_response_latency(history: list[TurnTransition]) -> ResponseLatency | None:
    """`None` cuando no hay ninguna muestra válida (ej. la llamada terminó antes de que el
    entrenando respondiera ni una vez) — nunca 0, que se leería como "respondió instantáneo".

    Delta negativo (clock skew, o un futuro barge-in donde el entrenando interrumpe antes de que
    el dispatcher termine) se clampa a 0 en vez de descartarse o hacer `raise` — ver Fase 1
    Sección 2 (Error & Rescue) de la revisión: no es un error del sistema, es una muestra rara que
    de todos modos cuenta como "respuesta inmediata".
    """

    samples_ms: list[float] = []
    clamped_negative_count = 0
    pending_finish_at: float | None = None

    for transition in history:
        if transition.event == _DISPATCHER_FINISHED_EVENT:
            pending_finish_at = transition.at
        elif transition.event == _SUPERVISOR_STARTED_EVENT and pending_finish_at is not None:
            delta_seconds = transition.at - pending_finish_at
            if delta_seconds < 0:
                clamped_negative_count += 1
                delta_seconds = 0.0
            samples_ms.append(delta_seconds * 1000)
            pending_finish_at = None

    if not samples_ms:
        return None

    return ResponseLatency(
        average_ms=round(sum(samples_ms) / len(samples_ms)),
        sample_count=len(samples_ms),
        fastest_ms=round(min(samples_ms)),
        slowest_ms=round(max(samples_ms)),
        clamped_negative_count=clamped_negative_count,
    )


# Bandas de calificación — ver docs/designs/motor-de-metricas.md Fase 2, Pass 1: esta señal vive
# en el panel de "Communication Coaching" (tip-card cualitativa), NUNCA en `category_scores`
# (que es una fórmula ponderada ya cerrada, TODO-10 RESOLVED) — mismo precedente que
# `video_reaction_seconds` en `core/scoring.py`.
RESPONSE_LATENCY_GOOD_MS = 3000
RESPONSE_LATENCY_CRITICAL_MS = 8000


def rate_response_latency(latency: ResponseLatency | None) -> dict | None:
    """Convierte un `ResponseLatency` en una tip-card cualitativa (`rating` + `tip` en inglés —
    el resto de la copy de coaching, `core/scoring.py::_narrative`, también está en inglés: es el
    idioma en el que se entrena, NFR-12). `None` si no hubo ninguna muestra — el frontend debe
    ocultar esta tip-card, nunca mostrar un placeholder en 0.
    """

    if latency is None:
        return None

    if latency.average_ms <= RESPONSE_LATENCY_GOOD_MS:
        rating = "good"
        tip = (
            f"You responded in {latency.average_ms}ms on average after the dispatcher "
            "finished speaking — a good, confident pace."
        )
    elif latency.average_ms <= RESPONSE_LATENCY_CRITICAL_MS:
        rating = "improve"
        tip = (
            f"You took {latency.average_ms}ms on average to respond after the dispatcher "
            "finished speaking. Try to close that gap — every second of dead air matters on a "
            "real call."
        )
    else:
        rating = "critical"
        tip = (
            f"You took {latency.average_ms}ms on average to respond — a real dispatcher would "
            "be concerned by silence that long. Practice having the details ready before the "
            "dispatcher finishes talking."
        )

    return {
        "rating": rating,
        "average_ms": latency.average_ms,
        "sample_count": latency.sample_count,
        "fastest_ms": latency.fastest_ms,
        "slowest_ms": latency.slowest_ms,
        "tip": tip,
    }
