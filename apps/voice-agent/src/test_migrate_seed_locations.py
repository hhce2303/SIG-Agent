"""Tests de `migrate_seed_locations.py` — docs/designs/ubicacion-del-incidente.md, Fase 3
Sección 2 punto 6. Verifica que la migración retire el `CriticalDataPoint` ad-hoc EN EL MISMO paso
que agrega `ScenarioLocation` (nunca un estado intermedio con las dos cosas, hallazgo H2/M1), y
que sea idempotente (correrla dos veces no duplica ni rompe nada).
"""

from migrate_seed_locations import migrate
from persistence.sqlite_scenario_location_store import SQLiteScenarioLocationStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore


def test_migrates_all_three_seed_scenarios(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    SQLiteScenarioStore(db_path)  # siembra los 3 escenarios (tabla vacía al crearla)

    migrated = migrate(db_path)

    assert set(migrated) == {"vehicle_theft", "domestic_dispute", "traffic_accident"}


def test_removes_the_ad_hoc_point_and_adds_a_scenario_location(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    scenario_store = SQLiteScenarioStore(db_path)
    location_store = SQLiteScenarioLocationStore(db_path)

    migrate(db_path)

    scenario = scenario_store.get("vehicle_theft")
    assert not any(p.key == "last_location" for p in scenario.critical_data_points)
    location = location_store.get("vehicle_theft")
    assert location is not None
    assert location.landmark == "Shopping center parking lot"


def test_never_leaves_double_counting_intermediate_state(tmp_path):
    # H2/M1 — el punto ad-hoc y el ScenarioLocation nunca deben coexistir tras la migración.
    db_path = str(tmp_path / "sessions.db")
    scenario_store = SQLiteScenarioStore(db_path)
    location_store = SQLiteScenarioLocationStore(db_path)

    migrate(db_path)

    for scenario_id, old_key in (
        ("vehicle_theft", "last_location"),
        ("domestic_dispute", "address"),
        ("traffic_accident", "location"),
    ):
        scenario = scenario_store.get(scenario_id)
        has_old_point = any(p.key == old_key for p in scenario.critical_data_points)
        has_location = location_store.get(scenario_id) is not None
        assert not (has_old_point and has_location), f"{scenario_id} double-counts its location fact"
        assert has_location, f"{scenario_id} should have a ScenarioLocation after migration"


def test_dry_run_reports_without_writing_anything(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    scenario_store = SQLiteScenarioStore(db_path)
    location_store = SQLiteScenarioLocationStore(db_path)

    migrated = migrate(db_path, dry_run=True)

    assert set(migrated) == {"vehicle_theft", "domestic_dispute", "traffic_accident"}
    assert location_store.get("vehicle_theft") is None
    assert any(p.key == "last_location" for p in scenario_store.get("vehicle_theft").critical_data_points)


def test_running_twice_is_idempotent(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    SQLiteScenarioStore(db_path)

    migrate(db_path)
    second_run = migrate(db_path)

    # Nada que migrar en la segunda corrida — ya no hay punto ad-hoc y ya existe la ubicación.
    assert second_run == []
