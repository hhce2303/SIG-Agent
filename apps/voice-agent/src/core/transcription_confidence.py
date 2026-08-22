"""Confianza de transcripción de Whisper, agregada en una tip-card cualitativa — motor de
métricas, docs/designs/motor-de-metricas.md (T2/T4).

Dominio puro (ADR-0006): opera sobre `SttSegment` (ya calculados por el adaptador de STT, ver
`stt/whisper.py`), nunca llama a faster-whisper directamente.

**Naming deliberado (Fase 1 0A punto 1 de la revisión):** esto NUNCA se llama "acento"/"accent".
faster-whisper no tiene clasificador de acento ni ground-truth contra qué validarlo — la señal
disponible (`avg_logprob`/`no_speech_prob`/`compression_ratio`) conflaciona ruido de fondo,
calidad de mic, muletillas/falsos-inicios, Y acento sin ninguna forma de aislar el componente de
acento de los otros tres. Nombrar un campo "accent_score" a partir de este dato sería nombrar mal
el dato — lo que en realidad se mide es "qué tan seguro estuvo el modelo de lo que transcribió".
"""

from dataclasses import dataclass

from core.ports import SttSegment

# Mismo umbral que ya usaba `stt/whisper.py` para el marcador inline `[unclear: ...]` (NFR-09) —
# el adaptador importa esta constante desde aquí (dirección correcta de dependencia hexagonal:
# adaptador → dominio, nunca al revés) en vez de duplicarla.
LOW_CONFIDENCE_THRESHOLD = -1.0

_GOOD_AVG_LOGPROB = -0.3
_CRITICAL_LOW_CONFIDENCE_RATIO = 0.35  # 35%+ de segmentos poco claros ya es una llamada difícil


@dataclass(frozen=True)
class TranscriptionConfidence:
    average_logprob: float
    segment_count: int
    low_confidence_segment_count: int
    low_confidence_ratio: float


def aggregate_transcription_confidence(segments: list[SttSegment]) -> TranscriptionConfidence | None:
    """`None` si no hubo ningún segmento con texto real (llamada vacía/silenciosa) — no se
    inventa un score de confianza sobre nada."""

    texted = [segment for segment in segments if segment.text.strip()]
    if not texted:
        return None

    low_confidence_count = sum(1 for segment in texted if segment.is_low_confidence)

    return TranscriptionConfidence(
        average_logprob=sum(segment.avg_logprob for segment in texted) / len(texted),
        segment_count=len(texted),
        low_confidence_segment_count=low_confidence_count,
        low_confidence_ratio=low_confidence_count / len(texted),
    )


def rate_transcription_confidence(confidence: TranscriptionConfidence | None) -> dict | None:
    """Tip-card cualitativa para el panel de "Communication Coaching" — nunca un campo llamado
    "acento" (ver docstring del módulo). `None` si `confidence` es `None` (nada que puntuar).
    """

    if confidence is None:
        return None

    if (
        confidence.average_logprob >= _GOOD_AVG_LOGPROB
        and confidence.low_confidence_ratio < 0.15
    ):
        rating = "good"
        tip = (
            "Your speech came through clearly — the transcription had high confidence "
            "throughout the call."
        )
    elif confidence.low_confidence_ratio >= _CRITICAL_LOW_CONFIDENCE_RATIO:
        rating = "critical"
        tip = (
            f"{confidence.low_confidence_segment_count} of {confidence.segment_count} segments "
            "were hard to transcribe — check your microphone, reduce background noise, and slow "
            "down on critical details like plates or VINs."
        )
    else:
        rating = "improve"
        tip = (
            f"{confidence.low_confidence_segment_count} of {confidence.segment_count} segments "
            "were flagged as unclear. Speaking a bit slower on critical details can help the "
            "dispatcher (and the transcript) catch them the first time."
        )

    return {
        "rating": rating,
        "segment_count": confidence.segment_count,
        "low_confidence_segment_count": confidence.low_confidence_segment_count,
        "tip": tip,
    }
