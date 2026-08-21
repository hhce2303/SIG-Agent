"""Test de integración de escenarios de video contra `TestClient` — docs/designs/
escenarios-de-video.md, ADR-0009/ADR-0010/ADR-0011. Mismo patrón que `test_server_app.py`
(stubs de STT/TTS/LLM/mic, SQLite real contra `tmp_path`), extendido con
`scenario_video_store`/`video_token_issuer`/`manager_passphrase`.
"""

import os

import pytest
from fastapi.testclient import TestClient

from auth.session_token import HmacSessionTokenIssuer
from auth.video_token import HmacVideoTokenIssuer
from persistence.sqlite_incident_store import SQLiteIncidentStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore
from persistence.sqlite_scenario_video_store import SQLiteScenarioVideoStore
from persistence.sqlite_settings_store import SQLiteSettingsStore
from persistence.sqlite_store import SQLiteSessionStore
from server.app import create_app
from test_server_app import StubDispatcher, StubMicrophone, StubSTT, StubTTS, _drain_until, make_clock

SUPERVISOR_PASSPHRASE = "correct-passphrase"
MANAGER_PASSPHRASE = "manager-passphrase"


@pytest.fixture
def video_file(tmp_path):
    path = tmp_path / "robbery_001.mp4"
    path.write_bytes(b"fake-mp4-bytes-for-tests" * 100)
    return str(path)


@pytest.fixture
def app_components(tmp_path):
    token_issuer = HmacSessionTokenIssuer(secret_key=b"test-secret", clock=make_clock())
    video_token_issuer = HmacVideoTokenIssuer(secret_key=b"test-video-secret", clock=make_clock())
    session_store = SQLiteSessionStore(str(tmp_path / "sessions.db"))
    scenario_store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    scenario_video_store = SQLiteScenarioVideoStore(str(tmp_path / "scenario_videos.db"))
    settings_store = SQLiteSettingsStore(str(tmp_path / "settings.db"))
    incident_store = SQLiteIncidentStore(str(tmp_path / "incidents.db"))

    return {
        "token_issuer": token_issuer,
        "video_token_issuer": video_token_issuer,
        "session_store": session_store,
        "scenario_store": scenario_store,
        "scenario_video_store": scenario_video_store,
        "settings_store": settings_store,
        "incident_store": incident_store,
        "video_storage_dir": str(tmp_path / "video_storage"),  # ADR-0012
    }


def make_client(components, configure_video=True, configure_upload=True, **overrides):
    kwargs = dict(
        token_issuer=components["token_issuer"],
        session_store=components["session_store"],
        scenario_store=components["scenario_store"],
        settings_store=components["settings_store"],
        incident_store=components["incident_store"],
        supervisor_passphrase=SUPERVISOR_PASSPHRASE,
        manager_passphrase=MANAGER_PASSPHRASE,
        dispatcher=overrides.pop("dispatcher", None) or StubDispatcher(["911, what is your emergency?"]),
        stt=overrides.pop("stt", None) or StubSTT([""]),
        tts=overrides.pop("tts", None) or StubTTS(),
        microphone=overrides.pop("microphone", None) or StubMicrophone(),
        clock=make_clock(),
    )
    if configure_video:
        kwargs["scenario_video_store"] = components["scenario_video_store"]
        kwargs["video_token_issuer"] = components["video_token_issuer"]
    if configure_upload:
        kwargs["video_storage_dir"] = components["video_storage_dir"]
    kwargs.update(overrides)
    return TestClient(create_app(**kwargs))


@pytest.fixture
def client(app_components):
    return make_client(app_components)


def _login(client, supervisor_id="sup-42", passphrase=SUPERVISOR_PASSPHRASE):
    return client.post("/auth/login", json={"supervisor_id": supervisor_id, "passphrase": passphrase})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# has_video flag on the existing scenario CRUD
# ---------------------------------------------------------------------------


def test_scenarios_have_no_video_by_default(client):
    token = _login(client).json()["token"]

    scenarios = client.get("/scenarios", headers=_bearer(token)).json()

    assert all(s["has_video"] is False for s in scenarios)


