"""Test de integración del servidor FastAPI/WebSocket (roadmap Fase 1 + Fase 2) contra
`TestClient` — sin red real, sin proceso `uvicorn` separado, pero ejercitando la app ASGI de
punta a punta: login → handshake de WebSocket autenticado (NFR-04) → protocolo completo de
comandos/eventos (`call.start` → grabación → `call.end` → `session.completed` con evaluación) →
registro de sesión (ADR-0007) → REST de escenarios/ajustes.

Los puertos de STT/TTS/LLM/micrófono se stubean (son `Protocol`, ver `core/ports.py`) — nada de
esto toca Whisper/Kokoro/Claude/sounddevice reales.
"""

import pytest
from fastapi.testclient import TestClient

from auth.session_token import HmacSessionTokenIssuer
from core.ports import DispatcherError
from persistence.sqlite_scenario_store import SQLiteScenarioStore
from persistence.sqlite_settings_store import SQLiteSettingsStore
from persistence.sqlite_store import SQLiteSessionStore
from server.app import create_app

PASSPHRASE = "correct-passphrase"


def make_clock():
    ticks = iter(range(1, 10_000))
    return lambda: next(ticks)


class StubDispatcher:
    def __init__(self, replies, error_on: set[int] = frozenset()):
        self._replies = list(replies)
        self._error_on = error_on
        self.calls = 0

    def respond(self, conversation, scenario):
        index = self.calls
        self.calls += 1
        if index in self._error_on:
            raise DispatcherError("Claude API unavailable after retries")
        return self._replies[index]


class StubSTT:
    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = 0

    def transcribe(self, audio_path):
        text = self._texts[self.calls]
        self.calls += 1
        return text


class StubTTS:
    def __init__(self):
        self.spoken: list[tuple[str, str | None]] = []

    def speak(self, text, voice=None):
        self.spoken.append((text, voice))


class StubMicrophone:
    def __init__(self, available: bool = True):
        self._available = available
        self.recording = False

    def is_available(self):
        return self._available

    def start_recording(self, output_path="recording.wav"):
        self.recording = True

    def stop_recording(self):
        self.recording = False
        return "stub-audio.wav"

    def record(self, output_path="recording.wav"):
        return "stub-audio.wav"


@pytest.fixture
def app_components(tmp_path):
    token_issuer = HmacSessionTokenIssuer(secret_key=b"test-secret", clock=make_clock())
    session_store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    scenario_store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    settings_store = SQLiteSettingsStore(str(tmp_path / "settings.db"))

    return token_issuer, session_store, scenario_store, settings_store


def make_client(app_components, dispatcher=None, stt=None, tts=None, microphone=None):
    token_issuer, session_store, scenario_store, settings_store = app_components
    app = create_app(
        token_issuer=token_issuer,
        session_store=session_store,
        scenario_store=scenario_store,
        settings_store=settings_store,
        supervisor_passphrase=PASSPHRASE,
        dispatcher=dispatcher or StubDispatcher(["911, what is your emergency?"]),
        stt=stt or StubSTT([""]),
        tts=tts or StubTTS(),
        microphone=microphone or StubMicrophone(),
        clock=make_clock(),
    )
    return TestClient(app)


@pytest.fixture
def client(app_components):
    return make_client(app_components)


def _login(client, supervisor_id="sup-42", passphrase=PASSPHRASE):
    return client.post("/auth/login", json={"supervisor_id": supervisor_id, "passphrase": passphrase})


def _drain_until(ws, event_name, max_messages=30):
    """Lee mensajes del WS hasta encontrar el evento buscado — el protocolo real emite varios
    eventos intermedios (`call.status`, `engine.activity`, `dispatcher.speaking`, ...) antes de
    cada evento que a un test le interesa puntualmente."""

    for _ in range(max_messages):
        message = ws.receive_json()
        if message.get("event") == event_name:
            return message

    raise AssertionError(f"event {event_name!r} was not received")


# ---------------------------------------------------------------------------
# REST — salud, auth (sin cambios de Fase 1)
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_with_correct_passphrase_returns_token_and_session_id(client):
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert "session_id" in body
    assert "token" in body


def test_login_with_wrong_passphrase_is_rejected(client):
    response = _login(client, passphrase="wrong")

    assert response.status_code == 401


def test_websocket_rejects_invalid_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/session/some-session?token=not-a-real-token"):
            pass


def test_websocket_rejects_token_for_a_different_session(client):
    body = _login(client).json()

    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/session/some-other-session?token={body['token']}"):
            pass


