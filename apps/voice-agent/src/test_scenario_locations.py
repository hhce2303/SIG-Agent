"""Unit tests de `SQLiteScenarioLocationStore` (docs/designs/ubicacion-del-incidente.md) — mismo
patrón que `test_scenario_videos.py`: SQLite real contra un archivo temporal.
"""

from core.ports import ScenarioLocation
from persistence.sqlite_scenario_location_store import SQLiteScenarioLocationStore


def _location(scenario_id: str = "robbery_001", **overrides) -> ScenarioLocation:
    defaults = dict(
        scenario_id=scenario_id,
        street="5th Avenue",
        cross_street="Main Street",
        landmark="Westfield Shopping Center",
        city_or_zone="Downtown",
        additional_directions="Behind the parking garage",
        match_hints=["fifth ave"],
        marker_x=0.6,
        marker_y=0.4,
    )
    defaults.update(overrides)
    return ScenarioLocation(**defaults)


def test_get_returns_none_when_the_scenario_has_no_location(tmp_path):
    store = SQLiteScenarioLocationStore(str(tmp_path / "locations.db"))

    assert store.get("does-not-exist") is None


def test_upsert_then_get_round_trips_all_fields(tmp_path):
    store = SQLiteScenarioLocationStore(str(tmp_path / "locations.db"))
    location = _location()

    store.upsert(location)
    fetched = store.get("robbery_001")

    assert fetched.street == "5th Avenue"
    assert fetched.cross_street == "Main Street"
    assert fetched.landmark == "Westfield Shopping Center"
    assert fetched.city_or_zone == "Downtown"
    assert fetched.additional_directions == "Behind the parking garage"
    assert fetched.match_hints == ["fifth ave"]
    assert fetched.marker_x == 0.6
    assert fetched.marker_y == 0.4
    assert fetched.created_at > 0
    assert fetched.updated_at > 0


def test_marker_none_round_trips_as_none_not_default(tmp_path):
    # B10 (design doc): `None` = "sin posicionar", distinto de "posicionado en 0.5/0.5" — el
    # round-trip de SQLite (columna REAL nullable) no debe convertirlo en 0.0 ni en un default.
    store = SQLiteScenarioLocationStore(str(tmp_path / "locations.db"))
    store.upsert(_location(marker_x=None, marker_y=None))

    fetched = store.get("robbery_001")

    assert fetched.marker_x is None
    assert fetched.marker_y is None


def test_upsert_is_a_true_upsert_not_a_duplicate_row(tmp_path):
    store = SQLiteScenarioLocationStore(str(tmp_path / "locations.db"))
    store.upsert(_location())

    store.upsert(_location(street="6th Avenue"))

    fetched = store.get("robbery_001")
    assert fetched.street == "6th Avenue"


def test_delete_removes_the_reference(tmp_path):
    store = SQLiteScenarioLocationStore(str(tmp_path / "locations.db"))
    store.upsert(_location())

    store.delete("robbery_001")

    assert store.get("robbery_001") is None


def test_two_scenarios_can_each_have_their_own_location(tmp_path):
    store = SQLiteScenarioLocationStore(str(tmp_path / "locations.db"))
    store.upsert(_location(scenario_id="robbery_001"))
    store.upsert(_location(scenario_id="robbery_002", street="9th Avenue"))

    assert store.get("robbery_001").street == "5th Avenue"
    assert store.get("robbery_002").street == "9th Avenue"
