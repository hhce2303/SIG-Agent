"""Unit tests de `SQLiteSessionStore` (ADR-0007) contra un archivo temporal real — SQLite es lo
bastante barato para no necesitar mockearlo; lo que se prueba es el contrato de `PersistencePort`.
"""

from core.ports import SessionRecord
from persistence.sqlite_store import SQLiteSessionStore


def test_save_and_get_round_trips_a_session(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    session = SessionRecord(
        session_id="sess-1",
        supervisor_id="sup-42",
        scenario_name="vehicle_theft",
        started_at=1000.0,
        turns=[{"role": "user", "content": "A car was stolen."}],
    )

    store.save_session(session)
    loaded = store.get_session("sess-1")

    assert loaded == session


def test_get_session_returns_none_when_not_found(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))

    assert store.get_session("does-not-exist") is None


def test_save_session_twice_updates_instead_of_duplicating(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    session = SessionRecord(
        session_id="sess-1",
        supervisor_id="sup-42",
        scenario_name="vehicle_theft",
        started_at=1000.0,
        turns=[{"role": "user", "content": "A car was stolen."}],
    )
    store.save_session(session)

    session.ended_at = 1042.0
    session.turns.append({"role": "assistant", "content": "Copy that."})
    store.save_session(session)

    loaded = store.get_session("sess-1")
    assert loaded.ended_at == 1042.0
    assert len(loaded.turns) == 2


def test_store_persists_across_instances_on_the_same_file(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    SQLiteSessionStore(db_path).save_session(
        SessionRecord(
            session_id="sess-1",
            supervisor_id="sup-42",
            scenario_name="vehicle_theft",
            started_at=1000.0,
        )
    )

    reopened = SQLiteSessionStore(db_path)
    assert reopened.get_session("sess-1") is not None
