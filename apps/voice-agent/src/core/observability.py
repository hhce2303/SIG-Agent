"""Logging estructurado con id de correlación — NFR-08.

`log_event` toma el id de correlación como parámetro explícito (el `session_id` de la conexión,
normalmente) en vez de guardarlo en una variable global/contextvar implícita: quien llama
siempre lo tiene a mano, y explícito es más simple de seguir y de probar que magia de contexto
compartido entre corrutinas concurrentes.

Dominio puro (sin FastAPI) — cualquier capa puede usar `log_event`, no solo el servidor.
"""

import json
import logging
import logging.handlers
import os
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


def configure_logging(level: int = logging.INFO, log_dir: str | None = None) -> None:
    """Reemplaza los handlers del root logger. Llamar una vez al arrancar el proceso (ver
    `server_main.py`) — los tests configuran sus propios loggers/`caplog`, no llaman a esto.

    `log_dir` (docs/designs/empaquetado-ejecutable-backend.md, Premisa 8 — diagnóstico de campo):
    si se pasa, agrega un `RotatingFileHandler` que escribe a `<log_dir>/server.log`. En un
    `.exe` de doble-click sin consola visible (`console=False` en el `.spec`), el stdout de hoy
    se pierde por completo — este handler es lo que permite mandar `logs/` para diagnosticar en
    vez de nada. Guardrail: nunca loguear el valor de un secreto
    (`ANTHROPIC_API_KEY`/`SESSION_TOKEN_SECRET`/`SUPERVISOR_PASSPHRASE`/`MANAGER_PASSPHRASE`) —
    hoy nada lo hace, pero no hay ningún chequeo automático que lo impida si alguien agrega un
    log line de debug más adelante; quien toque este módulo debe mantener esa disciplina a mano.
    """

    handlers: list[logging.Handler] = []

    # Guard `sys.stdout is not None`: bajo un build de PyInstaller con `console=False`,
    # `sys.stdout` puede ser `None` — pasarlo explícito a `StreamHandler(None)` no cae a stderr
    # como cuando se omite el argumento, así que esas líneas se perderían en silencio por cada
    # log line en vez de simplemente no agregar el handler.
    if sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(JsonFormatter())
        handlers.append(stream_handler)

    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "server.log"),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(JsonFormatter())
            handlers.append(file_handler)
        except OSError:
            # Disco lleno, permisos bloqueados en una máquina de concesionario endurecida —
            # una app corriendo sin log de archivo es mejor que ninguna app (Premisa 8).
            pass

    root = logging.getLogger()
    root.handlers = handlers
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
