"""Unit tests de `MicrophoneRecorder`, con I/O de audio mockeado (NFR-10).

El bug original de este archivo (llamar a `record(duration=5, ...)` cuando `record()` no
aceptaba `duration`) quedó corregido agregando el parámetro a `MicrophoneRecorder.record` — ver
`audio/microphone.py`. Estos tests cubren ambos modos (duración fija y push-to-talk
interactivo) sin tocar hardware real.
"""

from unittest.mock import patch

import numpy as np
import pytest

from audio.microphone import MicrophoneRecorder


@pytest.fixture
def recorder():
    return MicrophoneRecorder(sample_rate=16000, channels=1)


def test_record_with_duration_does_not_prompt_for_input(recorder, tmp_path):
    fake_audio = np.zeros((16000 * 2, 1), dtype="float32")
    output_path = str(tmp_path / "out.wav")

    with (
        patch("audio.microphone.sd.rec", return_value=fake_audio) as mock_rec,
        patch("audio.microphone.sd.wait") as mock_wait,
        patch("audio.microphone.sf.write") as mock_write,
        patch("builtins.input") as mock_input,
    ):
        result = recorder.record(output_path=output_path, duration=2)

        mock_input.assert_not_called()
        mock_rec.assert_called_once_with(
            16000 * 2,
            samplerate=16000,
            channels=1,
            dtype="float32",
        )
        mock_wait.assert_called_once()
        mock_write.assert_called_once()

    assert result == output_path


def test_record_interactive_saves_captured_frames(recorder, tmp_path):
    captured_callback = {}

    class FakeInputStream:
        def __init__(self, *, samplerate, channels, dtype, callback):
            captured_callback["fn"] = callback

        def __enter__(self):
            # Simula un frame de audio llegando mientras el stream está abierto.
            captured_callback["fn"](
                np.ones((10, 1), dtype="float32"), 10, None, None
            )
            return self

        def __exit__(self, *args):
            return False

    output_path = str(tmp_path / "out.wav")

    with (
        patch("audio.microphone.sd.InputStream", FakeInputStream),
        patch("builtins.input"),
        patch("audio.microphone.sf.write") as mock_write,
    ):
        result = recorder.record(output_path=output_path)

        mock_write.assert_called_once()

    assert result == output_path


def test_record_interactive_raises_when_nothing_captured(recorder, tmp_path):
    class EmptyInputStream:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with (
        patch("audio.microphone.sd.InputStream", EmptyInputStream),
        patch("builtins.input"),
    ):
        with pytest.raises(RuntimeError, match="No audio was recorded"):
            recorder.record(output_path=str(tmp_path / "out.wav"))
