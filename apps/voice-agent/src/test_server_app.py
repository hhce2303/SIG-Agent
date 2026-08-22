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
from core.ports import DispatcherError, TranscriptionResult
from persistence.sqlite_incident_store import SQLiteIncidentStore
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
    """T2/T12 (docs/designs/motor-de-metricas.md): devuelve `TranscriptionResult`, no un `str` —
    este stub también lo importa `test_server_video.py`, así que arreglarlo acá cubre los dos
    archivos (hallazgo de la voz independiente de ingeniería)."""

    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = 0

    def transcribe(self, audio_path) -> TranscriptionResult:
        text = self._texts[self.calls]
        self.calls += 1
        return TranscriptionResult(text=text, segments=[])


class StubTTS:
    def __init__(self):
        self.spoken: list[tuple[str, str | None]] = []

    def speak(self, text, voice=None):
        self.spoken.append((text, voice))


class StubMetricsJudge:
    """T13/T14 (docs/designs/motor-de-metricas.md) — stub de `MetricsJudgePort`. `error` inyecta
    una `MetricsJudgeError` para probar la degradación explícita de `finish_call`."""

    def __init__(self, error: Exception | None = None):
        self._error = error
        self.calls = 0

    def judge(self, transcript, critical_data_points, collected, missing):
        self.calls += 1
        if self._error is not None:
            raise self._error
        from core.ports import MetricsJudgment
        return MetricsJudgment(
            coherence_rating="good",
            coherence_tip="Clear and well organized report.",
            english_quality_rating="good",
            english_quality_tip="Fluent, no notable errors.",
            completeness_agrees_with_keyword_match=True,
            raw_response="{}",
        )


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
    incident_store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))

    return token_issuer, session_store, scenario_store, settings_store, incident_store


def make_client(app_components, dispatcher=None, stt=None, tts=None, microphone=None, metrics_judge=None):
    token_issuer, session_store, scenario_store, settings_store, incident_store = app_components
    app = create_app(
        token_issuer=token_issuer,
        session_store=session_store,
        scenario_store=scenario_store,
        settings_store=settings_store,
        incident_store=incident_store,
        supervisor_passphrase=PASSPHRASE,
        metrics_judge=metrics_judge,
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
    # T4/T14 (docs/designs/motor-de-metricas.md): sin `metrics_judge` configurado, la sesión
    # sigue completándose — el panel de coaching se degrada explícitamente, no rompe la llamada.
    coaching = record.evaluation["communication_coaching"]
    assert coaching["coherence"] is None
    assert coaching["english_quality"] is None
    assert record.evaluation["judge_unavailable"] is True
    # `StubSTT` no fabrica `SttSegment`s (solo texto) — sin datos de segmento no hay nada que
    # agregar, `transcription_confidence` queda en `None` (nunca inventa un score sin datos).
    assert coaching["transcription_confidence"] is None


def test_full_call_flow_with_metrics_judge_fills_coherence_and_english_quality(app_components):
    judge = StubMetricsJudge()
    dispatcher = StubDispatcher(["911, what is your emergency?", "Can you spell out the license plate?"])
    stt = StubSTT(["My car was stolen, license plate ABC123, near the mall this morning."])
    client = make_client(app_components, dispatcher=dispatcher, stt=stt, metrics_judge=judge)
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "recording.start"})
        _drain_until(ws, "operator.speaking")
        ws.send_json({"command": "recording.stop"})
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "call.end"})
        completed = _drain_until(ws, "session.completed")

    coaching = completed["session"]["evaluation"]["communication_coaching"]
    assert coaching["coherence"] == {"rating": "good", "tip": "Clear and well organized report."}
    assert coaching["english_quality"]["rating"] == "good"
    assert completed["session"]["evaluation"]["judge_unavailable"] is False
    assert judge.calls == 1


def test_full_call_flow_degrades_gracefully_when_judge_fails(app_components):
    from core.ports import MetricsJudgeError

    judge = StubMetricsJudge(error=MetricsJudgeError("simulated Claude outage"))
    client = make_client(app_components, metrics_judge=judge)
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "call.end"})
        completed = _drain_until(ws, "session.completed")

    # La sesión se completa igual — nunca se tumba `finish_call` por un fallo del judge.
    evaluation = completed["session"]["evaluation"]
    assert evaluation is not None
    assert evaluation["judge_unavailable"] is True
    assert evaluation["communication_coaching"]["coherence"] is None
    assert evaluation["category_scores"]["completeness"] is not None  # las 4 categorías siguen intactas


def test_judge_is_never_called_when_the_call_network_drops(app_components):
    """T14 (CRÍTICO, hallazgo de la voz independiente): el judge no debe correr en una
    desconexión trivial — `score_session` devuelve `None` para `network_drop` y todo el bloque
    que llama al judge está detrás de `if evaluation is not None`."""

    judge = StubMetricsJudge()
    client = make_client(app_components, metrics_judge=judge)
    body = _login(client).json()

    with client.websocket_connect(f"/ws/session/{body['session_id']}?token={body['token']}") as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")
        # Desconexión sin `call.end` — network_drop.

    assert judge.calls == 0
    record = app_components[1].get_session(body["session_id"])
    assert record.outcome == "network_drop"
    assert record.evaluation is None


