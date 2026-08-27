"""Regresión de topología compartida — descubierta durante la revisión de ingeniería de
docs/designs/escenarios-de-video.md (hallazgo 3.2), independiente del feature de video en sí.

`server_main.py::build_app` apunta los SIETE stores (scenario/session/settings/incident/video/
stt-metrics/location — el séptimo agregado por docs/designs/ubicacion-del-incidente.md, tras el
sexto de T4 en motor-de-metricas.md) al mismo archivo SQLite, cada uno con su propia conexión por
operación y sin `busy_timeout` configurado en ningún `sqlite3.connect()` — riesgo pre-existente,
documentado en TODO-20, no introducido por ninguno de estos features. Ningún test existente
ejercitaba esa topología real — cada test de store usa su propio `tmp_path` privado. Este test abre
los siete contra UN archivo compartido y los golpea concurrentemente, para confirmar que no
aparece `sqlite3.OperationalError: database is locked`.
"""

import threading

from core.ports import (
    CriticalDataPoint,
    IncidentOutcome,
    Scenario,
    ScenarioLocation,
    ScenarioVideo,
    SessionRecord,
    SttSegment,
)
from persistence.sqlite_incident_store import SQLiteIncidentStore
from persistence.sqlite_scenario_location_store import SQLiteScenarioLocationStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore
from persistence.sqlite_scenario_video_store import SQLiteScenarioVideoStore
from persistence.sqlite_settings_store import SQLiteSettingsStore
from persistence.sqlite_store import SQLiteSessionStore
from persistence.sqlite_stt_metrics_store import SQLiteSttMetricsStore


def test_seven_stores_on_one_shared_file_survive_concurrent_writes(tmp_path):
    shared_db_path = str(tmp_path / "sessions.db")

    scenario_store = SQLiteScenarioStore(shared_db_path)
    session_store = SQLiteSessionStore(shared_db_path)
    settings_store = SQLiteSettingsStore(shared_db_path)
    incident_store = SQLiteIncidentStore(shared_db_path)
    video_store = SQLiteScenarioVideoStore(shared_db_path)
    stt_metrics_store = SQLiteSttMetricsStore(shared_db_path)
    location_store = SQLiteScenarioLocationStore(shared_db_path)

    errors: list[Exception] = []
    errors_lock = threading.Lock()

    def _run(fn):
        try:
            fn()
        except Exception as error:  # noqa: BLE001 — se quiere capturar CUALQUIER excepción real
            with errors_lock:
                errors.append(error)

    def write_scenarios():
        for i in range(20):
            scenario_store.create(Scenario(
                id="", title=f"Scenario {i}", category="Police", difficulty="Easy",
                language="English", description="d", briefing="b",
                critical_data_points=[CriticalDataPoint(key="x", label="X")],
            ))

    def write_sessions():
        for i in range(20):
            session_store.save_session(SessionRecord(
                session_id=f"sess-{i}", supervisor_id="sup-1", scenario_name="vehicle_theft",
                started_at=1000.0 + i, ended_at=1010.0 + i, outcome="ended",
            ))

    def write_settings():
        for i in range(20):
            settings_store.set_tts_voice("am_michael" if i % 2 == 0 else "af_bella")

    def write_incidents():
        for i in range(20):
            incident_store.create(IncidentOutcome(
                id="", occurred_at=1000.0 + i, supervisor_id="sup-1", category="theft",
                outcome_rating=3, critical_data_captured=True, protocol_followed=True,
            ))

    def write_videos():
        for i in range(20):
            video_store.upsert(ScenarioVideo(
                scenario_id=f"video-scenario-{i}", video_path=f"/videos/{i}.mp4",
                video_checksum=f"checksum-{i}", duration_seconds=30.0, content_type="video/mp4",
            ))

    def write_stt_metrics():
        for i in range(20):
            stt_metrics_store.save_segments(f"sess-{i}", [
                SttSegment(
                    text="a segment", avg_logprob=-0.2, no_speech_prob=0.05,
                    compression_ratio=1.0, start_seconds=0.0, end_seconds=1.0,
                ),
            ])

    def write_locations():
        for i in range(20):
            location_store.upsert(ScenarioLocation(
                scenario_id=f"location-scenario-{i}", street=f"{i}th Avenue",
                cross_street="Main Street",
            ))

    threads = [
        threading.Thread(target=_run, args=(fn,))
        for fn in (
            write_scenarios, write_sessions, write_settings, write_incidents,
            write_videos, write_stt_metrics, write_locations,
        )
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"concurrent writes against the shared file raised: {errors}"
    assert len(session_store.list_sessions("sup-1")) == 20
    assert len(incident_store.list()) == 20
