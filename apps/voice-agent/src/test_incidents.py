"""Unit tests de `SQLiteIncidentStore` (roadmap Fase 3) — mismo patrón que `test_scenarios.py`:
SQLite real contra un archivo temporal, se prueba el contrato de `IncidentOutcomePort`.
"""

from core.ports import IncidentOutcome
from persistence.sqlite_incident_store import SQLiteIncidentStore


def _incident(**overrides) -> IncidentOutcome:
    fields = dict(
        id="",
        occurred_at=100.0,
        supervisor_id="sup-1",
        category="Vehicle Theft",
        outcome_rating=4,
        critical_data_captured=True,
        protocol_followed=True,
        notes="Went well overall.",
        reported_by="manager-1",
    )
    fields.update(overrides)
    return IncidentOutcome(**fields)


def test_create_assigns_an_id_and_created_at(tmp_path):
    store = SQLiteIncidentStore(str(tmp_path / "incidents.db"), clock=lambda: 42.0)
    incident = _incident()

    store.create(incident)

    assert incident.id
    assert incident.created_at == 42.0


def test_list_orders_newest_incident_first(tmp_path):
    store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))
    older = _incident(occurred_at=100.0)
    newer = _incident(occurred_at=200.0)
    store.create(older)
    store.create(newer)

    assert [i.id for i in store.list()] == [newer.id, older.id]


def test_get_returns_none_for_unknown_id(tmp_path):
    store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))
    assert store.get("does-not-exist") is None


def test_delete_removes_the_incident(tmp_path):
    store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))
    incident = _incident()
    store.create(incident)

    store.delete(incident.id)

    assert store.list() == []


def test_mark_promoted_records_the_scenario_id(tmp_path):
    store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))
    incident = _incident()
    store.create(incident)

    store.mark_promoted(incident.id, "scenario-abc")

    assert store.get(incident.id).promoted_scenario_id == "scenario-abc"


def test_boolean_fields_round_trip_through_sqlite(tmp_path):
    # SQLite no tiene un tipo BOOLEAN nativo — se guarda como INTEGER 0/1, esto confirma que la
    # conversión de ida y vuelta preserva `bool`, no un `int` truthy.
    store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))
    incident = _incident(critical_data_captured=False, protocol_followed=True)
    store.create(incident)

    reloaded = store.get(incident.id)
    assert reloaded.critical_data_captured is False
    assert reloaded.protocol_followed is True
