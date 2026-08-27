"""Adaptador de persistencia de la ubicación del incidente adjunta a un escenario — roadmap
docs/designs/ubicacion-del-incidente.md (autoplan 2026-08-21/22).

Deliberadamente una TABLA NUEVA (`scenario_locations`), nunca una columna agregada a `scenarios`:
mismo razonamiento que `sqlite_scenario_video_store.py` (TODO-20, docs/architecture/TODOS.md) —
`CREATE TABLE IF NOT EXISTS` es un no-op contra una tabla que ya existe, y `sessions.db` ya tiene
datos reales de Gate 0. Mismo patrón que el resto de los stores: una conexión por operación, sin
pool, sin migraciones, `clock` inyectable para tests deterministas.

Relación 1:1 con `Scenario` (PK = `scenario_id`) — un solo punto de interés por escenario (el
soporte de múltiples marcadores, ej. ruta de escape, queda diferido a TODOS.md, fuera del pedido
original que habla de "la ubicación del suceso" en singular).
"""

import json
import sqlite3
import time
from contextlib import closing

from core.ports import ScenarioLocation, ScenarioLocationPort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenario_locations (
    scenario_id TEXT PRIMARY KEY,
    street TEXT NOT NULL DEFAULT '',
    cross_street TEXT NOT NULL DEFAULT '',
    landmark TEXT NOT NULL DEFAULT '',
    city_or_zone TEXT NOT NULL DEFAULT '',
    additional_directions TEXT NOT NULL DEFAULT '',
    match_hints_json TEXT NOT NULL DEFAULT '[]',
    marker_x REAL,
    marker_y REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""


class SQLiteScenarioLocationStore(ScenarioLocationPort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get(self, scenario_id: str) -> ScenarioLocation | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT scenario_id, street, cross_street, landmark, city_or_zone,
                       additional_directions, match_hints_json, marker_x, marker_y,
                       created_at, updated_at
                FROM scenario_locations
                WHERE scenario_id = ?
                """,
                (scenario_id,),
            ).fetchone()

        return self._from_row(row) if row else None

    def upsert(self, location: ScenarioLocation) -> None:
        now = self._clock()
        location.created_at = location.created_at or now
        location.updated_at = now

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO scenario_locations
                    (scenario_id, street, cross_street, landmark, city_or_zone,
                     additional_directions, match_hints_json, marker_x, marker_y,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    street = excluded.street,
                    cross_street = excluded.cross_street,
                    landmark = excluded.landmark,
                    city_or_zone = excluded.city_or_zone,
                    additional_directions = excluded.additional_directions,
                    match_hints_json = excluded.match_hints_json,
                    marker_x = excluded.marker_x,
                    marker_y = excluded.marker_y,
                    updated_at = excluded.updated_at
                """,
                self._to_row(location),
            )
            conn.commit()

    def delete(self, scenario_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM scenario_locations WHERE scenario_id = ?", (scenario_id,))
            conn.commit()

    @staticmethod
    def _to_row(location: ScenarioLocation) -> tuple:
        return (
            location.scenario_id,
            location.street,
            location.cross_street,
            location.landmark,
            location.city_or_zone,
            location.additional_directions,
            json.dumps(location.match_hints),
            location.marker_x,
            location.marker_y,
            location.created_at,
            location.updated_at,
        )

    @staticmethod
    def _from_row(row) -> ScenarioLocation:
        return ScenarioLocation(
            scenario_id=row[0],
            street=row[1],
            cross_street=row[2],
            landmark=row[3],
            city_or_zone=row[4],
            additional_directions=row[5],
            match_hints=json.loads(row[6]),
            marker_x=row[7],
            marker_y=row[8],
            created_at=row[9],
            updated_at=row[10],
        )
