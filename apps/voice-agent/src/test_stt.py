"""Unit tests de `WhisperSTT`, con el modelo de faster-whisper mockeado (NFR-10).

No cargan ningún modelo real ni tocan audio de disco — `WhisperModel.transcribe()` se reemplaza
por un stub que devuelve segmentos fabricados.

T2/T12 (docs/designs/motor-de-metricas.md): `transcribe()` ahora devuelve `TranscriptionResult`
en vez de `str` — estos tests leen `.text` donde antes comparaban el string directo, y agregan
casos nuevos para `.segments`/`.language_probability`.
"""

from types import SimpleNamespace
from unittest.mock import patch

from stt.whisper import WhisperSTT


def _segment(text: str, avg_logprob: float = -0.2, no_speech_prob: float = 0.05, compression_ratio: float = 1.0, start: float = 0.0, end: float = 1.0):
    return SimpleNamespace(
        text=text,
        avg_logprob=avg_logprob,
        no_speech_prob=no_speech_prob,
        compression_ratio=compression_ratio,
        start=start,
        end=end,
    )


def test_transcribe_joins_segments_into_one_string():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = (
            [_segment(" There's a"), _segment(" white Camry ")],
            SimpleNamespace(),
        )

        stt = WhisperSTT()
        result = stt.transcribe("recording.wav")

    assert result.text == "There's a white Camry"


def test_transcribe_returns_empty_string_when_no_speech_detected():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([], SimpleNamespace())

        stt = WhisperSTT()
        result = stt.transcribe("silence.wav")

    assert result.text == ""
    assert result.segments == []


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
        avg_logprob=-1.8,  # confianza baja — por debajo de core.transcription_confidence.LOW_CONFIDENCE_THRESHOLD
    )

    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([unclear_vin_segment], SimpleNamespace())

        stt = WhisperSTT()
        result = stt.transcribe("unclear_vin.wav")

    assert result.text == "[unclear: one H G C M eight two six three three, I think]"
    assert result.segments[0].is_low_confidence is True


def test_transcribe_does_not_mark_high_confidence_segments():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = (
            [_segment("A white Camry was stolen.", avg_logprob=-0.1)],
            SimpleNamespace(),
        )

        stt = WhisperSTT()
        result = stt.transcribe("clear.wav")

    assert result.text == "A white Camry was stolen."
    assert "[unclear:" not in result.text
    assert result.segments[0].is_low_confidence is False


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
        result = stt.transcribe("mixed.wav")

    assert result.text == "License plate is [unclear: A B C one two three]"
    assert len(result.segments) == 2
    assert result.segments[0].is_low_confidence is False
    assert result.segments[1].is_low_confidence is True


def test_transcribe_configures_english_language_and_vad_filter():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([], SimpleNamespace())

        stt = WhisperSTT()
        stt.transcribe("recording.wav")

        _, kwargs = instance.transcribe.call_args
        assert kwargs["language"] == "en"  # NFR-12: entrenamiento en inglés
        assert kwargs["vad_filter"] is True


def test_transcribe_preserves_segment_confidence_fields_previously_discarded():
    """T2 (docs/designs/motor-de-metricas.md): `no_speech_prob`/`compression_ratio`/timestamps
    ya existían en la librería pero se descartaban — ahora se preservan en `.segments`."""

    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = (
            [_segment("A white Camry", avg_logprob=-0.2, no_speech_prob=0.12, compression_ratio=1.4, start=0.5, end=2.1)],
            SimpleNamespace(),
        )

        stt = WhisperSTT()
        result = stt.transcribe("recording.wav")

    segment = result.segments[0]
    assert segment.avg_logprob == -0.2
    assert segment.no_speech_prob == 0.12
    assert segment.compression_ratio == 1.4
    assert segment.start_seconds == 0.5
    assert segment.end_seconds == 2.1


def test_transcribe_preserves_language_probability():
    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([], SimpleNamespace(language_probability=0.97))

        stt = WhisperSTT()
        result = stt.transcribe("recording.wav")

    assert result.language_probability == 0.97


def test_transcribe_missing_confidence_fields_default_instead_of_raising():
    """Un stub mínimo (o una versión vieja de faster-whisper) sin `no_speech_prob`/
    `compression_ratio` no debe romper la transcripción real — son campos de métricas
    secundarios, no el dato principal."""

    minimal_segment = SimpleNamespace(text="A white Camry", avg_logprob=-0.2)

    with patch("stt.whisper.WhisperModel") as MockModel:
        instance = MockModel.return_value
        instance.transcribe.return_value = ([minimal_segment], SimpleNamespace())

        stt = WhisperSTT()
        result = stt.transcribe("recording.wav")

    assert result.text == "A white Camry"
    assert result.segments[0].no_speech_prob == 0.0
    assert result.segments[0].compression_ratio == 0.0
