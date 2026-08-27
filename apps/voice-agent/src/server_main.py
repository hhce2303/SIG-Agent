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
- `VIDEO_TOKEN_SECRET` (default: reusa `SESSION_TOKEN_SECRET`) — clave HMAC para el token de
  streaming de video (ADR-0009). Escenarios de video quedan deshabilitados (503, ver
  `server/app.py::_require_video_feature`) si tampoco hay `SESSION_TOKEN_SECRET` — en la
  práctica siempre hay una, así que esto solo importa si se quiere rotar la clave de video
  independiente de la de sesión.
- `MANAGER_PASSPHRASE` — passphrase de manager (ADR-0011, TODO-16 acotado). Sin configurar
  (default), no existe ningún login de manager posible — falla cerrado: nadie puede adjuntar
  video real de un incidente al promoverlo hasta que se configure explícitamente.
- `VIDEO_STORAGE_DIR` (default `./video_storage`) — carpeta donde `POST /video/upload` guarda
  los archivos subidos (ADR-0012, reemplaza tener que colocarlos a mano). Se crea si no existe.
- `VIDEO_MAX_UPLOAD_BYTES` (default 2 GiB) — límite de tamaño por archivo subido.
- `METRICS_JUDGE_ENABLED` (default `1`) — motor de métricas (docs/designs/motor-de-metricas.md):
  `0` apaga el juez LLM de coherencia/calidad de inglés post-llamada sin revertir el resto del
  plan (latencia de turno y confianza de transcripción siguen activas — son puras, bajo riesgo).
  Reusa `ANTHROPIC_API_KEY`/`CLAUDE_MODEL`, las mismas credenciales que ya usa el dispatcher.
- `WHISPER_MODEL_PATH` / `KOKORO_MODEL_DIR` (docs/designs/empaquetado-ejecutable-backend.md,
  Premisas 2-4) — rutas locales a pesos ya descargados (relativas a `bundle_dir()`, o absolutas),
  para correr sin acceso a internet en el ejecutable empaquetado. Sin configurar, caen al
  comportamiento actual (descarga de HuggingFace en el primer uso) — el modo esperado en
  desarrollo local, no un fallback silencioso indeseado.

