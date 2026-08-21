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
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._output_path = "recording.wav"

    def start_recording(self, output_path: str = "recording.wav") -> None:
        """Abre el micrófono en modo streaming, sin bloquear — roadmap Fase 2: el servidor real
        recibe `recording.start`/`recording.stop` como dos comandos WS separados, no puede
        esperar un `input()` de teclado como el modo interactivo de `record()` de arriba.

        No es parte de `MicrophonePort` original (`record()` solo) — se agregó como método
        nuevo del puerto en vez de un cambio de firma, así el prototipo CLI/`VoiceConversation`
        no se ven afectados (ver CONTRIBUTING.md regla 6, no romper en cascada).
        """

        self._frames = []
        self._output_path = output_path

        def callback(indata, frames_count, time_info, status):
            if status:
                print(status)

            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()

    def stop_recording(self) -> str:
        """Cierra la captura abierta por `start_recording` y guarda el WAV. Compañero de
        `start_recording` para el servidor real — ver docstring de arriba."""

        if self._stream is None:
            raise RuntimeError("stop_recording() called without a prior start_recording()")

        self._stream.stop()
        self._stream.close()
        self._stream = None

        if not self._frames:
            raise RuntimeError("No audio was recorded.")

        audio = np.concatenate(self._frames).reshape(-1)
        return self._save(audio, self._output_path)

    def is_available(self) -> bool:
        """Chequeo de mic previo a `call.start` (roadmap Fase 2: estado "conectando/chequeo de
        mic" antes de iniciar la llamada) — no abre el stream, solo confirma que existe al
        menos un dispositivo de entrada."""

        try:
            devices = sd.query_devices()
        except Exception:
            return False

        return any(device.get("max_input_channels", 0) > 0 for device in devices)

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

        print("Listening... Press ENTER when finished.")

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

        # Sin emoji a propósito (encontrado en una sesión de pruebas reales): la consola de
        # Windows en su codepage por default (cp1252) no puede codificar U+1F4BE y este print
        # tumbaba `stop_recording()` con UnicodeEncodeError — el servidor lo capturaba como
        # "No speech was detected", enmascarando el crash real como si fuera un problema de voz
        # del supervisor. Mismo bug que ya se corrigió en `server_main.py::build_uvicorn_kwargs`.
        print(f"Audio saved to: {output_path}")

        return output_path