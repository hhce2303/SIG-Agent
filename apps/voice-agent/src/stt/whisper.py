from faster_whisper import WhisperModel

from core.ports import SpeechToTextPort, SttSegment, TranscriptionResult
from core.transcription_confidence import LOW_CONFIDENCE_THRESHOLD


class WhisperSTT(SpeechToTextPort):
    """Adaptador de STT (ver ADR-0006) — implementa `SpeechToTextPort`.

    NFR-09: los segmentos de baja confianza (`avg_logprob` por debajo de
    `LOW_CONFIDENCE_THRESHOLD`) se marcan inline como `[unclear: ...]` en `TranscriptionResult.text`
    — el marcador viaja tal cual hasta el dispatcher, cuyo system prompt (ver `llm/claude.py`)
    sabe pedirle al caller que repita/deletree un dato crítico marcado así.

    **Migración T2/T12 (docs/designs/motor-de-metricas.md):** `transcribe()` devolvía un `str`
    a propósito hasta ahora — el docstring original explicaba que cambiar la firma hubiera
    obligado a tocar `SpeechToTextPort`, `VoiceConversation`, y todos los stubs de test en
    cascada. Esa migración ya se hizo, atómicamente, en el mismo cambio que este archivo: ahora
    se preservan `avg_logprob`/`no_speech_prob`/`compression_ratio`/timestamps/`words` por
    segmento (antes se descartaban después de decidir el marcador inline) y
    `info.language_probability`, para el motor de métricas (confianza de transcripción — NUNCA
    llamada "acento", ver `core/transcription_confidence.py`).
    """

    LOW_CONFIDENCE_THRESHOLD = LOW_CONFIDENCE_THRESHOLD

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )

    def transcribe(self, audio_path: str) -> TranscriptionResult:

        segments, info = self.model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500,
            },
            initial_prompt=(
                "This is a police emergency call. "
                "The caller may report stolen vehicles, "
                "vehicle descriptions, license plates, "
                "locations, times, names, and incidents. "
                "The conversation is in English."
            ),
        )

        parts = []
        stt_segments: list[SttSegment] = []

        for segment in segments:
            text = segment.text.strip()
            is_low_confidence = bool(text) and segment.avg_logprob < self.LOW_CONFIDENCE_THRESHOLD

            display_text = f"[unclear: {text}]" if is_low_confidence else text
            parts.append(display_text)

            if text:
                stt_segments.append(
                    SttSegment(
                        text=text,
                        avg_logprob=segment.avg_logprob,
                        # `no_speech_prob`/`compression_ratio` no siempre están en el stub de
                        # test (SimpleNamespace mínimo) ni en versiones viejas de faster-whisper
                        # — default a 0.0 en vez de romper la transcripción real por un campo de
                        # métricas secundario.
                        no_speech_prob=getattr(segment, "no_speech_prob", 0.0),
                        compression_ratio=getattr(segment, "compression_ratio", 0.0),
                        start_seconds=getattr(segment, "start", 0.0),
                        end_seconds=getattr(segment, "end", 0.0),
                        is_low_confidence=is_low_confidence,
                    )
                )

        return TranscriptionResult(
            text=" ".join(parts).strip(),
            segments=stt_segments,
            language_probability=getattr(info, "language_probability", None),
        )
