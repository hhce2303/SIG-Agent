"""Adaptador de persistencia del video adjunto a un escenario — roadmap
docs/designs/escenarios-de-video.md, ver ADR-0009/ADR-0010.

Deliberadamente una TABLA NUEVA (`scenario_videos`), nunca una columna agregada a `scenarios`:
`CREATE TABLE IF NOT EXISTS` es un no-op contra una tabla que ya existe, y `sessions.db` ya tiene
datos reales de Gate 0 (ver TODO-20, docs/architecture/TODOS.md) — agregar una columna ahí
rompería en producción sin que ningún test lo detecte (cada test usa un `tmp_path` nuevo). Mismo
patrón que el resto de los stores: una conexión por operación, sin pool, sin migraciones (no
existe esa capa todavía en este repo).

Relación 1:1 con `Scenario` (PK = `scenario_id`) — el producto de v1 asocia como máximo un video
por escenario (varios "escenarios de video" distintos en la librería, no varios videos dentro de
uno). `video_path` se coloca manualmente en disco por quien administra el servidor (recorte de
alcance de v1 — sin endpoint de upload todavía, ver docs/designs/escenarios-de-video.md, "Scope
Decision"); este store no es dueño del ciclo de vida del archivo, solo de la referencia.
"""

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import asdict

from core.ports import ScenarioVideo, ScenarioVideoPort, VideoGroundTruthPoint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenario_videos (
    scenario_id TEXT PRIMARY KEY,
    video_path TEXT NOT NULL,
    video_checksum TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    content_type TEXT NOT NULL,
    ground_truth_points_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""


class SQLiteScenarioVideoStore(ScenarioVideoPort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get(self, scenario_id: str) -> ScenarioVideo | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT scenario_id, video_path, video_checksum, duration_seconds, content_type,
                       ground_truth_points_json, created_at, updated_at
                FROM scenario_videos
                WHERE scenario_id = ?
                """,
                (scenario_id,),
            ).fetchone()

        return self._from_row(row) if row else None

    def upsert(self, video: ScenarioVideo) -> None:
        now = self._clock()
        video.created_at = video.created_at or now
        video.updated_at = now

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO scenario_videos
                    (scenario_id, video_path, video_checksum, duration_seconds, content_type,
                     ground_truth_points_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    video_path = excluded.video_path,
                    video_checksum = excluded.video_checksum,
                    duration_seconds = excluded.duration_seconds,
                    content_type = excluded.content_type,
                    ground_truth_points_json = excluded.ground_truth_points_json,
                    updated_at = excluded.updated_at
                """,
                self._to_row(video),
            )
            conn.commit()

    def delete(self, scenario_id: str) -> None:
        # Solo borra la fila de referencia — el archivo en disco no es propiedad de este store
        # en v1 (ver docstring del módulo). Si el archivo se elimina físicamente, `get()` sigue
        # devolviendo la referencia (server/app.py la trata como "video ausente en disco" al
        # momento de servir, no acá).
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM scenario_videos WHERE scenario_id = ?", (scenario_id,))
            conn.commit()

    @staticmethod
    def _to_row(video: ScenarioVideo) -> tuple:
        return (
            video.scenario_id,
            video.video_path,
            video.video_checksum,
            video.duration_seconds,
            video.content_type,
            json.dumps([asdict(point) for point in video.ground_truth_points]),
            video.created_at,
            video.updated_at,
        )

    @staticmethod
    def _from_row(row) -> ScenarioVideo:
        return ScenarioVideo(
            scenario_id=row[0],
            video_path=row[1],
            video_checksum=row[2],
            duration_seconds=row[3],
            content_type=row[4],
            ground_truth_points=[VideoGroundTruthPoint(**point) for point in json.loads(row[5])],
            created_at=row[6],
            updated_at=row[7],
        )
