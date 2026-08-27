"""Motor de métricas/ponderado — roadmap Fase 2, TODO-10 resuelto.

Dominio puro (ADR-0006): no importa FastAPI ni ningún adaptador de persistencia/STT/TTS/LLM.
Opera sobre datos ya extraídos (transcript, escenario, timestamps) — nunca llama a un reloj, el
reloj del servidor (`SessionRecord.started_at`/`ended_at`, ya autoridad única por
`TurnStateMachine`) siempre se pasa calculado desde afuera.

Fórmula (pesos confirmados con el usuario — completitud 40% / tiempo-a-dato-crítico 30% /
claridad 20% / tiempo total 10%): ver `ScoreWeights`. No vive en el dominio de Settings — el
roadmap limita Settings a voz de TTS, esto se ajusta por variables de entorno si hace falta
re-tunear sin código, no por una pantalla.

Completitud usa coincidencia de palabra clave contra el texto de los turnos `operator` — una
heurística determinista y testeable, no una segunda llamada a Claude (evita costo/latencia/
no-determinismo adicional).

**TODO-17 (resuelto parcialmente):** matchear solo contra el `label` de cada `CriticalDataPoint`
(ej. "Vehicle description") resultó, en una llamada real de punta a punta, en 17/100 de
completitud sobre un reporte correcto y en lenguaje natural — el label es una etiqueta de UI, no
vocabulario que un reporte real repita literalmente. El fix: `CriticalDataPoint.match_hints`
(ver `core/ports.py`) deja que quien autora el escenario liste frases de CONTENIDO esperado (ej.
`["toyota camry", "camry"]`), matcheadas por substring — no por palabra suelta, porque son frases
elegidas a propósito, no un label genérico. El matching por palabra del label se mantiene como
último recurso para escenarios sin `match_hints` todavía (compatibilidad), pero para escenarios
nuevos se recomienda siempre completar `match_hints`. Esto sigue siendo una heurística
determinista, no extracción semántica real — si en el uso real resulta insuficiente (ej. el
entrenando usa una sinonimia que nadie previó), la mejora natural sigue siendo extracción vía
LLM, con su propio análisis de costo/latencia — no se descartó, solo se resolvió lo barato primero.
"""

import os
from dataclasses import dataclass

from core.ports import CriticalDataPoint, ScenarioLocation, VideoGroundTruthPoint
from core.turn_latency import compute_response_latency, rate_response_latency
from core.turn_state import TurnTransition

FILLER_WORDS = {"um", "uh", "like", "you know", "so", "actually", "basically"}

# Ver ADR-0010: escenarios de video (docs/designs/escenarios-de-video.md). `VideoGroundTruthPoint`
# tiene los mismos campos que `_matches_point` necesita (`label`, `match_hints`) — se puede
# mezclar con `CriticalDataPoint` en la misma lista de puntos sin ningún cambio en `_completeness`/
# `_time_to_critical_data`. Esto es deliberado (evita una segunda "pasada" de scoring paralela
# para video — ver hallazgo de diseño sobre plegar cobertura de video en `collected`/`missing`
# existentes en vez de un panel nuevo) — un video-scenario simplemente pasa
# `critical_data_points + video_ground_truth` como los mismos "puntos" de siempre.
REACTION_TARGET_SECONDS = 15.0  # tiempo "bueno" de reacción tras terminar el video pre-llamada
REACTION_MAX_SECONDS = 60.0

# Bandas objetivo del motor de scoring — ajustables por env igual que los pesos, sin ADR propio
# porque son parámetros de calibración, no una decisión arquitectónica.
TIME_TO_CRITICAL_TARGET_SECONDS = 60.0
TIME_TO_CRITICAL_MAX_SECONDS = 180.0
TOTAL_TIME_TARGET_MIN_SECONDS = 90.0
TOTAL_TIME_TARGET_MAX_SECONDS = 240.0


