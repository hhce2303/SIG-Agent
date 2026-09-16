"""Unit tests de `SQLiteScenarioDraftStore` (ADR-0014) — mismo patrón que `test_incidents.py`:
SQLite real contra un archivo temporal, se prueba el contrato de `ScenarioDraftStorePort`.
"""

from core.ports import CriticalDataPoint, ScenarioDraft
from persistence.sqlite_scenario_draft_store import SQLiteScenarioDraftStore


def _draft(**overrides) -> ScenarioDraft:
    fields = dict(
        id="",
        incident_id="incident-1",
        status="pending",
        title="Vehicle Theft — Real Incident",
        category="Vehicle Theft",
        difficulty="Medium",
        language="English",
        description="Drafted from a real incident post-mortem.",
        briefing="A caller reports a stolen vehicle from the dealership lot.",
        critical_data_points=[
            CriticalDataPoint(key="vehicle_description", label="Vehicle description", match_hints=["camry"]),
        ],
        missing_information=["exact time of theft was not in the notes"],
    )
    fields.update(overrides)
    return ScenarioDraft(**fields)


def test_create_assigns_an_id_and_timestamps(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"), clock=lambda: 42.0)
    draft = _draft()

    store.create(draft)

    assert draft.id
    assert draft.created_at == 42.0
    assert draft.updated_at == 42.0


def test_get_returns_none_for_unknown_id(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    assert store.get("does-not-exist") is None


def test_get_round_trips_critical_data_points_and_missing_information(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft()
    store.create(draft)

    reloaded = store.get(draft.id)

    assert reloaded.critical_data_points == draft.critical_data_points
    assert reloaded.missing_information == draft.missing_information
    assert reloaded.status == "pending"


def test_get_pending_for_incident_ignores_non_pending_drafts(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft(incident_id="incident-9")
    store.create(draft)

    assert store.get_pending_for_incident("incident-9").id == draft.id

    store.mark_rejected(draft.id)

    assert store.get_pending_for_incident("incident-9") is None


def test_list_orders_newest_first(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    older = _draft(incident_id="incident-1")
    store.create(older)
    newer = _draft(incident_id="incident-2")
    store.create(newer)

    assert [d.id for d in store.list()] == [newer.id, older.id]


def test_update_persists_edited_fields(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"), clock=lambda: 99.0)
    draft = _draft()
    store.create(draft)

    draft.title = "Edited title"
    draft.critical_data_points = [
        CriticalDataPoint(key="location", label="Location", match_hints=["5th avenue"]),
    ]
    store.update(draft)

    reloaded = store.get(draft.id)
    assert reloaded.title == "Edited title"
    assert reloaded.critical_data_points[0].key == "location"
    assert reloaded.updated_at == 99.0


def test_mark_approved_sets_status_and_scenario_id(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft()
    store.create(draft)

    store.mark_approved(draft.id, "scenario-abc")

    reloaded = store.get(draft.id)
    assert reloaded.status == "approved"
    assert reloaded.approved_scenario_id == "scenario-abc"


def test_mark_rejected_sets_status(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft()
    store.create(draft)

    store.mark_rejected(draft.id)

    assert store.get(draft.id).status == "rejected"
