"""Adaptador de persistencia — SQLite embebido (ADR-0007, accepted 2026-08-19).

Implementa `PersistencePort` (ver `core/ports.py`) contra un archivo SQLite local. El dominio
no importa este módulo directamente (ADR-0006) — algo por encima (el server) decide qué
implementación de `PersistencePort` usar.

Fase 2 amplía el esquema (`scenario_id`, `transcript_json`, `evaluation_json`, `outcome`) y
agrega `list_sessions` (necesario para el historial — ADR-0007 ya anticipó esto: "el motor de
métricas de Fase 2 va a necesitar queries que archivos planos no dan"). Sin capa de migraciones
todavía (no existe una en este repo y `sessions.db` es de desarrollo, gitignored, sin datos
reales que preservar) — el DDL se recrea completo en vez de un `ALTER TABLE` incremental.
"""

import json
import sqlite3
from contextlib import closing

from core.ports import PersistencePort, SessionRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    supervisor_id TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    scenario_id TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    ended_at REAL,
    turns_json TEXT NOT NULL,
    transcript_json TEXT NOT NULL DEFAULT '[]',
    evaluation_json TEXT,
    outcome TEXT NOT NULL DEFAULT 'ended',
    difficulty TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    training_type TEXT NOT NULL DEFAULT ''
)
"""

_COLUMNS = (
    "session_id, supervisor_id, scenario_name, scenario_id, started_at, ended_at, "
    "turns_json, transcript_json, evaluation_json, outcome, difficulty, language, training_type"
)


class SQLiteSessionStore(PersistencePort):

    def __init__(self, db_path: str):
        self.db_path = db_path

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save_session(self, session: SessionRecord) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                f"""
                INSERT INTO sessions ({_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    ended_at = excluded.ended_at,
                    turns_json = excluded.turns_json,
                    transcript_json = excluded.transcript_json,
                    evaluation_json = excluded.evaluation_json,
                    outcome = excluded.outcome,
                    difficulty = excluded.difficulty,
                    language = excluded.language,
                    training_type = excluded.training_type
                """,
                self._to_row(session),
            )
            conn.commit()

    def get_session(self, session_id: str) -> SessionRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        return self._from_row(row) if row else None

    def list_sessions(self, supervisor_id: str) -> list[SessionRecord]:
        # Visibilidad self-only (decisión del usuario, roadmap Fase 2/NFR-06): siempre se
        # scopea por el `supervisor_id` del token verificado, nunca por uno provisto por el
        # cliente — quien llama a esto es responsable de pasar `claims.supervisor_id`.
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT {_COLUMNS} FROM sessions
                WHERE supervisor_id = ?
                ORDER BY started_at DESC
                """,
                (supervisor_id,),
            ).fetchall()

        return [self._from_row(row) for row in rows]

    @staticmethod
    def _to_row(session: SessionRecord) -> tuple:
        return (
            session.session_id,
            session.supervisor_id,
            session.scenario_name,
            session.scenario_id,
            session.started_at,
            session.ended_at,
            json.dumps(session.turns),
            json.dumps(session.transcript),
            json.dumps(session.evaluation) if session.evaluation is not None else None,
            session.outcome,
            session.difficulty,
            session.language,
            session.training_type,
        )

    @staticmethod
    def _from_row(row) -> SessionRecord:
        return SessionRecord(
            session_id=row[0],
            supervisor_id=row[1],
            scenario_name=row[2],
            scenario_id=row[3],
            started_at=row[4],
            ended_at=row[5],
            turns=json.loads(row[6]),
            transcript=json.loads(row[7]),
            evaluation=json.loads(row[8]) if row[8] is not None else None,
            outcome=row[9],
            difficulty=row[10],
            language=row[11],
            training_type=row[12],
        )
