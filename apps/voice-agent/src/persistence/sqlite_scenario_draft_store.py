"""Adaptador de persistencia de borradores de escenario — ver ADR-0014.

Implementa `ScenarioDraftStorePort` (`core/ports.py`) contra el mismo motor SQLite embebido de
ADR-0007. Mismo patrón que `SQLiteIncidentStore`/`SQLiteScenarioStore`: una conexión por
operación, sin pool, sin capa de migraciones (no existe una todavía en este repo).
"""

import json
import sqlite3
import time
import uuid
from contextlib import closing

from core.ports import CriticalDataPoint, ScenarioDraft, ScenarioDraftStorePort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenario_drafts (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    language TEXT NOT NULL,
    description TEXT NOT NULL,
    briefing TEXT NOT NULL,
    critical_data_points_json TEXT NOT NULL,
    missing_information_json TEXT NOT NULL,
    raw_response TEXT NOT NULL DEFAULT '',
    approved_scenario_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""

_COLUMNS = (
    "id, incident_id, status, title, category, difficulty, language, description, briefing, "
    "critical_data_points_json, missing_information_json, raw_response, approved_scenario_id, "
    "created_at, updated_at"
)


class SQLiteScenarioDraftStore(ScenarioDraftStorePort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def create(self, draft: ScenarioDraft) -> None:
        if not draft.id:
            draft.id = str(uuid.uuid4())
        now = self._clock()
        draft.created_at = draft.created_at or now
        draft.updated_at = now

        with closing(self._connect()) as conn:
            conn.execute(
                f"INSERT INTO scenario_drafts ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._to_row(draft),
            )
            conn.commit()

    def get(self, draft_id: str) -> ScenarioDraft | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM scenario_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def get_pending_for_incident(self, incident_id: str) -> ScenarioDraft | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM scenario_drafts "
                "WHERE incident_id = ? AND status = 'pending'",
                (incident_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[ScenarioDraft]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM scenario_drafts ORDER BY created_at DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(self, draft: ScenarioDraft) -> None:
        draft.updated_at = self._clock()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE scenario_drafts SET
                    status = ?, title = ?, category = ?, difficulty = ?, language = ?,
                    description = ?, briefing = ?, critical_data_points_json = ?,
                    missing_information_json = ?, approved_scenario_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    draft.status,
                    draft.title,
                    draft.category,
                    draft.difficulty,
                    draft.language,
                    draft.description,
                    draft.briefing,
                    json.dumps([p.__dict__ for p in draft.critical_data_points]),
                    json.dumps(draft.missing_information),
                    draft.approved_scenario_id,
                    draft.updated_at,
                    draft.id,
                ),
            )
            conn.commit()

    def mark_approved(self, draft_id: str, scenario_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE scenario_drafts SET status = 'approved', approved_scenario_id = ?, "
                "updated_at = ? WHERE id = ?",
                (scenario_id, self._clock(), draft_id),
            )
            conn.commit()

    def mark_rejected(self, draft_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE scenario_drafts SET status = 'rejected', updated_at = ? WHERE id = ?",
                (self._clock(), draft_id),
            )
            conn.commit()

    @staticmethod
    def _to_row(draft: ScenarioDraft) -> tuple:
        return (
            draft.id,
            draft.incident_id,
            draft.status,
            draft.title,
            draft.category,
            draft.difficulty,
            draft.language,
            draft.description,
            draft.briefing,
            json.dumps([p.__dict__ for p in draft.critical_data_points]),
            json.dumps(draft.missing_information),
            draft.raw_response,
            draft.approved_scenario_id,
            draft.created_at,
            draft.updated_at,
        )

    @staticmethod
    def _from_row(row) -> ScenarioDraft:
        return ScenarioDraft(
            id=row[0],
            incident_id=row[1],
            status=row[2],
            title=row[3],
            category=row[4],
            difficulty=row[5],
            language=row[6],
            description=row[7],
            briefing=row[8],
            critical_data_points=[CriticalDataPoint(**p) for p in json.loads(row[9])],
            missing_information=json.loads(row[10]),
            raw_response=row[11],
            approved_scenario_id=row[12],
            created_at=row[13],
            updated_at=row[14],
        )
