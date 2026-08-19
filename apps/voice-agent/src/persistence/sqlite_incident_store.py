"""Adaptador de persistencia de incidentes reales — roadmap Fase 3.

Implementa `IncidentOutcomePort` (ver `core/ports.py`) contra el mismo motor SQLite embebido de
ADR-0007. Mismo patrón que `SQLiteScenarioStore`/`SQLiteSessionStore`: una conexión por
operación, sin pool, sin capa de migraciones (no existe una todavía en este repo).
"""

import sqlite3
import time
import uuid
from contextlib import closing

from core.ports import IncidentOutcome, IncidentOutcomePort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incident_outcomes (
    id TEXT PRIMARY KEY,
    occurred_at REAL NOT NULL,
    supervisor_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    outcome_rating INTEGER NOT NULL,
    critical_data_captured INTEGER NOT NULL,
    protocol_followed INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    reported_by TEXT NOT NULL DEFAULT '',
    promoted_scenario_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
)
"""

_COLUMNS = (
    "id, occurred_at, supervisor_id, category, outcome_rating, critical_data_captured, "
    "protocol_followed, notes, reported_by, promoted_scenario_id, created_at"
)


class SQLiteIncidentStore(IncidentOutcomePort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def list(self) -> list[IncidentOutcome]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM incident_outcomes ORDER BY occurred_at DESC"
            ).fetchall()

        return [self._from_row(row) for row in rows]

    def get(self, incident_id: str) -> IncidentOutcome | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM incident_outcomes WHERE id = ?",
                (incident_id,),
            ).fetchone()

        return self._from_row(row) if row else None

    def create(self, incident: IncidentOutcome) -> None:
        if not incident.id:
            incident.id = str(uuid.uuid4())
        incident.created_at = incident.created_at or self._clock()

        with closing(self._connect()) as conn:
            conn.execute(
                f"""
                INSERT INTO incident_outcomes ({_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._to_row(incident),
            )
            conn.commit()

    def delete(self, incident_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM incident_outcomes WHERE id = ?", (incident_id,))
            conn.commit()

    def mark_promoted(self, incident_id: str, scenario_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE incident_outcomes SET promoted_scenario_id = ? WHERE id = ?",
                (scenario_id, incident_id),
            )
            conn.commit()

    @staticmethod
    def _to_row(incident: IncidentOutcome) -> tuple:
        return (
            incident.id,
            incident.occurred_at,
            incident.supervisor_id,
            incident.category,
            incident.outcome_rating,
            int(incident.critical_data_captured),
            int(incident.protocol_followed),
            incident.notes,
            incident.reported_by,
            incident.promoted_scenario_id,
            incident.created_at,
        )

    @staticmethod
    def _from_row(row) -> IncidentOutcome:
        return IncidentOutcome(
            id=row[0],
            occurred_at=row[1],
            supervisor_id=row[2],
            category=row[3],
            outcome_rating=row[4],
            critical_data_captured=bool(row[5]),
            protocol_followed=bool(row[6]),
            notes=row[7],
            reported_by=row[8],
            promoted_scenario_id=row[9],
            created_at=row[10],
        )
