"""Unit tests de `KokoroTTS`, con el pipeline de Kokoro y la salida de audio mockeados (NFR-10).

No sintetiza audio real ni reproduce nada por parlantes — `KPipeline` y `sounddevice.play/wait`
se reemplazan por stubs.
"""

import os
from unittest.mock import patch

import numpy as np

from tts.kokoro import KokoroTTS


def _make_tts(chunks):
    with patch("tts.kokoro.KPipeline"):
        tts = KokoroTTS(voice="af_heart")
        tts.pipeline = lambda text, voice: iter(chunks)

    return tts


def test_speak_plays_each_audio_chunk_from_the_generator():
    chunks = [
        (None, None, np.zeros(10, dtype="float32")),
        (None, None, np.ones(10, dtype="float32")),
    ]
    tts = _make_tts(chunks)

    with (
        patch("tts.kokoro.sd.play") as mock_play,
        patch("tts.kokoro.sd.wait") as mock_wait,
    ):
        tts.speak("Copy that, please repeat the plate number.")

    assert mock_play.call_count == len(chunks)
    assert mock_wait.call_count == len(chunks)


def test_speak_with_empty_generator_plays_nothing():
    tts = _make_tts([])

    with (
        patch("tts.kokoro.sd.play") as mock_play,
        patch("tts.kokoro.sd.wait") as mock_wait,
    ):
        tts.speak("")

    mock_play.assert_not_called()
    mock_wait.assert_not_called()


def test_model_dir_builds_a_local_kmodel_instead_of_downloading():
    """docs/designs/empaquetado-ejecutable-backend.md, Premisa 3: cuando se pasa `model_dir`, se
    construye un `KModel` local con `config`/`model` en vez de dejar que `KPipeline` dispare
    `hf_hub_download`."""

    with (
        patch("tts.kokoro.KModel") as MockKModel,
        patch("tts.kokoro.KPipeline") as MockKPipeline,
    ):
        MockKModel.MODEL_NAMES = {"hexgrad/Kokoro-82M": "kokoro-v1_0.pth"}

        KokoroTTS(voice="am_michael", model_dir="/models/kokoro")

        MockKModel.assert_called_once_with(
            repo_id="hexgrad/Kokoro-82M",
            config=os.path.join("/models/kokoro", "config.json"),
            model=os.path.join("/models/kokoro", "kokoro-v1_0.pth"),
        )
        _, kwargs = MockKPipeline.call_args
        assert kwargs["model"] == MockKModel.return_value


def test_speak_resolves_voice_to_local_pt_path_when_model_dir_is_set():
    """Sin esto, `speak()` le pasaría el voice id crudo (ej. `"am_michael"`) a
    `load_single_voice()`, que dispara `hf_hub_download` salvo que el string termine en `.pt` —
    ver `kokoro/pipeline.py`."""

    with (
        patch("tts.kokoro.KModel") as MockKModel,
        patch("tts.kokoro.KPipeline"),
    ):
        MockKModel.MODEL_NAMES = {"hexgrad/Kokoro-82M": "kokoro-v1_0.pth"}
        tts = KokoroTTS(voice="am_michael", model_dir="/models/kokoro")
        tts.pipeline = lambda text, voice: iter([])

        calls = []
        tts.pipeline = lambda text, voice: calls.append(voice) or iter([])

        tts.speak("test")

    assert calls == [os.path.join("/models/kokoro", "voices", "am_michael.pt")]


def test_speak_passes_voice_id_unchanged_when_no_model_dir():
    """Sin `model_dir`, el comportamiento es el actual sin cambios -- se le pasa el voice id
    crudo a `KPipeline`, que lo resuelve vía descarga de HuggingFace."""

    with patch("tts.kokoro.KPipeline"):
        tts = KokoroTTS(voice="af_heart")

    calls = []
    tts.pipeline = lambda text, voice: calls.append(voice) or iter([])

    tts.speak("test")

    assert calls == ["af_heart"]
