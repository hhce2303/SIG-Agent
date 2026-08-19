"""Logging estructurado con id de correlación — NFR-08.

`log_event` toma el id de correlación como parámetro explícito (el `session_id` de la conexión,
normalmente) en vez de guardarlo en una variable global/contextvar implícita: quien llama
siempre lo tiene a mano, y explícito es más simple de seguir y de probar que magia de contexto
compartido entre corrutinas concurrentes.

Dominio puro (sin FastAPI) — cualquier capa puede usar `log_event`, no solo el servidor.
"""

import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    """Un log por línea, en JSON — pensado para ingestión por una herramienta de logs, no para
    lectura humana directa en la terminal."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))

        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Reemplaza los handlers del root logger por uno que emite JSON a stdout. Llamar una vez
    al arrancar el proceso (ver `server_main.py`) — los tests configuran sus propios loggers/
    `caplog`, no llaman a esto."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(
    logger: logging.Logger,
    message: str,
    correlation_id: str | None = None,
    **fields,
) -> None:
    """Log estructurado: `message` es el nombre del evento (ej. "turn_transition"), el resto
    son campos libres. Van dentro de `extra={"fields": ...}` en vez de sueltos como kwargs de
    `extra=` porque `logging` reserva varios nombres de atributo de `LogRecord` (`message`,
    `args`, `name`, ...) y pisar uno de esos por accidente rompe el logging en producción, no
    en el momento de escribir el código."""

    logger.info(message, extra={"fields": {"correlation_id": correlation_id, **fields}})
