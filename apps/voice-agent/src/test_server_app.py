"""Test de integración del servidor FastAPI/WebSocket (roadmap Fase 1) contra `TestClient` —
sin red real, sin proceso `uvicorn` separado, pero ejercitando la app ASGI de punta a punta:
login → handshake de WebSocket autenticado (NFR-04) → sincronización de turno → registro de
sesión al desconectar (ADR-0007).
"""

import pytest
from fastapi.testclient import TestClient

from auth.session_token import HmacSessionTokenIssuer
from persistence.sqlite_store import SQLiteSessionStore
from server.app import create_app

PASSPHRASE = "correct-passphrase"


def make_clock():
    ticks = iter(range(1, 1000))
    return lambda: next(ticks)


@pytest.fixture
def app_components(tmp_path):
    token_issuer = HmacSessionTokenIssuer(secret_key=b"test-secret", clock=make_clock())
    session_store = SQLiteSessionStore(str(tmp_path / "sessions.db"))

    return token_issuer, session_store


@pytest.fixture
def client(app_components):
    token_issuer, session_store = app_components
    app = create_app(
        token_issuer=token_issuer,
        session_store=session_store,
        supervisor_passphrase=PASSPHRASE,
        clock=make_clock(),
    )

    return TestClient(app)


def _login(client, supervisor_id="sup-42", passphrase=PASSPHRASE):
    response = client.post(
        "/auth/login",
        json={"supervisor_id": supervisor_id, "passphrase": passphrase},
    )
    return response


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


def test_websocket_accepts_valid_token_and_syncs_turn_state(client):
    body = _login(client).json()

    with client.websocket_connect(
        f"/ws/session/{body['session_id']}?token={body['token']}"
    ) as ws:
        ws.send_json({"event": "supervisor_started_speaking"})
        reply = ws.receive_json()

        assert reply == {"state": "supervisor_speaking"}

        ws.send_json({"event": "supervisor_stopped_speaking"})
        reply = ws.receive_json()

        assert reply == {"state": "processing"}


def test_websocket_reports_invalid_event_without_dropping_the_connection(client):
    body = _login(client).json()

    with client.websocket_connect(
        f"/ws/session/{body['session_id']}?token={body['token']}"
    ) as ws:
        ws.send_json({"event": "dispatcher_finished_speaking"})  # inválido desde 'listening'
        reply = ws.receive_json()

        assert reply["error"]
        assert reply["state"] == "listening"

        # La conexión sigue viva después del error — NFR-02, no se cuelga.
        ws.send_json({"event": "supervisor_started_speaking"})
        reply = ws.receive_json()
        assert reply == {"state": "supervisor_speaking"}


def test_disconnecting_persists_the_session_record(client, app_components):
    _, session_store = app_components
    body = _login(client).json()

    with client.websocket_connect(
        f"/ws/session/{body['session_id']}?token={body['token']}"
    ) as ws:
        ws.send_json({"event": "supervisor_started_speaking"})
        ws.receive_json()

    record = session_store.get_session(body["session_id"])

    assert record is not None
    assert record.supervisor_id == "sup-42"
    assert record.turns == [
        {"event": "supervisor_started_speaking", "from": "listening", "to": "supervisor_speaking"}
    ]
    assert record.ended_at is not None


def test_server_emits_structured_logs_with_session_correlation_id(client, caplog):
    """NFR-08: logs estructurados con id de correlación por sesión, desde el login hasta la
    desconexión — no solo "hay logs", sino que comparten el mismo `correlation_id`."""

    with caplog.at_level("INFO", logger="voice_agent.server"):
        body = _login(client).json()
        session_id = body["session_id"]

        with client.websocket_connect(f"/ws/session/{session_id}?token={body['token']}") as ws:
            ws.send_json({"event": "supervisor_started_speaking"})
            ws.receive_json()

    events = {
        record.message: record.fields
        for record in caplog.records
        if record.name == "voice_agent.server"
    }

    assert events["login_succeeded"]["correlation_id"] == session_id
    assert events["session_connected"]["correlation_id"] == session_id
    assert events["turn_transition"] == {
        "correlation_id": session_id,
        "event": "supervisor_started_speaking",
        "from_state": "listening",
        "to_state": "supervisor_speaking",
    }
    assert events["session_disconnected"]["correlation_id"] == session_id
    assert events["session_disconnected"]["turn_count"] == 1