def test_video_feature_returns_503_when_not_configured(app_components):
    client = make_client(app_components, configure_video=False)
    token = _login(client).json()["token"]

    response = client.get("/scenarios/vehicle_theft/video", headers=_bearer(token))

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# PUT/GET/DELETE /scenarios/{id}/video
# ---------------------------------------------------------------------------


def test_attach_video_then_it_shows_up_on_the_scenario_list(client, video_file):
    token = _login(client).json()["token"]

    put_response = client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={
            "video_path": video_file,
            "duration_seconds": 42.0,
            "ground_truth_points": [
                {
                    "key": "suspect_clothing",
                    "label": "Suspect clothing",
                    "match_hints": ["red jacket"],
                    "visible_from_seconds": 2.0,
                    "visible_to_seconds": 8.0,
                },
            ],
        },
    )
    assert put_response.status_code == 200
    assert put_response.json()["video_checksum"]  # server-computed, no vacío

    scenarios = client.get("/scenarios", headers=_bearer(token)).json()
    vehicle_theft = next(s for s in scenarios if s["id"] == "vehicle_theft")
    assert vehicle_theft["has_video"] is True


def test_attach_video_rejects_a_ground_truth_range_outside_the_duration(client, video_file):
    token = _login(client).json()["token"]

    response = client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={
            "video_path": video_file,
            "duration_seconds": 10.0,
            "ground_truth_points": [
                {"key": "x", "label": "X", "visible_from_seconds": 5.0, "visible_to_seconds": 20.0},
            ],
        },
    )

    assert response.status_code == 422


def test_attach_video_with_a_missing_file_returns_400(client):
    token = _login(client).json()["token"]

    response = client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={"video_path": "C:/does/not/exist.mp4", "duration_seconds": 10.0},
    )

    assert response.status_code == 400


def test_trainee_facing_video_access_never_includes_ground_truth(client, video_file):
    token = _login(client).json()["token"]
    client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={
            "video_path": video_file,
            "duration_seconds": 42.0,
            "ground_truth_points": [{"key": "x", "label": "X", "match_hints": ["secret-answer"]}],
        },
    )

    access = client.get("/scenarios/vehicle_theft/video", headers=_bearer(token)).json()

    assert "ground_truth_points" not in access
    assert "match_hints" not in str(access)  # ninguna forma de la respuesta filtra el hint
    assert access["stream_url"].startswith("/scenarios/vehicle_theft/video/stream?token=")


def test_editor_ground_truth_view_includes_match_hints(client, video_file):
    token = _login(client).json()["token"]
    client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={
            "video_path": video_file,
            "duration_seconds": 42.0,
            "ground_truth_points": [{"key": "x", "label": "X", "match_hints": ["red jacket"]}],
        },
    )

    ground_truth = client.get("/scenarios/vehicle_theft/video/ground-truth", headers=_bearer(token)).json()

    assert ground_truth["ground_truth_points"][0]["match_hints"] == ["red jacket"]


def test_delete_video_removes_the_reference(client, video_file):
    token = _login(client).json()["token"]
    client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={"video_path": video_file, "duration_seconds": 42.0},
    )

    delete_response = client.delete("/scenarios/vehicle_theft/video", headers=_bearer(token))
    assert delete_response.status_code == 204

    access = client.get("/scenarios/vehicle_theft/video", headers=_bearer(token))
    assert access.status_code == 404


