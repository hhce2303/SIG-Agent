import numpy as np
import sounddevice as sd
import soundfile as sf

from core.ports import MicrophonePort


class MicrophoneRecorder(MicrophonePort):

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        self.sample_rate = sample_rate
        self.channels = channels

    def record(
        self,
        output_path: str = "recording.wav",
        duration: float | None = None,
    ) -> str:
        """Graba audio del micrófono y lo guarda en `output_path`.

        Sin `duration`: modo interactivo (push-to-talk del prototipo CLI) — Enter para empezar,
        Enter de nuevo para terminar.

        Con `duration`: captura no interactiva de exactamente `duration` segundos, sin esperar
        input de teclado. Existe para poder probar esta clase con I/O mockeado (ver
        `test_microphone.py`) y como punto de partida hacia una captura por VAD en Fase 1 — hoy
        sigue siendo de duración fija, no detección de voz.
        """

        if duration is not None:
            audio = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
            )
            sd.wait()

            return self._save(audio.reshape(-1), output_path)

        input("Press ENTER to start speaking...")

        print("🎤 Listening... Press ENTER when finished.")

        frames = []

        def callback(indata, frames_count, time, status):
            if status:
                print(status)

            frames.append(indata.copy())

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback,
        ):
            input()

        if not frames:
            raise RuntimeError("No audio was recorded.")

        audio = b"".join(
            frame.tobytes()
            for frame in frames
        )

        audio = np.frombuffer(
            audio,
            dtype=np.float32,
        )

        return self._save(audio, output_path)

    def _save(self, audio: np.ndarray, output_path: str) -> str:
        sf.write(
            output_path,
            audio,
            self.sample_rate,
        )

        print(f"💾 Audio saved to: {output_path}")

        return output_path