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

**No expone WSS/TLS todavía** (NFR-05, ver PHASE1-PROGRESS.md) — no correr esto contra la LAN
real de un concesionario sin poner TLS delante (ej. un reverse proxy), o auth + token quedan
viajando en claro.
"""

import os

import uvicorn
from dotenv import load_dotenv

from auth.session_token import HmacSessionTokenIssuer
from persistence.sqlite_store import SQLiteSessionStore
from server.app import create_app

load_dotenv()


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


app = build_app()


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
    )
