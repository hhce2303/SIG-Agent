"""Descarga los pesos de Whisper y Kokoro a `models/` para el build empaquetado (PyInstaller).

Ver docs/designs/empaquetado-ejecutable-backend.md, Premisa 4. Correr una vez antes de
`pyinstaller server_main.spec` (o cada vez que cambie `WHISPER_MODEL_SIZE`/`KOKORO_VOICE`) —
`models/` está en `.gitignore`, igual que hoy se regenera `uv sync` para el venv.

Uso:
    uv run python scripts/fetch_models.py

Variables de entorno opcionales (mismos nombres/defaults que `server_main.py` usa en runtime):
- `WHISPER_MODEL_SIZE` (default `small`) — tamaño de modelo de faster-whisper a descargar.
- `KOKORO_VOICE` (default `am_michael`) — qué voz de Kokoro descargar. Deliberadamente NO se
  descarga el catálogo completo de voces (serían decenas de archivos, la mayoría nunca usados
  en este producto) — cambiar de voz más adelante requiere volver a correr este script.

No requiere PyInstaller ni el venv del backend estar "frozen" — es un script de build-time
normal, corre con el mismo intérprete que ya usa `uv run`.
"""

from __future__ import annotations

import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(REPO_ROOT, "models")

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE") or "small"
KOKORO_VOICE = os.getenv("KOKORO_VOICE") or "am_michael"
KOKORO_REPO_ID = "hexgrad/Kokoro-82M"


def fetch_whisper() -> str:
    """faster_whisper.download_model() produce un snapshot completo de CTranslate2 que
    `WhisperModel(local_dir, ...)` acepta directamente — sin transformación adicional (ver
    Premisa 4)."""
    from faster_whisper import download_model

    output_dir = os.path.join(MODELS_DIR, "whisper")
    print(f"Descargando Whisper '{WHISPER_MODEL_SIZE}' -> {output_dir}")
    resolved = download_model(WHISPER_MODEL_SIZE, output_dir=output_dir)
    print(f"OK: {resolved}")
    return resolved


def fetch_kokoro() -> str:
    """Layout esperado (Premisa 4): `config.json` + el `.pth` del modelo base
    (`KModel.MODEL_NAMES[repo_id]`) en la raíz, y `voices/<voice>.pt` para la voz configurada —
    NO el catálogo completo de voces."""
    from huggingface_hub import hf_hub_download
    from kokoro import KModel

    output_dir = os.path.join(MODELS_DIR, "kokoro")
    voices_dir = os.path.join(output_dir, "voices")
    os.makedirs(voices_dir, exist_ok=True)

    model_filename = KModel.MODEL_NAMES[KOKORO_REPO_ID]

    print(f"Descargando Kokoro config.json -> {output_dir}")
    config_src = hf_hub_download(repo_id=KOKORO_REPO_ID, filename="config.json")
    shutil.copy(config_src, os.path.join(output_dir, "config.json"))

    print(f"Descargando Kokoro {model_filename} -> {output_dir}")
    model_src = hf_hub_download(repo_id=KOKORO_REPO_ID, filename=model_filename)
    shutil.copy(model_src, os.path.join(output_dir, model_filename))

    voice_filename = f"{KOKORO_VOICE}.pt"
    print(f"Descargando voz Kokoro '{KOKORO_VOICE}' -> {voices_dir}")
    voice_src = hf_hub_download(repo_id=KOKORO_REPO_ID, filename=f"voices/{voice_filename}")
    shutil.copy(voice_src, os.path.join(voices_dir, voice_filename))

    print(f"OK: {output_dir}")
    return output_dir


def main() -> int:
    os.makedirs(MODELS_DIR, exist_ok=True)
    try:
        fetch_whisper()
        fetch_kokoro()
    except Exception as exc:  # noqa: BLE001 — script de build-time, un fallo debe ser ruidoso y
        # terminar el build ahí mismo, no dejar `models/` a medio descargar y fallar silencioso
        # más tarde en el smoke test offline.
        print(f"ERROR: fetch de modelos falló: {exc}", file=sys.stderr)
        return 1

    print(f"\nListo. Configurar antes del build:\n  WHISPER_MODEL_PATH=whisper\n  KOKORO_MODEL_DIR=kokoro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
