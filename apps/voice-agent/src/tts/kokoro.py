import sounddevice as sd
import numpy as np

from kokoro import KPipeline

from core.ports import TextToSpeechPort


class KokoroTTS(TextToSpeechPort):
    def __init__(
        self,
        voice: str = "am_michael",
        lang_code: str = "a",
        sample_rate: int = 24000,
    ):
        self.pipeline = KPipeline(
            lang_code=lang_code,
            repo_id="hexgrad/Kokoro-82M",
        )
        self.voice = voice
        self.sample_rate = sample_rate

    def speak(self, text: str, voice: str | None = None) -> None:
        """`voice` (roadmap Fase 2, Ajustes) sobreescribe la voz por defecto para esta síntesis
        puntual sin reconstruir el pipeline — Kokoro selecciona la voz por llamada, no al cargar
        el modelo, así que cambiar de voz entre sesiones no tiene costo de recarga."""

        generator = self.pipeline(
            text,
            voice=voice or self.voice,
        )

        for _, _, audio in generator:
            audio = np.asarray(audio, dtype=np.float32)

            sd.play(audio, self.sample_rate)
            sd.wait()
