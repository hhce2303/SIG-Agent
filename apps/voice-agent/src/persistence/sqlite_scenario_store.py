"""Adaptador de persistencia de escenarios — roadmap Fase 2 (TODO-11 resuelto).

Implementa `ScenarioPort` (ver `core/ports.py`) contra el mismo motor SQLite embebido de
ADR-0007. Mismo patrón que `SQLiteSessionStore`: una conexión por operación, sin pool, sin
capa de migraciones (no existe una todavía en este repo, y no hay datos reales de escenarios
que migrar).

Sembrado inicial: el `SCENARIO` string original de `scenarios/vehicle_theft.py` se mantiene tal
cual para el prototipo CLI (NFR-03, `main.py` sigue importándolo directo) — acá se migra su
contenido a la forma estructurada nueva, más dos escenarios adicionales (roadmap Fase 2: "más de
un tipo de incidente además de robo de vehículo"), usando los mismos IDs que ya existía como
`fallbackScenarios` en `frontend/src/stores/engineStore.ts` para no romper esa referencia.
"""

import json
import sqlite3
import time
import uuid
from contextlib import closing

from core.ports import CriticalDataPoint, Scenario, ScenarioPort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    language TEXT NOT NULL,
    description TEXT NOT NULL,
    briefing TEXT NOT NULL,
    critical_data_points_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""


def _seed_scenarios(now: float) -> list[Scenario]:
    return [
        Scenario(
            id="vehicle_theft",
            title="Vehicle Theft",
            category="Police",
            difficulty="Medium",
            language="English",
            description="Report a recently stolen vehicle.",
            briefing=(
                "A caller is reporting a stolen vehicle.\n\n"
                "Vehicle:\n"
                "- 2021 Toyota Camry\n"
                "- White\n"
                "- License plate: ABC123\n\n"
                "Incident:\n"
                "- The vehicle was last seen approximately two hours ago.\n"
                "- It was parked near a shopping center.\n"
                "- The caller is currently at home."
            ),
            critical_data_points=[
                CriticalDataPoint(key="incident_description", label="What happened"),
                CriticalDataPoint(key="vehicle_description", label="Vehicle description"),
                CriticalDataPoint(key="license_plate", label="License plate"),
                CriticalDataPoint(key="last_location", label="Last known location"),
                CriticalDataPoint(key="approx_time", label="Approximate time"),
                CriticalDataPoint(key="caller_info", label="Caller information"),
            ],
            created_at=now,
            updated_at=now,
        ),
        Scenario(
            id="domestic_dispute",
            title="Domestic Dispute",
            category="Police",
            difficulty="Hard",
            language="English",
            description="Handle an active domestic disturbance.",
            briefing=(
                "A caller is reporting an active domestic disturbance at their residence.\n\n"
                "Situation:\n"
                "- Loud arguing and a possible physical altercation next door.\n"
                "- The caller is not directly involved but can hear it clearly.\n"
                "- It is unclear if anyone is injured or if weapons are involved.\n\n"
                "The caller is anxious and speaking quickly."
            ),
            critical_data_points=[
                CriticalDataPoint(key="incident_description", label="What is happening right now"),
                CriticalDataPoint(key="address", label="Address of the disturbance"),
                CriticalDataPoint(key="injuries", label="Whether anyone is injured"),
                CriticalDataPoint(key="weapons", label="Whether weapons are involved"),
                CriticalDataPoint(key="people_involved", label="Number of people involved"),
                CriticalDataPoint(key="caller_info", label="Caller information"),
            ],
            created_at=now,
            updated_at=now,
        ),
        Scenario(
            id="traffic_accident",
            title="Traffic Accident",
            category="Police / EMS",
            difficulty="Medium",
            language="English",
            description="Report a collision with a possible injury.",
            briefing=(
                "A caller is reporting a two-vehicle traffic collision.\n\n"
                "Incident:\n"
                "- Collision at a busy intersection a few minutes ago.\n"
                "- At least one driver reports neck pain.\n"
                "- Both vehicles are blocking a traffic lane.\n\n"
                "The caller is one of the drivers involved."
            ),
            critical_data_points=[
                CriticalDataPoint(key="incident_description", label="What happened"),
                CriticalDataPoint(key="location", label="Exact location / intersection"),
                CriticalDataPoint(key="injuries", label="Whether anyone is injured"),
                CriticalDataPoint(key="vehicles_involved", label="Number of vehicles involved"),
                CriticalDataPoint(key="road_blocked", label="Whether the road is blocked"),
                CriticalDataPoint(key="caller_info", label="Caller information"),
            ],
            created_at=now,
            updated_at=now,
        ),
    ]


class SQLiteScenarioStore(ScenarioPort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

        if not self.list():
            for scenario in _seed_scenarios(self._clock()):
                self.create(scenario)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def list(self) -> list[Scenario]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, title, category, difficulty, language, description, briefing,
                       critical_data_points_json, created_at, updated_at
                FROM scenarios
                ORDER BY created_at ASC
                """
            ).fetchall()

        return [self._from_row(row) for row in rows]

    def get(self, scenario_id: str) -> Scenario | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT id, title, category, difficulty, language, description, briefing,
                       critical_data_points_json, created_at, updated_at
                FROM scenarios
                WHERE id = ?
                """,
                (scenario_id,),
            ).fetchone()

        return self._from_row(row) if row else None

    def create(self, scenario: Scenario) -> None:
        if not scenario.id:
            scenario.id = str(uuid.uuid4())

        now = self._clock()
        scenario.created_at = scenario.created_at or now
        scenario.updated_at = now

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO scenarios
                    (id, title, category, difficulty, language, description, briefing,
                     critical_data_points_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._to_row(scenario),
            )
            conn.commit()

    def update(self, scenario: Scenario) -> None:
        scenario.updated_at = self._clock()

        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE scenarios SET
                    title = ?, category = ?, difficulty = ?, language = ?, description = ?,
                    briefing = ?, critical_data_points_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    scenario.title,
                    scenario.category,
                    scenario.difficulty,
                    scenario.language,
                    scenario.description,
                    scenario.briefing,
                    json.dumps([point.__dict__ for point in scenario.critical_data_points]),
                    scenario.updated_at,
                    scenario.id,
                ),
            )
            conn.commit()

    def delete(self, scenario_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
            conn.commit()

    @staticmethod
    def _to_row(scenario: Scenario) -> tuple:
        return (
            scenario.id,
            scenario.title,
            scenario.category,
            scenario.difficulty,
            scenario.language,
            scenario.description,
            scenario.briefing,
            json.dumps([point.__dict__ for point in scenario.critical_data_points]),
            scenario.created_at,
            scenario.updated_at,
        )

    @staticmethod
    def _from_row(row) -> Scenario:
        return Scenario(
            id=row[0],
            title=row[1],
            category=row[2],
            difficulty=row[3],
            language=row[4],
            description=row[5],
            briefing=row[6],
            critical_data_points=[CriticalDataPoint(**point) for point in json.loads(row[7])],
            created_at=row[8],
            updated_at=row[9],
        )
