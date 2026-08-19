"""Unit tests de `KokoroTTS`, con el pipeline de Kokoro y la salida de audio mockeados (NFR-10).

No sintetiza audio real ni reproduce nada por parlantes — `KPipeline` y `sounddevice.play/wait`
se reemplazan por stubs.
"""

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
