import os

import sounddevice as sd
import numpy as np

from kokoro import KModel, KPipeline

from core.ports import TextToSpeechPort


class KokoroTTS(TextToSpeechPort):
    def __init__(
        self,
        voice: str = "am_michael",
        lang_code: str = "a",
        sample_rate: int = 24000,
        model_dir: str | None = None,
    ):
        """`model_dir` (docs/designs/empaquetado-ejecutable-backend.md, Premisa 3): directorio
        local con `config.json` + el `.pth` del modelo base (nombre según
        `KModel.MODEL_NAMES[repo_id]`) en la raíz, y `voices/<voice>.pt` por cada voz —
        producido por `scripts/fetch_models.py`. Si se pasa, se construye un `KModel` local (sin
        llamar a `hf_hub_download`) y las voces se resuelven a su ruta `.pt` local en vez de
        pasarle el id crudo a `load_single_voice()` (que también dispara una descarga de HF si
        el string no termina en `.pt` — ver `kokoro/pipeline.py`). Si no se pasa, cae al
        comportamiento actual (descarga de HuggingFace) — usado por el prototipo CLI
        (`main.py`) y en desarrollo local con internet.

        `voice` **conserva su significado actual** (un voice id corto, ej. `am_michael`) tanto
        en modo local como en modo descarga — nunca una ruta `.pt` cruda; ese mapeo lo hace
        `_resolve_voice()` internamente.
        """
        self._model_dir = model_dir

        if model_dir:
            repo_id = "hexgrad/Kokoro-82M"
            config_path = os.path.join(model_dir, "config.json")
            model_path = os.path.join(model_dir, KModel.MODEL_NAMES[repo_id])
            kmodel = KModel(repo_id=repo_id, config=config_path, model=model_path)
            self.pipeline = KPipeline(lang_code=lang_code, model=kmodel)
        else:
            self.pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")

        self.voice = voice
        self.sample_rate = sample_rate

    def _resolve_voice(self, voice_id: str) -> str:
        """Mapea un voice id corto (ej. `am_michael`) a lo que espera `KPipeline.__call__`. En
        modo local: la ruta `.pt` bajo `<model_dir>/voices/` — `load_single_voice()` usa esa
        ruta tal cual (`voice.endswith('.pt')`) sin llamar a `hf_hub_download`. En modo
        descarga: el id tal cual, comportamiento actual sin cambios."""
        if self._model_dir:
            return os.path.join(self._model_dir, "voices", f"{voice_id}.pt")
        return voice_id

    def speak(self, text: str, voice: str | None = None) -> None:
        """`voice` (roadmap Fase 2, Ajustes) sobreescribe la voz por defecto para esta síntesis
        puntual sin reconstruir el pipeline — Kokoro selecciona la voz por llamada, no al cargar
        el modelo, así que cambiar de voz entre sesiones no tiene costo de recarga."""

        generator = self.pipeline(
            text,
            voice=self._resolve_voice(voice or self.voice),
        )

        for _, _, audio in generator:
            audio = np.asarray(audio, dtype=np.float32)

            sd.play(audio, self.sample_rate)
            sd.wait()
