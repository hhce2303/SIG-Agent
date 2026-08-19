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


def test_round_trips_fase2_fields(tmp_path):
    """Fase 2: transcript real, evaluación y outcome — no solo transiciones de turno."""
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    session = SessionRecord(
        session_id="sess-1",
        supervisor_id="sup-42",
        scenario_name="Vehicle Theft",
        scenario_id="vehicle_theft",
        started_at=1000.0,
        ended_at=1090.0,
        transcript=[{"role": "operator", "text": "My car was stolen.", "at": 1005.0, "seconds": 5}],
        evaluation={"overall_score": 82, "category_scores": {}, "collected": [], "missing": [], "strengths": [], "improvements": [], "summary": "Good call."},
        outcome="ended",
        difficulty="Medium",
        language="English",
        training_type="Police",
    )

    store.save_session(session)
    loaded = store.get_session("sess-1")

    assert loaded == session


def test_network_drop_sessions_have_no_evaluation(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    store.save_session(
        SessionRecord(
            session_id="sess-1",
            supervisor_id="sup-42",
            scenario_name="Vehicle Theft",
            started_at=1000.0,
            ended_at=1010.0,
            outcome="network_drop",
            evaluation=None,
        )
    )

    loaded = store.get_session("sess-1")
    assert loaded.outcome == "network_drop"
    assert loaded.evaluation is None


def test_list_sessions_scopes_by_supervisor_and_orders_newest_first(tmp_path):
    """Visibilidad self-only (roadmap Fase 2/NFR-06) — nunca se filtra por lo que provee el
    cliente, siempre por el `supervisor_id` del token verificado."""
    store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    store.save_session(SessionRecord(session_id="a1", supervisor_id="alice", scenario_name="x", started_at=1000.0))
    store.save_session(SessionRecord(session_id="a2", supervisor_id="alice", scenario_name="x", started_at=2000.0))
    store.save_session(SessionRecord(session_id="b1", supervisor_id="bob", scenario_name="x", started_at=1500.0))

    alice_sessions = store.list_sessions("alice")

    assert [s.session_id for s in alice_sessions] == ["a2", "a1"]
    assert store.list_sessions("bob") and store.list_sessions("bob")[0].session_id == "b1"
    assert store.list_sessions("nobody") == []