def test_deleting_a_scenario_cascades_its_video_reference(client, video_file):
    token = _login(client).json()["token"]
    scenario = client.post(
        "/scenarios",
        headers=_bearer(token),
        json={
            "title": "Test", "category": "Police", "difficulty": "Easy", "language": "English",
            "description": "d", "briefing": "b",
        },
    ).json()
    client.put(f"/scenarios/{scenario['id']}/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })

    client.delete(f"/scenarios/{scenario['id']}", headers=_bearer(token))

    assert client.get(f"/scenarios/{scenario['id']}/video", headers=_bearer(token)).status_code == 404


# ---------------------------------------------------------------------------
# Upload real (ADR-0012) — reemplaza tener que colocar el archivo a mano en el servidor.
# ---------------------------------------------------------------------------


def _minimal_mp4_bytes(duration_seconds: float = 12.0) -> bytes:
    import struct

    def box(box_type: bytes, body: bytes) -> bytes:
        return struct.pack(">I4s", 8 + len(body), box_type) + body

    ftyp = box(b"ftyp", b"isom" + b"\x00" * 4)
    mvhd_body = (
        bytes([0, 0, 0, 0]) + b"\x00" * 4 + b"\x00" * 4
        + struct.pack(">I", 1000) + struct.pack(">I", int(duration_seconds * 1000))
    )
    moov = box(b"moov", box(b"mvhd", mvhd_body))
    return ftyp + moov


def test_upload_saves_the_file_and_detects_duration(client):
    token = _login(client).json()["token"]

    response = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", _minimal_mp4_bytes(duration_seconds=17.5), "video/mp4")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duration_seconds"] == 17.5
    assert body["video_checksum"]
    assert body["content_type"] == "video/mp4"
    # Nombre de archivo generado por el servidor (Eng 4.3), nunca "robbery.mp4" del cliente.
    assert "robbery" not in body["video_path"]
    with open(body["video_path"], "rb") as handle:
        assert handle.read() == _minimal_mp4_bytes(duration_seconds=17.5)


def test_upload_falls_back_to_none_duration_when_it_cant_be_detected(client):
    token = _login(client).json()["token"]

    response = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", b"not a real mp4, just bytes with the right extension", "video/mp4")},
    )

    assert response.status_code == 200
    assert response.json()["duration_seconds"] is None


def test_upload_rejects_an_unsupported_file_extension(client):
    token = _login(client).json()["token"]

    response = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.avi", b"whatever", "video/x-msvideo")},
    )

    assert response.status_code == 415


def test_upload_rejects_files_over_the_size_limit(app_components):
    client = make_client(app_components, video_max_upload_bytes=10)
    token = _login(client).json()["token"]

    response = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", b"x" * 1000, "video/mp4")},
    )

    assert response.status_code == 413


def test_upload_is_not_scoped_to_any_scenario(client):
    # Deliberado (ver docstring de `upload_video`): el archivo no pertenece a ningún escenario
    # todavía en el momento de subirlo — promote-to-scenario lo usa ANTES de que el escenario
    # exista. No hay "escenario no encontrado" posible acá, a diferencia de PUT/ground-truth.
    token = _login(client).json()["token"]

    response = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", _minimal_mp4_bytes(), "video/mp4")},
    )

    assert response.status_code == 200


def test_upload_returns_503_when_upload_is_not_configured(app_components):
    client = make_client(app_components, configure_upload=False)
    token = _login(client).json()["token"]

    response = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", _minimal_mp4_bytes(), "video/mp4")},
    )

    assert response.status_code == 503


def test_uploaded_video_is_immediately_usable_end_to_end(client):
    # Regresión directa del reporte del usuario: subir + adjuntar + que el escenario quede
    # marcado con video, todo en un solo flujo, sin tocar el filesystem del servidor a mano.
    token = _login(client).json()["token"]

    upload = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", _minimal_mp4_bytes(duration_seconds=20.0), "video/mp4")},
    ).json()

    attach = client.put(
        "/scenarios/vehicle_theft/video",
        headers=_bearer(token),
        json={
            "video_path": upload["video_path"],
            "duration_seconds": upload["duration_seconds"],
            "content_type": upload["content_type"],
            "ground_truth_points": [{"key": "x", "label": "X", "match_hints": ["knife"]}],
        },
    )
    assert attach.status_code == 200

    scenarios = client.get("/scenarios", headers=_bearer(token)).json()
    assert next(s for s in scenarios if s["id"] == "vehicle_theft")["has_video"] is True


def test_deleting_an_uploaded_video_removes_the_file_from_disk(client):
    token = _login(client).json()["token"]
    upload = client.post(
        "/videos/upload",
        headers=_bearer(token),
        files={"file": ("robbery.mp4", _minimal_mp4_bytes(), "video/mp4")},
    ).json()
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": upload["video_path"], "duration_seconds": upload["duration_seconds"] or 10.0,
    })
    assert os.path.exists(upload["video_path"])

    client.delete("/scenarios/vehicle_theft/video", headers=_bearer(token))

    assert not os.path.exists(upload["video_path"])  # ADR-0012 — archivo que SÍ subimos nosotros


