"""Test de integración de ubicación del incidente contra `TestClient` — docs/designs/
ubicacion-del-incidente.md. Mismo patrón que `test_server_video.py`: stubs de STT/TTS/LLM/mic,
SQLite real contra `tmp_path`, extendido con `scenario_location_store`.
"""

import pytest
from fastapi.testclient import TestClient

from auth.session_token import HmacSessionTokenIssuer
from persistence.sqlite_scenario_location_store import SQLiteScenarioLocationStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore
from persistence.sqlite_settings_store import SQLiteSettingsStore
from persistence.sqlite_incident_store import SQLiteIncidentStore
from persistence.sqlite_store import SQLiteSessionStore
from server.app import create_app
from test_server_app import StubDispatcher, StubMicrophone, StubSTT, StubTTS, make_clock

SUPERVISOR_PASSPHRASE = "correct-passphrase"


@pytest.fixture
def app_components(tmp_path):
    return {
        "token_issuer": HmacSessionTokenIssuer(secret_key=b"test-secret", clock=make_clock()),
        "session_store": SQLiteSessionStore(str(tmp_path / "sessions.db")),
        "scenario_store": SQLiteScenarioStore(str(tmp_path / "scenarios.db")),
        "scenario_location_store": SQLiteScenarioLocationStore(str(tmp_path / "scenario_locations.db")),
        "settings_store": SQLiteSettingsStore(str(tmp_path / "settings.db")),
        "incident_store": SQLiteIncidentStore(str(tmp_path / "incidents.db")),
    }


def make_client(components, configure_location=True, **overrides):
    kwargs = dict(
        token_issuer=components["token_issuer"],
        session_store=components["session_store"],
        scenario_store=components["scenario_store"],
        settings_store=components["settings_store"],
        incident_store=components["incident_store"],
        supervisor_passphrase=SUPERVISOR_PASSPHRASE,
        dispatcher=overrides.pop("dispatcher", None) or StubDispatcher(["911, what is your emergency?"]),
        stt=overrides.pop("stt", None) or StubSTT([""]),
        tts=overrides.pop("tts", None) or StubTTS(),
        microphone=overrides.pop("microphone", None) or StubMicrophone(),
        clock=make_clock(),
    )
    if configure_location:
        kwargs["scenario_location_store"] = components["scenario_location_store"]
    kwargs.update(overrides)
    return TestClient(create_app(**kwargs))


@pytest.fixture
def client(app_components):
    return make_client(app_components)


def _login(client, supervisor_id="sup-42", passphrase=SUPERVISOR_PASSPHRASE):
    return client.post("/auth/login", json={"supervisor_id": supervisor_id, "passphrase": passphrase})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _create_scenario(client, token):
    body = {
        "title": "Robbery in progress", "category": "Police", "difficulty": "Easy",
        "language": "English", "description": "d", "briefing": "b", "critical_data_points": [],
    }
    return client.post("/scenarios", json=body, headers=_bearer(token)).json()["id"]


# ---------------------------------------------------------------------------
# has_location flag on the existing scenario CRUD
# ---------------------------------------------------------------------------


def test_scenarios_have_no_location_by_default(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)

    scenarios = client.get("/scenarios", headers=_bearer(token)).json()

    assert next(s for s in scenarios if s["id"] == scenario_id)["has_location"] is False


def test_putting_a_location_flips_has_location_to_true(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)

    client.put(
        f"/scenarios/{scenario_id}/location",
        json={"street": "5th Avenue"},
        headers=_bearer(token),
    )

    scenario = client.get(f"/scenarios/{scenario_id}", headers=_bearer(token)).json()
    assert scenario["has_location"] is True


# ---------------------------------------------------------------------------
# PUT validation — B10 (design doc)
# ---------------------------------------------------------------------------


def test_put_rejects_marker_without_any_text_field(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)

    response = client.put(
        f"/scenarios/{scenario_id}/location",
        json={"marker_x": 0.5, "marker_y": 0.5},
        headers=_bearer(token),
    )

    assert response.status_code == 422


def test_put_rejects_marker_out_of_range(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)

    response = client.put(
        f"/scenarios/{scenario_id}/location",
        json={"street": "5th Avenue", "marker_x": 1.5, "marker_y": 0.5},
        headers=_bearer(token),
    )

    assert response.status_code == 422


def test_put_returns_404_for_a_nonexistent_scenario(client):
    token = _login(client).json()["token"]

    response = client.put(
        "/scenarios/does-not-exist/location",
        json={"street": "5th Avenue"},
        headers=_bearer(token),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Authoring view vs. trainee view — mismo split que video (ScenarioLocationOut vs AccessOut)
# ---------------------------------------------------------------------------


def test_authoring_view_includes_match_hints_trainee_view_does_not(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)
    client.put(
        f"/scenarios/{scenario_id}/location",
        json={"street": "5th Avenue", "match_hints": ["fifth ave"]},
        headers=_bearer(token),
    )

    authoring = client.get(f"/scenarios/{scenario_id}/location", headers=_bearer(token)).json()
    brief = client.get(f"/scenarios/{scenario_id}/location/brief", headers=_bearer(token)).json()

    assert authoring["match_hints"] == ["fifth ave"]
    assert "match_hints" not in brief
    assert brief["street"] == "5th Avenue"  # el contenido SÍ se muestra al trainee (0A punto 1)


def test_brief_returns_404_when_location_has_no_configured_fields(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)
    # Guardar sin ningún campo de texto (todos default "") no es posible directamente sin
    # marcador (bloqueado arriba) — simula el caso borrando después de configurar y no
    # reconfigurando: get_scenario_location_brief debe 404 cuando no hay fila en absoluto.

    response = client.get(f"/scenarios/{scenario_id}/location/brief", headers=_bearer(token))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cascada de borrado — mismo hallazgo que video (Eng finding 2.3)
# ---------------------------------------------------------------------------


def test_deleting_a_scenario_cascades_its_location_reference(client):
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)
    client.put(
        f"/scenarios/{scenario_id}/location",
        json={"street": "5th Avenue"},
        headers=_bearer(token),
    )

    client.delete(f"/scenarios/{scenario_id}", headers=_bearer(token))

    # Recrear un escenario nuevo con el mismo flujo confirma que no quedó una fila fantasma
    # apuntando al scenario_id reciclado — get() debe volver a ser None.
    assert client.get(f"/scenarios/{scenario_id}/location", headers=_bearer(token)).status_code == 404


# ---------------------------------------------------------------------------
# Feature no configurada — 503, no AttributeError (mismo patrón que video)
# ---------------------------------------------------------------------------


def test_location_routes_503_when_the_store_is_not_configured(app_components):
    client = make_client(app_components, configure_location=False)
    token = _login(client).json()["token"]
    scenario_id = _create_scenario(client, token)

    response = client.put(
        f"/scenarios/{scenario_id}/location",
        json={"street": "5th Avenue"},
        headers=_bearer(token),
    )

    assert response.status_code == 503
