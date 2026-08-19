"""Adaptador de persistencia de ajustes — roadmap Fase 2 ("la pieza más chica").

Implementa `SettingsPort` (ver `core/ports.py`). Una tabla clave-valor de una sola fila lógica
(concurrencia=1, NFR-11 — no hay ajustes por supervisor todavía) contra el mismo SQLite embebido
de ADR-0007. Alcance mínimo a propósito: hoy solo `tts_voice`.
"""

import sqlite3
from contextlib import closing

from core.ports import DEFAULT_TTS_VOICE, SettingsPort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_TTS_VOICE_KEY = "tts_voice"


class SQLiteSettingsStore(SettingsPort):

    def __init__(self, db_path: str):
        self.db_path = db_path

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_tts_voice(self) -> str:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (_TTS_VOICE_KEY,)
            ).fetchone()

        return row[0] if row else DEFAULT_TTS_VOICE

    def set_tts_voice(self, voice: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (_TTS_VOICE_KEY, voice),
            )
            conn.commit()
