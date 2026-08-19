"""Unit tests de `server_main.build_uvicorn_kwargs` — la decisión de TLS on/off (NFR-05), sin
levantar un servidor real.

Importar `server_main` construye `app` a nivel de módulo (a propósito: así
`uvicorn server_main:app` funciona desde la CLI sin pasar por `if __name__ == "__main__"`) — por
eso este archivo fija las variables de entorno requeridas y una ruta de sesiones en un
directorio temporal ANTES de importar, en vez de dejar que golpee el `sessions.db` real del
repo.
"""

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="voice-agent-test-")
os.environ.setdefault("SESSION_TOKEN_SECRET", "test-secret")
os.environ.setdefault("SUPERVISOR_PASSPHRASE", "test-pass")
os.environ.setdefault("SESSIONS_DB_PATH", os.path.join(_TMP_DIR, "sessions.db"))

import server_main  # noqa: E402 — el orden de import es intencional, ver docstring del módulo


def test_disable_tls_skips_cert_generation_and_returns_plain_kwargs(monkeypatch):
    monkeypatch.setenv("DISABLE_TLS", "1")

    kwargs = server_main.build_uvicorn_kwargs()

    assert "ssl_certfile" not in kwargs
    assert "ssl_keyfile" not in kwargs
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8000


def test_tls_is_on_by_default_and_generates_cert_and_key(monkeypatch, tmp_path):
    monkeypatch.delenv("DISABLE_TLS", raising=False)
    monkeypatch.setenv("TLS_CERT_PATH", str(tmp_path / "server.crt"))
    monkeypatch.setenv("TLS_KEY_PATH", str(tmp_path / "server.key"))

    kwargs = server_main.build_uvicorn_kwargs()

    assert kwargs["ssl_certfile"] == str(tmp_path / "server.crt")
    assert kwargs["ssl_keyfile"] == str(tmp_path / "server.key")
    assert (tmp_path / "server.crt").exists()
    assert (tmp_path / "server.key").exists()


def test_server_host_and_port_are_configurable(monkeypatch):
    monkeypatch.setenv("DISABLE_TLS", "1")
    monkeypatch.setenv("SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SERVER_PORT", "9443")

    kwargs = server_main.build_uvicorn_kwargs()

    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9443
