"""Unit tests de `ClaudeDispatcher`, con el cliente de Anthropic mockeado (NFR-10, NFR-02).

Cubren el camino feliz y el manejo de error de la API de Claude como estado de primera clase:
reintento acotado ante errores transitorios, y `DispatcherError` (dominio) cuando se agotan.
"""

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from anthropic import APIConnectionError, AuthenticationError, RateLimitError

from core.ports import DispatcherError
from llm.claude import ClaudeDispatcher


def _response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _fake_request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture
def dispatcher():
    with patch("llm.claude.Anthropic"):
        return ClaudeDispatcher(
            api_key="test-key",
            model="claude-test",
            max_retries=2,
            retry_delay_seconds=0,  # no dormir de verdad en tests
        )


def test_respond_returns_text_on_success(dispatcher):
    dispatcher.client.messages.create.return_value = _response("10-4, go ahead.")

    result = dispatcher.respond(conversation=[{"role": "user", "content": "hi"}], scenario="s")

    assert result == "10-4, go ahead."
    dispatcher.client.messages.create.assert_called_once()


def test_respond_retries_on_transient_error_then_succeeds(dispatcher):
    dispatcher.client.messages.create.side_effect = [
        APIConnectionError(request=_fake_request()),
        _response("Copy that."),
    ]

    result = dispatcher.respond(conversation=[], scenario="s")

    assert result == "Copy that."
    assert dispatcher.client.messages.create.call_count == 2


def test_respond_raises_dispatcher_error_after_exhausting_retries(dispatcher):
    dispatcher.client.messages.create.side_effect = RateLimitError(
        message="rate limited",
        response=httpx.Response(429, request=_fake_request()),
        body=None,
    )

    with pytest.raises(DispatcherError):
        dispatcher.respond(conversation=[], scenario="s")

    # max_retries=2 → 3 intentos totales.
    assert dispatcher.client.messages.create.call_count == 3


def test_respond_does_not_retry_non_transient_errors(dispatcher):
    dispatcher.client.messages.create.side_effect = AuthenticationError(
        message="invalid api key",
        response=httpx.Response(401, request=_fake_request()),
        body=None,
    )

    with pytest.raises(AuthenticationError):
        dispatcher.respond(conversation=[], scenario="s")

    # No es un error transitorio (ver RETRYABLE_ERRORS) — no vale la pena reintentar una API
    # key inválida, así que se propaga de inmediato en vez de agotar reintentos primero.
    dispatcher.client.messages.create.assert_called_once()