def test_stale_network_drop_never_overwrites_an_already_completed_session(app_components):
    """T15 — guarda de carrera de 2 conexiones (docs/designs/motor-de-metricas.md). Simula el
    escenario que encontró la voz independiente de ingeniería: una conexión reconectada ya
    completó `call.end` (outcome="ended" con evaluación real); una segunda conexión para la
    MISMA sesión que solo llega a desconectarse (network_drop tardío) no debe sobrescribirla."""

    # 2 conexiones → 2 saludos del dispatcher (uno por `call.start`).
    dispatcher = StubDispatcher(["911, what is your emergency?", "911, what is your emergency?"])
    client = make_client(app_components, dispatcher=dispatcher)
    body = _login(client).json()
    ws_url = f"/ws/session/{body['session_id']}?token={body['token']}"

    with client.websocket_connect(ws_url) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")
        ws.send_json({"command": "call.end"})
        _drain_until(ws, "session.completed")

    record_after_ended = app_components[1].get_session(body["session_id"])
    assert record_after_ended.outcome == "ended"
    assert record_after_ended.evaluation is not None

    # "Conexión vieja" tardía para la misma sesión — solo se desconecta, sin `call.start` ni
    # `call.end` (simula la reconexión del frontend habiendo llegado primero con el resultado
    # bueno, y la conexión original terminando después con un network_drop obsoleto).
    with client.websocket_connect(ws_url) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()
        ws.send_json({"command": "call.start", "scenarioId": "vehicle_theft", "difficulty": "Medium", "language": "English", "trainingType": "Police"})
        _drain_until(ws, "transcript.dispatcher")
        # Se desconecta sin `call.end` — dispara `finish_call("network_drop")` en el `finally`.

    record_after_stale_drop = app_components[1].get_session(body["session_id"])
    assert record_after_stale_drop.outcome == "ended"  # NO se sobrescribió con "network_drop"
    assert record_after_stale_drop.evaluation is not None


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


# ---------------------------------------------------------------------------
# Incidentes reales — roadmap Fase 3.
# ---------------------------------------------------------------------------


def _incident_payload(**overrides):
    payload = {
        "occurred_at": 500.0,
        "supervisor_id": "sup-42",
        "category": "Vehicle Theft",
        "outcome_rating": 4,
        "critical_data_captured": True,
        "protocol_followed": True,
        "notes": "Handled well, minor delay confirming the plate.",
    }
    payload.update(overrides)
    return payload


def test_incident_crud_round_trip(client):
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/incidents", json=_incident_payload(), headers=headers)
    assert created.status_code == 201
    incident_id = created.json()["id"]
    assert created.json()["reported_by"] == "sup-42"
    assert created.json()["promoted_scenario_id"] == ""

    listed = client.get("/incidents", headers=headers)
    assert listed.status_code == 200
    assert [i["id"] for i in listed.json()] == [incident_id]

    deleted = client.delete(f"/incidents/{incident_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/incidents", headers=headers).json() == []


def test_promote_incident_creates_a_draft_scenario_from_the_post_mortem(client):
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post(
        "/incidents", json=_incident_payload(notes="Caller was confused about the address."), headers=headers
    ).json()["id"]

    promoted = client.post(f"/incidents/{incident_id}/promote-to-scenario", headers=headers)
    assert promoted.status_code == 201
    scenario = promoted.json()
    assert scenario["briefing"] == "Caller was confused about the address."
    assert scenario["critical_data_points"] == []

    incident = client.get("/incidents", headers=headers).json()[0]
    assert incident["promoted_scenario_id"] == scenario["id"]

    # promover dos veces el mismo incidente sería un duplicado silencioso en la librería.
    again = client.post(f"/incidents/{incident_id}/promote-to-scenario", headers=headers)
    assert again.status_code == 409


def test_impact_report_is_inconclusive_below_the_minimum_sample_size(client):
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/incidents", json=_incident_payload(), headers=headers)

    report = client.get("/impact-report", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["is_conclusive"] is False
    assert body["total_incidents"] == 1
    assert body["caveat"] != ""


def test_impact_report_correlates_incidents_against_completed_training_sessions(app_components):
    client = make_client(app_components)
    token = _login(client, supervisor_id="trained-sup").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    session_store = app_components[1]
    for i in range(5):
        session_store.save_session(
            _make_completed_session(f"session-{i}", "trained-sup", ended_at=100.0)
        )

    for i in range(5):
        client.post(
            "/incidents",
            json=_incident_payload(supervisor_id="trained-sup", occurred_at=200.0, outcome_rating=5),
            headers=headers,
        )
    for i in range(5):
        client.post(
            "/incidents",
            json=_incident_payload(supervisor_id="untrained-sup", occurred_at=200.0, outcome_rating=2),
            headers=headers,
        )

    body = client.get("/impact-report", headers=headers).json()
    assert body["is_conclusive"] is True
    assert body["trained"]["sample_size"] == 5
    assert body["trained"]["avg_outcome_rating"] == 5.0
    assert body["untrained"]["sample_size"] == 5
    assert body["untrained"]["avg_outcome_rating"] == 2.0


def _make_completed_session(session_id, supervisor_id, ended_at):
    from core.ports import SessionRecord

    return SessionRecord(
        session_id=session_id,
        supervisor_id=supervisor_id,
        scenario_name="Vehicle Theft",
        started_at=ended_at - 60.0,
        ended_at=ended_at,
        outcome="ended",
    )
