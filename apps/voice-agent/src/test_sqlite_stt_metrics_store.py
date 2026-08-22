"""Unit tests de `SQLiteSttMetricsStore` (T4, docs/designs/motor-de-metricas.md) — mismo patrón
que el resto de los stores de este repo: `tmp_path` privado, sin mocks de SQLite."""

from core.ports import SttSegment
from persistence.sqlite_stt_metrics_store import SQLiteSttMetricsStore


def _segment(text: str, is_low_confidence: bool = False) -> SttSegment:
    return SttSegment(
        text=text,
        avg_logprob=-0.2,
        no_speech_prob=0.05,
        compression_ratio=1.0,
        start_seconds=0.0,
        end_seconds=1.5,
        is_low_confidence=is_low_confidence,
    )


def test_get_segments_returns_empty_list_for_unknown_session(tmp_path):
    store = SQLiteSttMetricsStore(str(tmp_path / "sessions.db"))

    assert store.get_segments("unknown-session") == []


def test_save_and_get_segments_round_trip_preserves_order_and_fields(tmp_path):
    store = SQLiteSttMetricsStore(str(tmp_path / "sessions.db"))
    segments = [_segment("first"), _segment("second", is_low_confidence=True)]

    store.save_segments("sess-1", segments)
    result = store.get_segments("sess-1")

    assert [s.text for s in result] == ["first", "second"]
    assert result[1].is_low_confidence is True
    assert result[0].avg_logprob == -0.2


def test_save_segments_is_a_no_op_for_an_empty_list(tmp_path):
    store = SQLiteSttMetricsStore(str(tmp_path / "sessions.db"))

    store.save_segments("sess-1", [])

    assert store.get_segments("sess-1") == []


def test_segments_are_scoped_per_session(tmp_path):
    store = SQLiteSttMetricsStore(str(tmp_path / "sessions.db"))

    store.save_segments("sess-1", [_segment("belongs to session 1")])
    store.save_segments("sess-2", [_segment("belongs to session 2")])

    assert [s.text for s in store.get_segments("sess-1")] == ["belongs to session 1"]
    assert [s.text for s in store.get_segments("sess-2")] == ["belongs to session 2"]


def test_creating_the_store_twice_against_the_same_file_does_not_fail(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` debe ser un no-op contra una tabla ya existente — mismo
    contrato que el resto de los stores (TODO-20)."""

    db_path = str(tmp_path / "sessions.db")
    SQLiteSttMetricsStore(db_path)
    store = SQLiteSttMetricsStore(db_path)  # no debe lanzar

    store.save_segments("sess-1", [_segment("still works")])
    assert len(store.get_segments("sess-1")) == 1