def test_deleting_a_manually_referenced_video_does_not_touch_the_file(client, video_file):
    # Eng 2.3: solo borramos lo que subimos NOSOTROS — un video_path de la v1 manual (fuera de
    # video_storage_dir) nunca se toca, no es nuestro para borrar.
    token = _login(client).json()["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })

    client.delete("/scenarios/vehicle_theft/video", headers=_bearer(token))

    assert os.path.exists(video_file)


# ---------------------------------------------------------------------------
# Streaming — auth, Range requests, y el escenario "archivo ausente en disco"
# ---------------------------------------------------------------------------


def test_stream_without_a_video_token_is_rejected(client, video_file):
    token = _login(client).json()["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })

    response = client.get("/scenarios/vehicle_theft/video/stream", params={"token": "not-a-real-token"})

    assert response.status_code == 401


def test_stream_rejects_a_token_issued_for_a_different_scenario(client, video_file):
    token = _login(client).json()["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })
    client.put("/scenarios/domestic_dispute/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })
    access = client.get("/scenarios/domestic_dispute/video", headers=_bearer(token)).json()
    foreign_token = access["stream_url"].split("token=")[1]

    response = client.get(
        "/scenarios/vehicle_theft/video/stream", params={"token": foreign_token}
    )

    assert response.status_code == 401


def test_full_video_streams_with_accept_ranges_header(client, video_file):
    token = _login(client).json()["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })
    access = client.get("/scenarios/vehicle_theft/video", headers=_bearer(token)).json()
    video_token = access["stream_url"].split("token=")[1]

    response = client.get("/scenarios/vehicle_theft/video/stream", params={"token": video_token})

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    with open(video_file, "rb") as handle:
        assert response.content == handle.read()


def test_range_request_returns_206_with_the_requested_slice(client, video_file):
    token = _login(client).json()["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })
    access = client.get("/scenarios/vehicle_theft/video", headers=_bearer(token)).json()
    video_token = access["stream_url"].split("token=")[1]

    response = client.get(
        "/scenarios/vehicle_theft/video/stream",
        params={"token": video_token},
        headers={"Range": "bytes=0-9"},
    )

    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-9/")
    assert len(response.content) == 10


def test_video_missing_on_disk_at_stream_time_returns_404_not_a_crash(client, video_file, tmp_path):
    token = _login(client).json()["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(token), json={
        "video_path": video_file, "duration_seconds": 10.0,
    })
    access = client.get("/scenarios/vehicle_theft/video", headers=_bearer(token)).json()
    video_token = access["stream_url"].split("token=")[1]

    os.remove(video_file)  # Eng finding 2.5 — el archivo desaparece entre autoría y reproducción

    response = client.get("/scenarios/vehicle_theft/video/stream", params={"token": video_token})

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# ADR-0011 — gate de rol mínimo para adjuntar video al promover un incidente
# ---------------------------------------------------------------------------


def test_login_with_manager_passphrase_grants_the_manager_role(client):
    response = client.post(
        "/auth/login", json={"supervisor_id": "mgr-1", "passphrase": MANAGER_PASSPHRASE}
    )

    assert response.status_code == 200
    # El body de login expone el rol solo como pista de UI — la aplicación real vive en el
    # token (ver `_require_manager`), que un cliente no puede falsear.
    assert response.json()["role"] == "manager"


def test_login_with_supervisor_passphrase_reports_the_supervisor_role(client):
    response = client.post(
        "/auth/login", json={"supervisor_id": "sup-1", "passphrase": SUPERVISOR_PASSPHRASE}
    )

    assert response.json()["role"] == "supervisor"


def _create_incident(client, token):
    return client.post(
        "/incidents",
        headers=_bearer(token),
        json={
            "occurred_at": 1000.0,
            "supervisor_id": "sup-42",
            "outcome_rating": 3,
            "critical_data_captured": True,
            "protocol_followed": True,
            "notes": "Real robbery post-mortem.",
        },
    ).json()


def test_promoting_with_video_as_supervisor_is_forbidden(client, video_file):
    token = _login(client).json()["token"]
    incident = _create_incident(client, token)

    response = client.post(
        f"/incidents/{incident['id']}/promote-to-scenario",
        headers=_bearer(token),
        json={"video": {"video_path": video_file, "duration_seconds": 10.0}},
    )

    assert response.status_code == 403


def test_promoting_with_video_as_manager_succeeds(client, video_file):
    manager_token = _login(client, supervisor_id="mgr-1", passphrase=MANAGER_PASSPHRASE).json()["token"]
    supervisor_token = _login(client).json()["token"]
    incident = _create_incident(client, supervisor_token)

    response = client.post(
        f"/incidents/{incident['id']}/promote-to-scenario",
        headers=_bearer(manager_token),
        json={
            "video": {
                "video_path": video_file,
                "duration_seconds": 10.0,
                "ground_truth_points": [{"key": "x", "label": "X", "match_hints": ["knife"]}],
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["has_video"] is True


def test_promoting_without_video_still_works_for_a_plain_supervisor(client):
    # ADR-0011: promover SIN video no cambia de comportamiento — sigue sin chequeo de rol.
    token = _login(client).json()["token"]
    incident = _create_incident(client, token)

    response = client.post(f"/incidents/{incident['id']}/promote-to-scenario", headers=_bearer(token))

    assert response.status_code == 201
    assert response.json()["has_video"] is False


# ---------------------------------------------------------------------------
# Loop de llamada en vivo con video — video.ended, reacción, cobertura plegada
# ---------------------------------------------------------------------------


def test_full_call_with_video_folds_ground_truth_into_the_existing_evaluation(app_components, video_file):
    dispatcher = StubDispatcher([
        "911, what is your emergency?",
        "Anything else you can tell me?",
    ])
    stt = StubSTT(["The suspect was wearing a red jacket and fled on foot."])
    client = make_client(app_components, dispatcher=dispatcher, stt=stt)
    token_response = _login(client).json()

    setup_token = token_response["token"]
    client.put("/scenarios/vehicle_theft/video", headers=_bearer(setup_token), json={
        "video_path": video_file,
        "duration_seconds": 20.0,
        "ground_truth_points": [
            {
                "key": "suspect_clothing",
                "label": "Suspect clothing",
                "match_hints": ["red jacket"],
                "visible_from_seconds": 1.0,
                "visible_to_seconds": 5.0,
            },
        ],
    })

    with client.websocket_connect(
        f"/ws/session/{token_response['session_id']}?token={token_response['token']}"
    ) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

        ws.send_json({"command": "video.ended", "scenarioId": "vehicle_theft"})

        ws.send_json({
            "command": "call.start", "scenarioId": "vehicle_theft",
            "difficulty": "Medium", "language": "English", "trainingType": "Police",
        })
        _drain_until(ws, "call.started")
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "recording.start"})
        _drain_until(ws, "operator.speaking")
        ws.send_json({"command": "recording.stop"})
        _drain_until(ws, "transcript.operator")
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "call.end"})
        completed = _drain_until(ws, "session.completed")

    evaluation = completed["session"]["evaluation"]
    assert "Suspect clothing" in evaluation["collected"]
    assert "video_collected" not in evaluation  # plegado, no un panel/categoría paralela
    assert evaluation["video_reaction_seconds"] is not None
    assert evaluation["video_reaction_seconds"] >= 0


def test_call_without_a_video_scenario_has_no_reaction_metric(client):
    token_response = _login(client).json()

    with client.websocket_connect(
        f"/ws/session/{token_response['session_id']}?token={token_response['token']}"
    ) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_json()

        ws.send_json({
            "command": "call.start", "scenarioId": "vehicle_theft",
            "difficulty": "Medium", "language": "English", "trainingType": "Police",
        })
        _drain_until(ws, "call.started")
        _drain_until(ws, "transcript.dispatcher")

        ws.send_json({"command": "call.end"})
        completed = _drain_until(ws, "session.completed")

    assert completed["session"]["evaluation"]["video_reaction_seconds"] is None
