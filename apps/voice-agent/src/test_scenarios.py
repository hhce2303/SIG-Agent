"""Unit tests de `SQLiteScenarioStore` (roadmap Fase 2, TODO-11 resuelto) — mismo patrón que
`test_persistence.py`: SQLite real contra un archivo temporal, se prueba el contrato de
`ScenarioPort`.
"""

from core.ports import CriticalDataPoint, Scenario
from persistence.sqlite_scenario_store import SQLiteScenarioStore


def test_seeds_the_three_initial_scenarios_on_first_run(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))

    ids = {scenario.id for scenario in store.list()}
    assert ids == {"vehicle_theft", "domestic_dispute", "traffic_accident"}

    vehicle_theft = store.get("vehicle_theft")
    assert vehicle_theft.briefing  # migró el contenido del SCENARIO string original
    assert any(point.key == "license_plate" for point in vehicle_theft.critical_data_points)


def test_seed_does_not_duplicate_on_a_second_instance_against_the_same_file(tmp_path):
    db_path = str(tmp_path / "scenarios.db")
    SQLiteScenarioStore(db_path)

    reopened = SQLiteScenarioStore(db_path)

    assert len(reopened.list()) == 3


def test_create_get_update_delete_round_trip(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    scenario = Scenario(
        id="",
        title="Burglary in Progress",
        category="Police",
        difficulty="Hard",
        language="English",
        description="An active burglary.",
        briefing="A caller reports someone breaking into their neighbor's house.",
        critical_data_points=[CriticalDataPoint(key="address", label="Address")],
    )

    store.create(scenario)
    assert scenario.id  # se le asignó un id

    fetched = store.get(scenario.id)
    assert fetched.title == "Burglary in Progress"
    assert fetched.critical_data_points == [CriticalDataPoint(key="address", label="Address")]

    fetched.title = "Burglary in Progress — Updated"
    store.update(fetched)
    assert store.get(scenario.id).title == "Burglary in Progress — Updated"

    store.delete(scenario.id)
    assert store.get(scenario.id) is None


def test_match_hints_round_trip_through_the_json_column(tmp_path):
    # TODO-17: match_hints se agregó a CriticalDataPoint después de que la tabla ya existía en
    # producción (Gate 0) — confirma que el round-trip funciona sin ALTER TABLE (ver TODO-20) y
    # que una fila vieja sin la clave `match_hints` en su JSON sigue cargando con el default.
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    scenario = Scenario(
        id="",
        title="Robbery",
        category="Police",
        difficulty="Hard",
        language="English",
        description="An armed robbery.",
        briefing="A caller reports an armed robbery in progress.",
        critical_data_points=[
            CriticalDataPoint(
                key="vehicle", label="Vehicle description", match_hints=["camry", "sedan"]
            ),
        ],
    )

    store.create(scenario)
    fetched = store.get(scenario.id)

    assert fetched.critical_data_points[0].match_hints == ["camry", "sedan"]

    # Fila "vieja" simulada: el seed original (creado antes de este cambio, ver
    # `_seed_scenarios`) ya no tiene match_hints vacío por default en este repo, pero el
    # contrato retrocompatible sí importa para cualquier fila real que exista hoy en
    # producción sin esa clave — probarlo directo contra el JSON, no contra el seed actual.
    vehicle_theft = store.get("vehicle_theft")
    assert isinstance(vehicle_theft.critical_data_points[0].match_hints, list)


def test_get_returns_none_for_an_unknown_id(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))

    assert store.get("does-not-exist") is None


def test_list_is_ordered_by_creation_order(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    ids_before = [scenario.id for scenario in store.list()]

    store.create(Scenario(
        id="", title="New One", category="Police", difficulty="Easy", language="English",
        description="d", briefing="b",
    ))

    ids_after = [scenario.id for scenario in store.list()]
    assert ids_after[:len(ids_before)] == ids_before
    assert ids_after[-1] not in ids_before
