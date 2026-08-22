"""Adaptador de persistencia del detalle por-segmento de confianza de Whisper — motor de
métricas, docs/designs/motor-de-metricas.md (T4).

Deliberadamente una TABLA NUEVA (`stt_turn_metrics`), nunca una columna agregada a `sessions`:
mismo motivo que `sqlite_scenario_video_store.py` (`TODO-20`, `docs/architecture/TODOS.md`) —
`sessions.db` ya tiene datos reales, `CREATE TABLE IF NOT EXISTS` es seguro contra eso,
`ALTER TABLE` no lo es. Una conexión por operación, sin pool, sin migraciones — mismo patrón que
el resto de los stores de este repo.

**Riesgo aceptado, documentado a propósito (hallazgo de la voz independiente de ingeniería en la
revisión de `/autoplan`, Fase 3 Sección 1/5):** esta escritura y la de `evaluation_json` en
`sessions` (`sqlite_store.py`) NO son atómicas entre sí — son 2 conexiones SQLite separadas, sin
transacción compartida, porque ningún store de este repo tiene ese mecanismo todavía. Si el
proceso muere entre las dos escrituras, puede quedar detalle de segmento sin su
`evaluation_json` correspondiente (o viceversa). Es una ventana angosta (escrituras SQLite son
rápidas) y no es peor que el resto de este repo (ningún store tiene transacciones cross-store
hoy) — se documenta en vez de resolverse en esta pasada, ver `docs/architecture/TODOS.md`.
"""

import sqlite3
import time
from contextlib import closing

from core.ports import SttMetricsPort, SttSegment

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stt_turn_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    avg_logprob REAL NOT NULL,
    no_speech_prob REAL NOT NULL,
    compression_ratio REAL NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    is_low_confidence INTEGER NOT NULL,
    created_at REAL NOT NULL
)
"""

_INDEX = "CREATE INDEX IF NOT EXISTS idx_stt_turn_metrics_session_id ON stt_turn_metrics(session_id)"


class SQLiteSttMetricsStore(SttMetricsPort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.execute(_INDEX)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save_segments(self, session_id: str, segments: list[SttSegment]) -> None:
        if not segments:
            return

        created_at = self._clock()
        with closing(self._connect()) as conn:
            conn.executemany(
                """
                INSERT INTO stt_turn_metrics (
                    session_id, segment_index, text, avg_logprob, no_speech_prob,
                    compression_ratio, start_seconds, end_seconds, is_low_confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        index,
                        segment.text,
                        segment.avg_logprob,
                        segment.no_speech_prob,
                        segment.compression_ratio,
                        segment.start_seconds,
                        segment.end_seconds,
                        int(segment.is_low_confidence),
                        created_at,
                    )
                    for index, segment in enumerate(segments)
                ],
            )
            conn.commit()

    def get_segments(self, session_id: str) -> list[SttSegment]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT text, avg_logprob, no_speech_prob, compression_ratio,
                       start_seconds, end_seconds, is_low_confidence
                FROM stt_turn_metrics
                WHERE session_id = ?
                ORDER BY segment_index ASC
                """,
                (session_id,),
            ).fetchall()

        return [
            SttSegment(
                text=row[0],
                avg_logprob=row[1],
                no_speech_prob=row[2],
                compression_ratio=row[3],
                start_seconds=row[4],
                end_seconds=row[5],
                is_low_confidence=bool(row[6]),
            )
            for row in rows
        ]