@dataclass(frozen=True)
class ScoreWeights:
    completeness: float = 0.40
    time_to_critical_data: float = 0.30
    clarity: float = 0.20
    total_time: float = 0.10

    @classmethod
    def from_env(cls) -> "ScoreWeights":
        return cls(
            completeness=float(os.getenv("METRICS_WEIGHT_COMPLETENESS", cls.completeness)),
            time_to_critical_data=float(
                os.getenv("METRICS_WEIGHT_TIME_TO_CRITICAL", cls.time_to_critical_data)
            ),
            clarity=float(os.getenv("METRICS_WEIGHT_CLARITY", cls.clarity)),
            total_time=float(os.getenv("METRICS_WEIGHT_TOTAL_TIME", cls.total_time)),
        )


def score_session(
    transcript: list[dict],
    critical_data_points: list[CriticalDataPoint],
    started_at: float,
    ended_at: float,
    outcome: str,
    weights: ScoreWeights | None = None,
    video_ground_truth: list[VideoGroundTruthPoint] | None = None,
    video_ended_at: float | None = None,
    turn_history: list[TurnTransition] | None = None,
    location: ScenarioLocation | None = None,
) -> dict | None:
    """Devuelve un dict con la forma exacta de `Evaluation` (`frontend/src/types.ts`), o `None`.

    `communication_coaching` (docs/designs/motor-de-metricas.md, Fase 2 Pass 1 — corregido tras
    la voz independiente de diseño): panel cualitativo nuevo, separado de `category_scores` a
    propósito — `category_scores` es una fórmula ponderada ya confirmada con el usuario
    (`TODO-10` RESOLVED) y no se reabre. `response_latency` se computa aquí, puro, a partir de
    `turn_history` (ya sellado por `TurnStateMachine`, ver `core/turn_latency.py`).
    `transcription_confidence`/`coherence`/`english_quality` quedan en `None` — los completa
    `finish_call` (`server/app.py`) después de esta función, porque dependen del juez LLM
    (`llm/metrics_judge.py`, adaptador con red — no puede vivir en este módulo puro, ADR-0006).

    `None` únicamente cuando `outcome == "network_drop"` (roadmap: "puntaje diferenciado —
    abandono deliberado vs. caída de red"): una sesión cortada por la red no se puntúa de forma
    punitiva, el frontend muestra "sesión interrumpida, no evaluada" en su lugar. Toda sesión
    terminada con `call.end` explícito (`outcome == "ended"`) SÍ se puntúa siempre, aunque haya
    terminado temprano con completitud baja — el desglose ya comunica eso; no existe una
    categoría de "abandono deliberado" separada porque el servidor no puede observar esa
    intención de forma confiable, solo si el cliente pidió terminar o si la conexión se cayó.

    Escenarios de video (ver ADR-0010): `video_ground_truth` se mezcla con
    `critical_data_points` para completitud/tiempo-a-dato-crítico — mismo mecanismo, mismas
    claves de salida, sin panel/categoría paralela (ver hallazgo de diseño). La única clave
    nueva es `video_reaction_seconds` (`None` cuando no hay video en esta sesión, o cuando el
    video nunca terminó de reproducirse antes de la llamada) — las filas de historial ya
    persistidas no la tienen, y eso es válido: el frontend debe tratar su ausencia como "no
    aplica", nunca como 0.
    """

    if outcome == "network_drop":
        return None

    weights = weights or ScoreWeights.from_env()
    video_ground_truth = video_ground_truth or []
    # docs/designs/ubicacion-del-incidente.md (ADR-0010-style: mismo mecanismo, sin categoría
    # ponderada nueva). Se puntúa incondicionalmente si hay ubicación configurada — nunca una
    # exención por "el trainee se saltó la pantalla de pre-llamada" (el borrador inicial de esa
    # revisión proponía justo eso y la voz independiente de ingeniería lo marcó como un exploit de
    # scoring controlado por el cliente sin persistencia real; se eliminó del diseño final).
    all_points = [*critical_data_points, *video_ground_truth, *_location_critical_points(location)]

    completeness, collected, missing = _completeness(transcript, all_points)
    time_score = _time_to_critical_data(transcript, all_points, started_at)
    if time_score is None:
        time_score = 100.0  # el escenario no define datos críticos: no penaliza esta categoría
    clarity = _clarity(transcript)
    total_time = _total_time(started_at, ended_at)

    overall = (
        weights.completeness * completeness
        + weights.time_to_critical_data * time_score
        + weights.clarity * clarity
        + weights.total_time * total_time
    )

    reaction_seconds = _video_reaction_seconds(transcript, video_ground_truth, video_ended_at)
    strengths, improvements = _narrative(completeness, time_score, clarity, missing, reaction_seconds)
    response_latency = rate_response_latency(compute_response_latency(turn_history or []))

    return {
        "overall_score": round(overall),
        "category_scores": {
            "completeness": round(completeness),
            "time_to_critical_data": round(time_score),
            "clarity": round(clarity),
            "total_time": round(total_time),
        },
        "collected": collected,
        "missing": missing,
        "strengths": strengths,
        "improvements": improvements,
        "summary": _summary(overall, missing),
        "video_reaction_seconds": reaction_seconds,
        "communication_coaching": {
            "response_latency": response_latency,
            "transcription_confidence": None,
            "coherence": None,
            "english_quality": None,
        },
    }


