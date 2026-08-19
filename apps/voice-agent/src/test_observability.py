"""Unit tests de logging estructurado (NFR-08)."""

import json
import logging

import pytest

from core.observability import JsonFormatter, log_event


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
