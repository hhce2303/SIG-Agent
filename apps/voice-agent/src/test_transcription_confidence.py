"""Unit tests de `core/transcription_confidence.py` (T2/T4, docs/designs/motor-de-metricas.md).

Dominio puro — `SttSegment` se construye a mano, sin faster-whisper real (mismo patrón que
`test_stt.py`, que sí mockea la librería porque vive en la capa de adaptador).
"""

from core.ports import SttSegment
from core.transcription_confidence import aggregate_transcription_confidence, rate_transcription_confidence


def _segment(text: str, avg_logprob: float = -0.2, is_low_confidence: bool = False) -> SttSegment:
    return SttSegment(
        text=text,
        avg_logprob=avg_logprob,
        no_speech_prob=0.05,
        compression_ratio=1.0,
        start_seconds=0.0,
        end_seconds=1.0,
        is_low_confidence=is_low_confidence,
    )


def test_no_segments_returns_none():
    assert aggregate_transcription_confidence([]) is None


def test_only_empty_text_segments_returns_none():
    assert aggregate_transcription_confidence([_segment("   ")]) is None


def test_aggregate_averages_logprob_and_counts_low_confidence():
    segments = [
        _segment("A white Camry", avg_logprob=-0.1),
        _segment("was stolen", avg_logprob=-0.3, is_low_confidence=True),
    ]

    result = aggregate_transcription_confidence(segments)

    assert result.segment_count == 2
    assert result.low_confidence_segment_count == 1
    assert result.low_confidence_ratio == 0.5
    assert round(result.average_logprob, 2) == -0.2


def test_rate_none_when_no_confidence_data():
    assert rate_transcription_confidence(None) is None


def test_rate_good_when_clear_throughout():
    segments = [_segment("clear speech", avg_logprob=-0.1) for _ in range(5)]
    rating = rate_transcription_confidence(aggregate_transcription_confidence(segments))

    assert rating["rating"] == "good"


def test_rate_critical_when_most_segments_are_low_confidence():
    segments = [
        _segment("clear", avg_logprob=-0.1, is_low_confidence=False),
        _segment("unclear one", avg_logprob=-1.5, is_low_confidence=True),
        _segment("unclear two", avg_logprob=-1.5, is_low_confidence=True),
    ]
    rating = rate_transcription_confidence(aggregate_transcription_confidence(segments))

    assert rating["rating"] == "critical"
    assert rating["low_confidence_segment_count"] == 2


def test_rate_improve_for_a_mixed_but_not_critical_call():
    segments = [
        _segment("clear one", avg_logprob=-0.1),
        _segment("clear two", avg_logprob=-0.2),
        _segment("clear three", avg_logprob=-0.2),
        _segment("one unclear bit", avg_logprob=-1.5, is_low_confidence=True),
    ]
    rating = rate_transcription_confidence(aggregate_transcription_confidence(segments))

    assert rating["rating"] == "improve"
