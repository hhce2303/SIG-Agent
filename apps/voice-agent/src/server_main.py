"""Punto de entrada para correr el servidor real (uvicorn) — Fase 1.

No reemplaza a `main.py` (el prototipo CLI) — NFR-03 pide que el CLI siga funcionando como
fallback manual mientras este servidor madura, así que ambos entry points coexisten.

Variables de entorno requeridas:
- `SESSION_TOKEN_SECRET` — clave HMAC para firmar tokens de sesión (ADR-0008). Generar una
  clave larga y aleatoria por despliegue, no reusar la de otro entorno.
- `SUPERVISOR_PASSPHRASE` — passphrase compartida mínima de ADR-0008 (sin SSO corporativo
  confirmado, ver TODO-02).

Opcionales:
- `SESSIONS_DB_PATH` (default `sessions.db`) — archivo SQLite de ADR-0007.
- `SERVER_HOST` (default `0.0.0.0`), `SERVER_PORT` (default `8000`).
- `TLS_CERT_PATH`/`TLS_KEY_PATH` (default `server.crt`/`server.key`) — si no existen, se genera
  un certificado autofirmado (ver `server/tls.py`). NFR-05 exige WSS/TLS como mínimo de Fase 1,
  así que TLS está prendido por default, no opt-in.
- `DISABLE_TLS=1` — **solo para desarrollo local.** Corre en texto plano. Nunca contra la LAN
  real de un concesionario: auth + token viajarían en claro.
"""

import os

import uvicorn
from dotenv import load_dotenv

from auth.session_token import HmacSessionTokenIssuer
from core.observability import configure_logging
from persistence.sqlite_store import SQLiteSessionStore
from server.app import create_app
from server.tls import ensure_self_signed_cert

load_dotenv()
configure_logging()  # NFR-08: logs estructurados desde el arranque del proceso, no agregados después.


def build_app():
    token_issuer = HmacSessionTokenIssuer(
        secret_key=os.environ["SESSION_TOKEN_SECRET"].encode(),
    )

    session_store = SQLiteSessionStore(
        os.getenv("SESSIONS_DB_PATH", "sessions.db"),
    )

    return create_app(
        token_issuer=token_issuer,
        session_store=session_store,
        supervisor_passphrase=os.environ["SUPERVISOR_PASSPHRASE"],
    )


def build_uvicorn_kwargs() -> dict:
    """Configuración de `uvicorn.run` — función pura (lee env, no llama a `uvicorn.run` en sí)
    para poder probar la decisión de TLS sin levantar un servidor real."""

    kwargs = {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", "8000")),
    }

    if os.getenv("DISABLE_TLS") == "1":
        print(
            "⚠️  DISABLE_TLS=1 — corriendo sin WSS/TLS (viola NFR-05). "
            "Solo válido para desarrollo local, nunca contra la LAN real."
        )
        return kwargs

    cert_path, key_path = ensure_self_signed_cert(
        os.getenv("TLS_CERT_PATH", "server.crt"),
        os.getenv("TLS_KEY_PATH", "server.key"),
    )
    kwargs["ssl_certfile"] = cert_path
    kwargs["ssl_keyfile"] = key_path

    return kwargs


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, **build_uvicorn_kwargs())
