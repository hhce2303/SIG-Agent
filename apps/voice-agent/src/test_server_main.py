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

import pytest

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


def test_server_port_falls_back_to_default_when_set_but_empty(monkeypatch):
    """docs/designs/empaquetado-ejecutable-backend.md, Premisa 7: una variable presente pero
    vacía (`SERVER_PORT=`, exactamente el patrón que `.env.example` invita a dejar) debe caer al
    default, no romper con un `ValueError` al hacer `int("")`."""
    monkeypatch.setenv("DISABLE_TLS", "1")
    monkeypatch.setenv("SERVER_PORT", "")

    kwargs = server_main.build_uvicorn_kwargs()

    assert kwargs["port"] == 8000


class TestRequireEnv:
    """`_require_env` (Premisa 7) — fail-fast con mensaje claro, no un traceback crudo."""

    def test_passes_silently_when_all_vars_present_and_non_empty(self, monkeypatch):
        monkeypatch.setenv("FOO", "bar")

        server_main._require_env("FOO")  # no debe lanzar SystemExit

    def test_exits_nonzero_when_a_required_var_is_missing(self, monkeypatch, capsys):
        monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)

        with pytest.raises(SystemExit) as exc_info:
            server_main._require_env("DEFINITELY_NOT_SET")

        assert exc_info.value.code == 1
        assert "DEFINITELY_NOT_SET" in capsys.readouterr().err

    def test_exits_nonzero_when_a_required_var_is_present_but_empty(self, monkeypatch, capsys):
        """El gap real: `.env.example` ya ejercita este patrón (`WHISPER_MODEL_PATH=` en
        blanco) -- `os.getenv(key)` es falsy tanto para ausente como para vacío."""
        monkeypatch.setenv("BLANK_VAR", "")

        with pytest.raises(SystemExit) as exc_info:
            server_main._require_env("BLANK_VAR")

        assert exc_info.value.code == 1
        assert "BLANK_VAR" in capsys.readouterr().err


class TestRequirePaths:
    """`_require_paths` (Premisa 7) — validación de rutas de modelo AL ARRANQUE, no en medio de
    una llamada de audio en vivo."""

    def test_passes_silently_when_path_exists(self, tmp_path):
        existing = tmp_path / "model.bin"
        existing.write_text("fake")

        server_main._require_paths(SOME_MODEL=str(existing))  # no debe lanzar SystemExit

    def test_exits_nonzero_when_a_path_does_not_exist(self, tmp_path, capsys):
        missing = tmp_path / "does-not-exist.bin"

        with pytest.raises(SystemExit) as exc_info:
            server_main._require_paths(SOME_MODEL=str(missing))

        assert exc_info.value.code == 1
        assert str(missing) in capsys.readouterr().err
