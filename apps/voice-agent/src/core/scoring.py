"""Motor de métricas/ponderado — roadmap Fase 2, TODO-10 resuelto.

Dominio puro (ADR-0006): no importa FastAPI ni ningún adaptador de persistencia/STT/TTS/LLM.
Opera sobre datos ya extraídos (transcript, escenario, timestamps) — nunca llama a un reloj, el
reloj del servidor (`SessionRecord.started_at`/`ended_at`, ya autoridad única por
`TurnStateMachine`) siempre se pasa calculado desde afuera.

Fórmula (pesos confirmados con el usuario — completitud 40% / tiempo-a-dato-crítico 30% /
claridad 20% / tiempo total 10%): ver `ScoreWeights`. No vive en el dominio de Settings — el
roadmap limita Settings a voz de TTS, esto se ajusta por variables de entorno si hace falta
re-tunear sin código, no por una pantalla.

Completitud usa coincidencia de palabra clave del `label` de cada `CriticalDataPoint` contra el
texto de los turnos `operator` — una heurística determinista y testeable, no una segunda llamada
a Claude (evita costo/latencia/no-determinismo adicional). Documentado como simplificación
mejorable, no como decisión final de producto — si en el uso real resulta demasiado burda, la
mejora natural es extracción vía LLM, con su propio análisis de costo/latencia primero.
"""

import os
from dataclasses import dataclass

from core.ports import CriticalDataPoint

FILLER_WORDS = {"um", "uh", "like", "you know", "so", "actually", "basically"}

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
) -> dict | None:
    """Devuelve un dict con la forma exacta de `Evaluation` (`frontend/src/types.ts`), o `None`.

    `None` únicamente cuando `outcome == "network_drop"` (roadmap: "puntaje diferenciado —
    abandono deliberado vs. caída de red"): una sesión cortada por la red no se puntúa de forma
    punitiva, el frontend muestra "sesión interrumpida, no evaluada" en su lugar. Toda sesión
    terminada con `call.end` explícito (`outcome == "ended"`) SÍ se puntúa siempre, aunque haya
    terminado temprano con completitud baja — el desglose ya comunica eso; no existe una
    categoría de "abandono deliberado" separada porque el servidor no puede observar esa
    intención de forma confiable, solo si el cliente pidió terminar o si la conexión se cayó.
    """

    if outcome == "network_drop":
        return None

    weights = weights or ScoreWeights.from_env()

    completeness, collected, missing = _completeness(transcript, critical_data_points)
    time_score = _time_to_critical_data(transcript, critical_data_points, started_at)
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

    strengths, improvements = _narrative(completeness, time_score, clarity, missing)

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
    }


def _words(text: str) -> list[str]:
    return [word.strip(".,!?;:").lower() for word in text.split() if word.strip(".,!?;:")]


def _operator_turns(transcript: list[dict]) -> list[dict]:
    return [turn for turn in transcript if turn.get("role") == "operator"]


def _matches_point(text_lower: str, point: CriticalDataPoint) -> bool:
    if point.label.lower() in text_lower:
        return True

    # Coincidencia permisiva a nivel de palabra — ver docstring del módulo sobre por qué esto es
    # una heurística y no extracción semántica real.
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
    completeness: float, time_score: float, clarity: float, missing: list[str]
) -> tuple[list[str], list[str]]:
    strengths, improvements = [], []

    if completeness >= 80:
        strengths.append("Collected nearly all the critical details the dispatcher needed.")
    if time_score >= 80:
        strengths.append("Got to the most critical information quickly.")
    if clarity >= 80:
        strengths.append("Communicated clearly, with minimal filler words.")

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