# ---------------------------------------------------------------------------
# REST — escenarios (Fase 2, TODO-11)
# ---------------------------------------------------------------------------


def test_scenarios_are_seeded_and_listed_over_rest(client):
    body = _login(client).json()

    response = client.get("/scenarios", headers={"Authorization": f"Bearer {body['token']}"})

    assert response.status_code == 200
    ids = {scenario["id"] for scenario in response.json()}
    assert {"vehicle_theft", "domestic_dispute", "traffic_accident"} <= ids


def test_scenario_crud_round_trip(client):
    body = _login(client).json()
    headers = {"Authorization": f"Bearer {body['token']}"}

    created = client.post(
        "/scenarios",
        headers=headers,
        json={
            "title": "Burglary in Progress",
            "category": "Police",
            "difficulty": "Hard",
            "language": "English",
            "description": "An active burglary.",
            "briefing": "A caller reports someone breaking into their neighbor's house.",
            "critical_data_points": [{"key": "address", "label": "Address", "required": True}],
        },
    )
    assert created.status_code == 201
    scenario_id = created.json()["id"]

    fetched = client.get(f"/scenarios/{scenario_id}", headers=headers)
    assert fetched.json()["title"] == "Burglary in Progress"

    updated = client.put(
        f"/scenarios/{scenario_id}",
        headers=headers,
        json={**created.json(), "title": "Burglary in Progress — Updated"},
    )
    assert updated.json()["title"] == "Burglary in Progress — Updated"

    deleted = client.delete(f"/scenarios/{scenario_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/scenarios/{scenario_id}", headers=headers).status_code == 404


def test_scenario_endpoints_require_a_bearer_token(client):
    response = client.get("/scenarios")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# REST — ajustes (Fase 2, alcance mínimo)
# ---------------------------------------------------------------------------


def test_settings_default_to_the_standard_voice_and_can_be_updated(client):
    body = _login(client).json()
    headers = {"Authorization": f"Bearer {body['token']}"}

    assert client.get("/settings", headers=headers).json() == {"tts_voice": "am_michael"}

    updated = client.put("/settings", headers=headers, json={"tts_voice": "bf_emma"})
    assert updated.json() == {"tts_voice": "bf_emma"}
    assert client.get("/settings", headers=headers).json() == {"tts_voice": "bf_emma"}


# ---------------------------------------------------------------------------
# WebSocket — el loop de llamada real (Fase 2 cierra el gap de Fase 1)
# ---------------------------------------------------------------------------


def test_websocket_sends_ready_scenarios_and_history_on_connect(client):
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        assert ws.receive_json()["event"] == "system.ready"
        assert ws.receive_json()["event"] == "scenarios.data"
        assert ws.receive_json() == {"event": "history.data", "sessions": []}


def test_full_call_flow_produces_a_completed_session_with_evaluation(app_components):
    dispatcher = StubDispatcher([
        "911, what is your emergency?",
        "Can you spell out the license plate for me?",
    ])
    stt = StubSTT(["My car was stolen, license plate ABC123, near the mall this morning."])
    tts = StubTTS()
    client = make_client(app_components, dispatcher=dispatcher, stt=stt, tts=tts)
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json()  # system.ready
        ws.receive_json()  # scenarios.data
        ws.receive_json()  # history.data

        ws.send_json({
            "command": "call.start",
            "scenarioId": "vehicle_theft",
            "difficulty": "Medium",
            "language": "English",
            "trainingType": "Police",
        })
        assert _drain_until(ws, "call.started")["scenario"]["id"] == "vehicle_theft"
        greeting = _drain_until(ws, "transcript.dispatcher")
        assert greeting["text"] == "911, what is your emergency?"

        ws.send_json({"command": "recording.start"})
        assert _drain_until(ws, "operator.speaking")["value"] is True

        ws.send_json({"command": "recording.stop"})
        operator_line = _drain_until(ws, "transcript.operator")
        assert "license plate" in operator_line["text"]
        dispatcher_line = _drain_until(ws, "transcript.dispatcher")
        assert dispatcher_line["text"] == "Can you spell out the license plate for me?"
        assert _drain_until(ws, "call.status")["status"] == "connected"

        ws.send_json({"command": "call.end"})
        completed = _drain_until(ws, "session.completed")

    session = completed["session"]
    assert session["status"] == "completed"
    assert session["evaluation"] is not None
    assert "License plate" in session["evaluation"]["collected"]
    assert tts.spoken  # el TTS stub recibió al menos la línea de saludo

    record = app_components[1].get_session(body["session_id"])
    assert record.outcome == "ended"
    assert record.evaluation is not None