def _words(text: str) -> list[str]:
    return [word.strip(".,!?;:").lower() for word in text.split() if word.strip(".,!?;:")]


def _operator_turns(transcript: list[dict]) -> list[dict]:
    return [turn for turn in transcript if turn.get("role") == "operator"]


def _matches_point(text_lower: str, point: CriticalDataPoint) -> bool:
    if point.label.lower() in text_lower:
        return True

    # TODO-17: match_hints son frases de contenido autoradas a propósito (no un label genérico),
    # así que se comparan por substring completo, sin el requisito de longitud>3 de abajo.
    if any(hint.strip() and hint.strip().lower() in text_lower for hint in point.match_hints):
        return True

    # docs/designs/ubicacion-del-incidente.md, Fase 3 Sección 1 — `word_fallback=False` apaga este
    # último recurso para puntos cuyo `label` es contenido real (ej. "Street: 5th Avenue"), no una
    # etiqueta de UI genérica: sin este flag, "avenue"/"street" sueltos en cualquier transcript
    # marcarían el punto como cumplido. `getattr` con default `True` porque `VideoGroundTruthPoint`
    # (mezclado en la misma lista de `all_points`, ver ADR-0010) no tiene este campo — mismo
    # comportamiento de siempre para video y para cualquier `CriticalDataPoint` ya autorado.
    if not getattr(point, "word_fallback", True):
        return False

    # Coincidencia permisiva a nivel de palabra sobre el label — último recurso para escenarios
    # sin match_hints todavía. Ver docstring del módulo sobre por qué esto es una heurística y no
    # extracción semántica real.
    return any(len(word) > 3 and word in text_lower for word in point.label.lower().split())


def _completeness(
    transcript: list[dict], points: list[CriticalDataPoint]
) -> tuple[float, list[str], list[str]]:
    if not points:
        return 100.0, [], []

    operator_text = " ".join(turn.get("text", "") for turn in _operator_turns(transcript)).lower()
    collected = [point.label for point in points if _matches_point(operator_text, point)]
    missing = [point.label for point in points if point.label not in collected]

    return 100.0 * len(collected) / len(points), collected, missing


