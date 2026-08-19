"""Adaptador de persistencia — SQLite embebido (ADR-0007, accepted 2026-08-19).

Implementa `PersistencePort` (ver `core/ports.py`) contra un archivo SQLite local. El dominio
no importa este módulo directamente (ADR-0006) — algo por encima (el server, todavía sin
construir) decide qué implementación de `PersistencePort` usar.
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
    started_at REAL NOT NULL,
    ended_at REAL,
    turns_json TEXT NOT NULL
)
"""


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
                """
                INSERT INTO sessions
                    (session_id, supervisor_id, scenario_name, started_at, ended_at, turns_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    ended_at = excluded.ended_at,
                    turns_json = excluded.turns_json
                """,
                (
                    session.session_id,
                    session.supervisor_id,
                    session.scenario_name,
                    session.started_at,
                    session.ended_at,
                    json.dumps(session.turns),
                ),
            )
            conn.commit()

    def get_session(self, session_id: str) -> SessionRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT session_id, supervisor_id, scenario_name, started_at, ended_at, turns_json
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        return SessionRecord(
            session_id=row[0],
            supervisor_id=row[1],
            scenario_name=row[2],
            started_at=row[3],
            ended_at=row[4],
            turns=json.loads(row[5]),
        )