def test_call_start_with_unknown_scenario_is_a_recoverable_error(client):
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

        ws.send_json({"command": "call.start", "scenarioId": "not-a-real-scenario", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        reply = ws.receive_json()

        assert reply == {"event": "error", "message": "Unknown scenario.", "recoverable": True}


def test_call_start_with_no_microphone_reports_a_recoverable_error(app_components):
    client = make_client(app_components, microphone=StubMicrophone(available=False))
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})

        assert _drain_until(ws, "error")["message"] == "No microphone was detected."
        assert _drain_until(ws, "call.status")["status"] == "error"


def test_dispatcher_error_recovers_in_dialogue_instead_of_dropping_the_call(app_components):
    dispatcher = StubDispatcher(["ignored"], error_on={0})
    client = make_client(app_components, dispatcher=dispatcher)
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        greeting = _drain_until(ws, "transcript.dispatcher")

        assert greeting["text"] == "Sorry, can you repeat that? I didn't catch it."


def test_call_pause_and_resume_update_call_status(client):
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "call.started")
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "call.pause"})
        assert ws.receive_json() == {"event": "call.status", "status": "paused"}

        ws.send_json({"command": "call.resume"})
        assert ws.receive_json() == {"event": "call.status", "status": "connected"}


def test_unknown_command_is_a_recoverable_error_and_keeps_the_connection_open(client):
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

        ws.send_json({"command": "not.a.real.command"})
        reply = ws.receive_json()
        assert reply["event"] == "error"
        assert reply["recoverable"] is True

        # La conexión sigue viva después del error — NFR-02, no se cuelga.
        ws.send_json({"command": "system.ping"})
        assert ws.receive_json()["event"] == "system.ready"


def test_disconnecting_mid_call_persists_a_network_drop_outcome_without_scoring(app_components):
    client = make_client(app_components)
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")
        # La conexión se cierra acá sin `call.end` — simula una caída de red a mitad de llamada.

    record = app_components[1].get_session(body["session_id"])

    assert record.outcome == "network_drop"
    assert record.evaluation is None


def test_disconnecting_without_ever_starting_a_call_does_not_persist_a_phantom_session(client):
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

    # No hay assert directo sobre "no existe" porque `get_session` requeriría saber que no se
    # guardó nada — se prueba indirectamente vía el historial, que debe seguir vacío.
    body2 = _login(client, supervisor_id="sup-42").json()
    with client.websocket_connect(f"/ws/session/{body2['session_id']}?token={body2['token']}") as ws:
        ws.receive_json()
        assert ws.receive_json()["event"] == "scenarios.data"
        assert ws.receive_json() == {"event": "history.data", "sessions": []}


def test_history_is_scoped_to_the_requesting_supervisor(app_components):
    client = make_client(app_components)

    alice = _login(client, supervisor_id="alice").json()
    with client.websocket_connect(f"/ws/session/{alice['session_id']}?token={alice['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")
        ws.send_json({"command": "call.end"})
        _drain_until(ws, "session.completed")

    bob = _login(client, supervisor_id="bob").json()
    with client.websocket_connect(f"/ws/session/{bob['session_id']}?token={bob['token']}") as ws:
        ws.receive_json()
        ws.receive_json()
        assert ws.receive_json() == {"event": "history.data", "sessions": []}  # bob no ve la sesión de alice


def test_server_emits_structured_logs_with_session_correlation_id(client, caplog):
    """NFR-08: logs estructurados con id de correlación por sesión, desde el login hasta la
    desconexión, incluyendo latencia por turno (STT/dispatcher/TTS)."""

    with caplog.at_level("INFO", logger="voice_agent.server"):
        body = _login(client).json()
        session_id = body["session_id"]

        with client.websocket_connect(f"/ws/session/{session_id}?token={body['token']}") as ws:
            ws.receive_json(), ws.receive_json(), ws.receive_json()
            ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
            _drain_until(ws, "transcript.dispatcher")

    events = {
        record.message: record.fields for record in caplog.records if record.name == "voice_agent.server"
    }

    assert events["login_succeeded"]["correlation_id"] == session_id
    assert events["session_connected"]["correlation_id"] == session_id
    assert events["turn_transition"]["correlation_id"] == session_id
    assert "latency_ms" in events["dispatcher_completed"]
    assert "latency_ms" in events["tts_completed"]
    assert events["session_disconnected"]["correlation_id"] == session_id
