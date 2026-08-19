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


def test_transcribe_unclear_vin_fixture_passes_through_low_confidence_text():
    """Fixture de 'VIN poco claro' (roadmap Fase 1, NFR-09).

    Un VIN mal pronunciado o cortado por ruido de fondo puede transcribirse de forma incorrecta
    con baja confianza (`avg_logprob` bajo). `WhisperSTT.transcribe` hoy solo concatena el texto
    de los segmentos y NO expone esa confianza al llamador — este test documenta ese
    comportamiento actual (no lo esconde) para que sirva de regresión cuando NFR-09
    ("Confirmación de datos críticos") se implemente en Fase 1: ese trabajo probablemente cambia
    la firma de `transcribe()` para devolver confianza por segmento, y este test debe
    actualizarse en ese momento, no seguir mockeado contra una firma vieja.
    """

    unclear_vin_segment = _segment(
        " one H G C M eight two six three three, I think",
        avg_logprob=-1.8,  # confianza baja — faster-whisper típicamente reporta esto por debajo de -1.0
    )

    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([unclear_vin_segment], SimpleNamespace())

        stt = WhisperSTT()
        text = stt.transcribe("unclear_vin.wav")

    assert text == "one H G C M eight two six three three, I think"
    # NOTA: sin NFR-09 implementado, este texto de baja confianza llegaría a Claude y al score
    # final como si fuera un dato correcto — ver docs/architecture/PHASE1-PROGRESS.md.


def test_transcribe_configures_english_language_and_vad_filter():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([], SimpleNamespace())

        stt = WhisperSTT()
        stt.transcribe("recording.wav")

        _, kwargs = instance.transcribe.call_args
        assert kwargs["language"] == "en"  # NFR-12: entrenamiento en inglés
        assert kwargs["vad_filter"] is True
