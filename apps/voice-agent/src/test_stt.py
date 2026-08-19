"""Unit tests de `WhisperSTT`, con el modelo de faster-whisper mockeado (NFR-10).

No cargan ningún modelo real ni tocan audio de disco — `WhisperModel.transcribe()` se reemplaza
por un stub que devuelve segmentos fabricados.
"""

from types import SimpleNamespace
from unittest.mock import patch

from stt.whisper import WhisperSTT


def _segment(text: str, avg_logprob: float = -0.2):
    return SimpleNamespace(text=text, avg_logprob=avg_logprob)


def test_transcribe_joins_segments_into_one_string():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = (
            [_segment(" There's a"), _segment(" white Camry ")],
            SimpleNamespace(),
        )

        stt = WhisperSTT()
        text = stt.transcribe("recording.wav")

    assert text == "There's a white Camry"


def test_transcribe_returns_empty_string_when_no_speech_detected():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([], SimpleNamespace())

        stt = WhisperSTT()
        text = stt.transcribe("silence.wav")

    assert text == ""


def test_transcribe_unclear_vin_fixture_marks_low_confidence_segment():
    """Fixture de 'VIN poco claro' (roadmap Fase 1, NFR-09).

    Un VIN mal pronunciado o cortado por ruido de fondo puede transcribirse de forma incorrecta
    con baja confianza (`avg_logprob` bajo). `WhisperSTT.transcribe` marca ese segmento inline
    como `[unclear: ...]` — el system prompt del dispatcher (`llm/claude.py`) sabe pedir
    confirmación explícita cuando ve ese marcador en un dato crítico, en vez de aceptarlo como
    correcto en silencio.
    """

    unclear_vin_segment = _segment(
        " one H G C M eight two six three three, I think",
        avg_logprob=-1.8,  # confianza baja — por debajo de WhisperSTT.LOW_CONFIDENCE_THRESHOLD
    )

    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([unclear_vin_segment], SimpleNamespace())

        stt = WhisperSTT()
        text = stt.transcribe("unclear_vin.wav")

    assert text == "[unclear: one H G C M eight two six three three, I think]"


def test_transcribe_does_not_mark_high_confidence_segments():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = (
            [_segment("A white Camry was stolen.", avg_logprob=-0.1)],
            SimpleNamespace(),
        )

        stt = WhisperSTT()
        text = stt.transcribe("clear.wav")

    assert text == "A white Camry was stolen."
    assert "[unclear:" not in text


def test_transcribe_marks_only_the_low_confidence_segment_in_a_mixed_sentence():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = (
            [
                _segment("License plate is", avg_logprob=-0.2),
                _segment("A B C one two three", avg_logprob=-1.5),
            ],
            SimpleNamespace(),
        )

        stt = WhisperSTT()
        text = stt.transcribe("mixed.wav")

    assert text == "License plate is [unclear: A B C one two three]"


def test_transcribe_configures_english_language_and_vad_filter():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([], SimpleNamespace())

        stt = WhisperSTT()
        stt.transcribe("recording.wav")

        _, kwargs = instance.transcribe.call_args
        assert kwargs["language"] == "en"  # NFR-12: entrenamiento en inglés
        assert kwargs["vad_filter"] is True
