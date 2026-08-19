from faster_whisper import WhisperModel

from core.ports import SpeechToTextPort


class WhisperSTT(SpeechToTextPort):
    """Adaptador de STT (ver ADR-0006) — implementa `SpeechToTextPort`.

    NFR-09: los segmentos de baja confianza (`avg_logprob` por debajo de
    `LOW_CONFIDENCE_THRESHOLD`) se marcan inline como `[unclear: ...]` en el texto devuelto, en
    vez de cambiar la firma de `transcribe()` a algo como `(texto, confianza_por_segmento)` —
    eso hubiera obligado a tocar `SpeechToTextPort`, `VoiceConversation`, y todos los stubs de
    test que ya lo implementan (ver CONTRIBUTING.md regla 6, confirmar alcance antes de cambios
    en cascada). El marcador viaja tal cual hasta el dispatcher, cuyo system prompt (ver
    `llm/claude.py`) sabe pedirle al caller que repita/deletree un dato crítico marcado así —
    ahí vive la "confirmación explícita" que pide el roadmap, no en código Python que adivine
    qué es una placa o un VIN.
    """

    LOW_CONFIDENCE_THRESHOLD = -1.0

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

    def transcribe(self, audio_path: str) -> str:

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

        for segment in segments:
            text = segment.text.strip()

            if text and segment.avg_logprob < self.LOW_CONFIDENCE_THRESHOLD:
                text = f"[unclear: {text}]"

            parts.append(text)

        return " ".join(parts).strip()