def _time_to_critical_data(
    transcript: list[dict], points: list[CriticalDataPoint], started_at: float
) -> float | None:
    # docs/designs/ubicacion-del-incidente.md, Fase 3 Sección 1 (hallazgo B5) — cualquier punto
    # nuevo en `all_points` solo puede adelantar o igualar esta categoría (30% del peso total),
    # nunca atrasarla, porque el loop de abajo se detiene en la PRIMERA mención de CUALQUIER punto.
    # Agregar puntos sin pensarlo re-pesa silenciosamente la categoría más pesada del score.
    # `counts_toward_timing=False` los excluye de este cálculo (siguen contando para completeness).
    points = [p for p in points if getattr(p, "counts_toward_timing", True)]
    if not points:
        return None

    for turn in _operator_turns(transcript):
        text_lower = turn.get("text", "").lower()
        if not any(_matches_point(text_lower, point) for point in points):
            continue

        elapsed = turn.get("at", started_at) - started_at
        if elapsed <= TIME_TO_CRITICAL_TARGET_SECONDS:
            return 100.0
        if elapsed >= TIME_TO_CRITICAL_MAX_SECONDS:
            return 0.0

        span = TIME_TO_CRITICAL_MAX_SECONDS - TIME_TO_CRITICAL_TARGET_SECONDS
        return 100.0 * (1 - (elapsed - TIME_TO_CRITICAL_TARGET_SECONDS) / span)

    return 0.0  # ningún turno del supervisor mencionó un dato crítico


def is_location_configured(location: ScenarioLocation | None) -> bool:
    """Regla única de "¿hay ubicación configurada?" — docs/designs/ubicacion-del-incidente.md,
    Fase 3 Sección 1 (hallazgo B9). El endpoint `PUT /scenarios/{id}/location` (`server/app.py`) es
    la única fuente de verdad autoritativa (rechaza con 422 un marcador sin texto); el frontend
    duplica esta misma regla solo como UX (deshabilitar guardado antes de golpear el 422) — no
    comparten código real entre Python y TypeScript, se documenta como copia, no como "una sola
    función compartida".
    """

    if location is None:
        return False
    return bool(location.street.strip() or location.cross_street.strip() or location.landmark.strip())


def _location_critical_points(location: ScenarioLocation | None) -> list[CriticalDataPoint]:
    """Deriva 0-3 `CriticalDataPoint`s planos desde `ScenarioLocation` — uno por campo de texto no
    vacío (calle/cruce/referencia). Reusa `CriticalDataPoint` en vez de una entidad de ground-truth
    paralela (a diferencia de `VideoGroundTruthPoint`, que sí lo justifica por tener campos
    estructurales propios — ver ADR-0010): calle/cruce/referencia no necesitan nada que
    `CriticalDataPoint` no tenga ya. `word_fallback=False`/`counts_toward_timing=False` en los tres
    — ver comentarios en `CriticalDataPoint` (`core/ports.py`) y en `_time_to_critical_data` arriba.
    """

    if not is_location_configured(location):
        return []  # nunca generar puntos vacíos que siempre fallan

    fields = (
        ("location_street", "Street", location.street),
        ("location_cross_street", "Cross street", location.cross_street),
        ("location_landmark", "Landmark", location.landmark),
    )
    points = []
    for key, field_label, value in fields:
        if value.strip():
            points.append(
                CriticalDataPoint(
                    key=key,
                    label=f"{field_label}: {value.strip()}",
                    match_hints=[value.strip(), *location.match_hints],
                    required=True,
                    word_fallback=False,
                    counts_toward_timing=False,
                )
            )
    return points