Empaquetado como ejecutable standalone (PyInstaller): ver
docs/designs/empaquetado-ejecutable-backend.md. `base_dir()`/`bundle_dir()`
(`core/paths.py`) anclan todo el estado escribible y los assets empaquetados al directorio del
propio `.exe`, no al CWD desde el que se lo invoque — independiente de si arranca con doble-click,
un acceso directo, o desde otra carpeta.
"""

import os
import sys

import uvicorn
from dotenv import load_dotenv

from audio.microphone import MicrophoneRecorder
from auth.session_token import HmacSessionTokenIssuer
from auth.video_token import HmacVideoTokenIssuer
from core.observability import configure_logging
from core.paths import base_dir, bundle_dir
from llm.claude import ClaudeDispatcher
from llm.metrics_judge import ClaudeMetricsJudge
from persistence.sqlite_incident_store import SQLiteIncidentStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore
from persistence.sqlite_scenario_video_store import SQLiteScenarioVideoStore
from persistence.sqlite_scenario_location_store import SQLiteScenarioLocationStore
from persistence.sqlite_settings_store import SQLiteSettingsStore
from persistence.sqlite_store import SQLiteSessionStore
from persistence.sqlite_stt_metrics_store import SQLiteSttMetricsStore
from server.app import create_app
from server.tls import ensure_self_signed_cert
from stt.whisper import WhisperSTT
from tts.kokoro import KokoroTTS

# `.env` — frozen vs. dev (Premisa 6): forzar `dotenv_path=` incondicionalmente rompería
# `dev-up.ps1`, que guarda `.env` en la raíz del repo mientras lanza el backend desde
# `apps/voice-agent/src` (dos niveles por debajo) — `load_dotenv()` sin argumentos hace una
# búsqueda hacia arriba desde ahí y lo encuentra. Esa búsqueda implícita SÍ es poco confiable
# bajo PyInstaller (camina desde el `co_filename` del frame llamante, que en código congelado
# conserva la ruta de la máquina de build) — por eso el modo frozen pasa `dotenv_path=` explícito
# en vez de confiar en la búsqueda, y el modo dev queda intacto.
if getattr(sys, "frozen", False):
    load_dotenv(dotenv_path=os.path.join(base_dir(), ".env"))
else:
    load_dotenv()

configure_logging(
    log_dir=os.path.join(base_dir(), "logs")
)  # NFR-08 + Premisa 8: logs estructurados desde el arranque, a stdout y a archivo.


def _require_env(*names: str) -> None:
    """Fail-fast con mensaje claro (Premisa 7) si falta o está VACÍA alguna variable requerida —
    `os.getenv(name)` es falsy tanto para ausente como para `""`, así que esto cubre el gap real
    que un `.env.example` con valores en blanco ya invita a cometer."""
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        sys.stderr.write(
            f"ERROR: faltan (o están vacías) estas variables requeridas en .env: "
            f"{', '.join(missing)}. El .env debe estar junto al ejecutable, en {base_dir()}.\n"
        )
        sys.exit(1)


def _require_paths(**named_paths: str) -> None:
    """Fail-fast al arranque (Premisa 7) si una ruta de modelo requerida no existe — nunca dejar
    que `speak()`/`transcribe()` fallen silenciosamente en medio de una llamada en vivo."""
    missing = {name: path for name, path in named_paths.items() if not os.path.exists(path)}
    if missing:
        for name, path in missing.items():
            sys.stderr.write(f"ERROR: {name} no existe: {path}\n")
        sys.exit(1)


def _resolve_model_path(env_var: str) -> str | None:
    """`WHISPER_MODEL_PATH`/`KOKORO_MODEL_DIR`, resueltos contra `bundle_dir()` si son
    relativos — nunca contra `base_dir()` (Premisa 4: son assets empaquetados de solo lectura,
    no estado escribible junto al exe)."""
    value = os.getenv(env_var)
    if not value:
        return None
    return value if os.path.isabs(value) else os.path.join(bundle_dir(), value)


_require_env("ANTHROPIC_API_KEY", "CLAUDE_MODEL", "SESSION_TOKEN_SECRET", "SUPERVISOR_PASSPHRASE")

_whisper_model_path = _resolve_model_path("WHISPER_MODEL_PATH")
_kokoro_model_dir = _resolve_model_path("KOKORO_MODEL_DIR")
if _whisper_model_path:
    _require_paths(WHISPER_MODEL_PATH=_whisper_model_path)
if _kokoro_model_dir:
    _require_paths(
        KOKORO_MODEL_DIR=_kokoro_model_dir,
        **{
            f"voz '{os.getenv('KOKORO_VOICE', 'am_michael')}'": os.path.join(
                _kokoro_model_dir, "voices", f"{os.getenv('KOKORO_VOICE', 'am_michael')}.pt"
            )
        },
    )


def build_app():
    token_issuer = HmacSessionTokenIssuer(
        secret_key=os.environ["SESSION_TOKEN_SECRET"].encode(),
    )
    # ADR-0009: puede rotarse independiente de SESSION_TOKEN_SECRET, pero por default reusa la
    # misma clave — no vale la pena una segunda variable obligatoria solo para esto.
    video_token_issuer = HmacVideoTokenIssuer(
        secret_key=os.getenv("VIDEO_TOKEN_SECRET", os.environ["SESSION_TOKEN_SECRET"]).encode(),
    )

    # Premisa 6: ancladas a `base_dir()` (junto al ejecutable), no al CWD desde el que se
    # invoque — `os.path.join` descarta `base_dir()` solo si el override ya es una ruta
    # absoluta, así que un `SESSIONS_DB_PATH` absoluto (ej. un share de red) sigue funcionando.
    # `os.getenv(key) or default`, no `os.getenv(key, default)` (Premisa 7) — una variable
    # presente pero vacía en `.env` debe caer al default, no resolver a `""`.
    sessions_db_path = os.path.join(base_dir(), os.getenv("SESSIONS_DB_PATH") or "sessions.db")

    # Fase 2 (cierre del gap de Fase 1): el servidor ahora invoca STT/Claude/TTS reales —
    # antes solo sincronizaba eventos de `TurnStateMachine` como JSON. Mismos adaptadores y
    # mismas variables de entorno que ya usa el prototipo CLI (`main.py`, NFR-03).
    return create_app(
        token_issuer=token_issuer,
        session_store=SQLiteSessionStore(sessions_db_path),
        scenario_store=SQLiteScenarioStore(sessions_db_path),
        settings_store=SQLiteSettingsStore(sessions_db_path),
        incident_store=SQLiteIncidentStore(sessions_db_path),
        supervisor_passphrase=os.environ["SUPERVISOR_PASSPHRASE"],
        dispatcher=ClaudeDispatcher(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=os.environ["CLAUDE_MODEL"],
        ),
        # `_whisper_model_path`/`_kokoro_model_dir` (módulo-level, Premisas 2-4): `None` cuando
        # `WHISPER_MODEL_PATH`/`KOKORO_MODEL_DIR` no están seteadas — cae al comportamiento
        # actual (descarga de HuggingFace por `model_size="small"`/voice id), el modo esperado
        # en desarrollo local.
        stt=WhisperSTT(
            model_size="small", device="cpu", compute_type="int8", model_path=_whisper_model_path
        ),
        tts=KokoroTTS(voice=os.getenv("KOKORO_VOICE") or "am_michael", model_dir=_kokoro_model_dir),
        microphone=MicrophoneRecorder(),
        # docs/designs/escenarios-de-video.md — tabla nueva, mismo archivo compartido
        # (ver TODO-20 sobre por qué nunca se altera `scenarios`/`sessions` para esto).
        scenario_video_store=SQLiteScenarioVideoStore(sessions_db_path),
        video_token_issuer=video_token_issuer,
        # ADR-0011: vacío por default — sin esta env var, no hay login de manager posible.
        manager_passphrase=os.getenv("MANAGER_PASSPHRASE") or "",
        # ADR-0012: upload real de video — reemplaza tener que colocar el archivo a mano.
        video_storage_dir=os.path.join(
            base_dir(), os.getenv("VIDEO_STORAGE_DIR") or "video_storage"
        ),
        video_max_upload_bytes=int(os.getenv("VIDEO_MAX_UPLOAD_BYTES") or str(2 * 1024**3)),
        # T13/Fase 1 Sección 9 (docs/designs/motor-de-metricas.md): feature flag recomendado
        # específicamente para el judge (no para latencia/confianza de transcripción, que son
        # de bajo riesgo) — `METRICS_JUDGE_ENABLED=0` lo apaga sin revertir el resto del plan si
        # aparece un problema de costo/latencia/calidad en producción. Prendido por default,
        # reusa las mismas credenciales que ya configura `ClaudeDispatcher`.
        metrics_judge=(
            ClaudeMetricsJudge(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                model=os.environ["CLAUDE_MODEL"],
            )
            if os.getenv("METRICS_JUDGE_ENABLED", "1") == "1"
            else None
        ),
        # T4: mismo archivo compartido que el resto (ver TODO-20 sobre por qué nunca se altera
        # `sessions`/`scenarios` — tabla nueva en su lugar).
        stt_metrics_store=SQLiteSttMetricsStore(sessions_db_path),
        # docs/designs/ubicacion-del-incidente.md — mismo patrón que scenario_video_store: tabla
        # nueva, mismo archivo compartido.
        scenario_location_store=SQLiteScenarioLocationStore(sessions_db_path),
    )


def build_uvicorn_kwargs() -> dict:
    """Configuración de `uvicorn.run` — función pura (lee env, no llama a `uvicorn.run` en sí)
    para poder probar la decisión de TLS sin levantar un servidor real."""

    kwargs = {
        "host": os.getenv("SERVER_HOST") or "0.0.0.0",
        "port": int(os.getenv("SERVER_PORT") or "8000"),
    }

    if os.getenv("DISABLE_TLS") == "1":
        # Sin emoji a propósito: la consola de Windows en su codepage por default (cp1252) no
        # puede codificar U+26A0/U+FE0F y el `print` tumbaba el proceso con UnicodeEncodeError
        # antes de arrancar uvicorn — encontrado corriendo este mismo escape hatch de verdad en
        # una sesión de pruebas reales, no una preferencia de estilo.
        print(
            "AVISO: DISABLE_TLS=1 — corriendo sin WSS/TLS (viola NFR-05). "
            "Solo válido para desarrollo local, nunca contra la LAN real."
        )
        return kwargs

    # Premisa 6: ancladas a `base_dir()`, como `sessions_db_path` arriba.
    cert_path, key_path = ensure_self_signed_cert(
        os.path.join(base_dir(), os.getenv("TLS_CERT_PATH") or "server.crt"),
        os.path.join(base_dir(), os.getenv("TLS_KEY_PATH") or "server.key"),
    )
    kwargs["ssl_certfile"] = cert_path
    kwargs["ssl_keyfile"] = key_path

    return kwargs


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, **build_uvicorn_kwargs())
