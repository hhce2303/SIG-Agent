"""Unit tests de logging estructurado (NFR-08)."""

import json
import logging
from unittest.mock import patch

import pytest

from core.observability import JsonFormatter, configure_logging, log_event


def test_log_event_attaches_correlation_id_and_extra_fields_to_the_record(caplog):
    logger = logging.getLogger("test.observability")

    with caplog.at_level(logging.INFO, logger="test.observability"):
        log_event(logger, "turn_transition", correlation_id="sess-1", event="x", latency_ms=42)

    record = caplog.records[0]
    assert record.message == "turn_transition"
    assert record.fields == {
        "correlation_id": "sess-1",
        "event": "x",
        "latency_ms": 42,
    }


def test_log_event_allows_no_correlation_id(caplog):
    logger = logging.getLogger("test.observability")

    with caplog.at_level(logging.INFO, logger="test.observability"):
        log_event(logger, "login_failed", supervisor_id="sup-42")

    assert caplog.records[0].fields == {"correlation_id": None, "supervisor_id": "sup-42"}


def test_json_formatter_produces_one_json_object_per_record():
    logger = logging.getLogger("test.observability.formatter")
    record = logger.makeRecord(
        name="test.observability.formatter",
        level=logging.INFO,
        fn="",
        lno=0,
        msg="session_connected",
        args=(),
        exc_info=None,
        extra={"fields": {"correlation_id": "sess-1", "supervisor_id": "sup-42"}},
    )

    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)

    assert payload["message"] == "session_connected"
    assert payload["level"] == "INFO"
    assert payload["correlation_id"] == "sess-1"
    assert payload["supervisor_id"] == "sup-42"


def test_json_formatter_handles_a_record_with_no_extra_fields():
    logger = logging.getLogger("test.observability.formatter")
    record = logger.makeRecord(
        name="test.observability.formatter",
        level=logging.WARNING,
        fn="",
        lno=0,
        msg="plain message, no log_event",
        args=(),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "plain message, no log_event"
    assert payload["level"] == "WARNING"


class TestConfigureLoggingFileHandler:
    """docs/designs/empaquetado-ejecutable-backend.md, Premisa 8 -- diagnóstico de campo: log a
    archivo además de stdout, con fallback silencioso si no se puede escribir."""

    def teardown_method(self):
        # `configure_logging` reemplaza los handlers del root logger -- dejarlo limpio para no
        # filtrar handlers con archivos abiertos a otros tests del módulo.
        logging.getLogger().handlers = []

    def test_writes_a_log_line_to_the_file_when_log_dir_is_given(self, tmp_path):
        configure_logging(log_dir=str(tmp_path))
        logging.getLogger("test.observability.file").info("server started")

        log_file = tmp_path / "server.log"
        assert log_file.exists()
        assert "server started" in log_file.read_text()

    def test_falls_back_to_stdout_only_when_log_dir_is_not_writable(self, tmp_path):
        """Disco lleno / permisos bloqueados (Premisa 8) -- una app corriendo sin log de
        archivo es mejor que ninguna app; `configure_logging` NUNCA debe lanzar."""
        with patch(
            "core.observability.logging.handlers.RotatingFileHandler",
            side_effect=OSError("permission denied"),
        ):
            configure_logging(log_dir=str(tmp_path))  # no debe lanzar

        root = logging.getLogger()
        assert len(root.handlers) == 1  # solo el StreamHandler de stdout sobrevive
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_no_file_handler_when_log_dir_is_none(self):
        configure_logging(log_dir=None)

        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)