def _video_reaction_seconds(
    transcript: list[dict], video_ground_truth: list[VideoGroundTruthPoint], video_ended_at: float | None
) -> float | None:
    """Segundos entre que terminó el video pre-llamada y la primera mención de cualquier dato de
    su ground truth (ADR-0010) — anclado a `video_ended_at` (reloj del servidor, sellado por el
    evento WS `video.ended`), NUNCA a `started_at`/`call.start`: un entrenando puede ver el
    video, pausar, tomarse un café, y arrancar la llamada después — confundir esos dos relojes
    fue un hallazgo explícito de la revisión de ingeniería (5c).

    `None` (no un número) cuando no hay escenario de video en esta sesión, o el cliente nunca
    mandó `video.ended` (por ejemplo: el entrenando tomó el camino de texto en un escenario
    mixto, o se saltó el video por un error de reproducción) — un `None` es "no aplica", nunca
    "reaccionó en 0 segundos".
    """

    if not video_ground_truth or video_ended_at is None:
        return None

    for turn in _operator_turns(transcript):
        text_lower = turn.get("text", "").lower()
        if not any(_matches_point(text_lower, point) for point in video_ground_truth):
            continue

        elapsed = turn.get("at", video_ended_at) - video_ended_at
        return max(0.0, elapsed)

    return None  # el entrenando nunca mencionó nada del ground truth de video — sin dato, no 0


def _clarity(transcript: list[dict]) -> float:
    words = [word for turn in _operator_turns(transcript) for word in _words(turn.get("text", ""))]

    if not words:
        return 100.0

    ratio = sum(1 for word in words if word in FILLER_WORDS) / len(words)
    return max(0.0, 100.0 - ratio * 400.0)  # 25% de muletillas ya lleva el score a 0


def _total_time(started_at: float, ended_at: float) -> float:
    duration = ended_at - started_at

    if TOTAL_TIME_TARGET_MIN_SECONDS <= duration <= TOTAL_TIME_TARGET_MAX_SECONDS:
        return 100.0

    if duration < TOTAL_TIME_TARGET_MIN_SECONDS:
        return 100.0 * max(0.0, duration / TOTAL_TIME_TARGET_MIN_SECONDS)

    return max(0.0, 100.0 - (duration - TOTAL_TIME_TARGET_MAX_SECONDS) / 2.0)


def _narrative(
    completeness: float,
    time_score: float,
    clarity: float,
    missing: list[str],
    reaction_seconds: float | None = None,
) -> tuple[list[str], list[str]]:
    strengths, improvements = [], []

    if completeness >= 80:
        strengths.append("Collected nearly all the critical details the dispatcher needed.")
    if time_score >= 80:
        strengths.append("Got to the most critical information quickly.")
    if clarity >= 80:
        strengths.append("Communicated clearly, with minimal filler words.")

    # Nota cualitativa, nunca un número de cronómetro junto al score (hallazgo de diseño: un
    # "tiempo de reacción" puntuado se siente como un test de reflejos encima de un video
    # perturbador) — por eso vive como frase en strengths/improvements, no como categoría
    # ponderada nueva en `category_scores`.
    if reaction_seconds is not None:
        if reaction_seconds <= REACTION_TARGET_SECONDS:
            strengths.append("Reported what the video showed right away, with barely a pause.")
        elif reaction_seconds >= REACTION_MAX_SECONDS:
            improvements.append("Take a breath, then report — but don't let too much time pass before calling in what you saw.")

    if completeness < 60:
        detail = ", ".join(missing[:3]) if missing else "key details"
        improvements.append(f"Confirm more critical details before ending the call — missing: {detail}.")
    if time_score < 50:
        improvements.append("Lead with the most critical detail (e.g. plate/VIN or location) earlier.")
    if clarity < 60:
        improvements.append("Reduce filler words (um, uh, like) for clearer radio communication.")

    if not strengths:
        strengths.append("Completed the call and engaged with the dispatcher's questions.")
    if not improvements:
        improvements.append("Keep practicing to stay this sharp under pressure.")

    return strengths, improvements


def _summary(overall: float, missing: list[str]) -> str:
    if overall >= 85:
        return "Strong call — clear communication and nearly all critical details collected."
    if overall >= 60:
        gap = f" Still missing: {', '.join(missing[:2])}." if missing else ""
        return f"Solid call with room to improve.{gap}"
    return "This call needs more practice — several critical details were missed or delayed."
