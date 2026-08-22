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
"""

import os

import uvicorn
from dotenv import load_dotenv

from audio.microphone import MicrophoneRecorder
from auth.session_token import HmacSessionTokenIssuer
from auth.video_token import HmacVideoTokenIssuer
from core.observability import configure_logging
from llm.claude import ClaudeDispatcher
from llm.metrics_judge import ClaudeMetricsJudge
from persistence.sqlite_incident_store import SQLiteIncidentStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore
from persistence.sqlite_scenario_video_store import SQLiteScenarioVideoStore
from persistence.sqlite_settings_store import SQLiteSettingsStore
from persistence.sqlite_store import SQLiteSessionStore
from persistence.sqlite_stt_metrics_store import SQLiteSttMetricsStore
from server.app import create_app
from server.tls import ensure_self_signed_cert
from stt.whisper import WhisperSTT
from tts.kokoro import KokoroTTS

load_dotenv()
configure_logging()  # NFR-08: logs estructurados desde el arranque del proceso, no agregados después.


def build_app():
    token_issuer = HmacSessionTokenIssuer(
        secret_key=os.environ["SESSION_TOKEN_SECRET"].encode(),
    )
    # ADR-0009: puede rotarse independiente de SESSION_TOKEN_SECRET, pero por default reusa la
    # misma clave — no vale la pena una segunda variable obligatoria solo para esto.
    video_token_issuer = HmacVideoTokenIssuer(
        secret_key=os.getenv("VIDEO_TOKEN_SECRET", os.environ["SESSION_TOKEN_SECRET"]).encode(),
    )

    sessions_db_path = os.getenv("SESSIONS_DB_PATH", "sessions.db")

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
        stt=WhisperSTT(model_size="small", device="cpu", compute_type="int8"),
        tts=KokoroTTS(voice=os.getenv("KOKORO_VOICE", "am_michael")),
        microphone=MicrophoneRecorder(),
        # docs/designs/escenarios-de-video.md — tabla nueva, mismo archivo compartido
        # (ver TODO-20 sobre por qué nunca se altera `scenarios`/`sessions` para esto).
        scenario_video_store=SQLiteScenarioVideoStore(sessions_db_path),
        video_token_issuer=video_token_issuer,
        # ADR-0011: vacío por default — sin esta env var, no hay login de manager posible.
        manager_passphrase=os.getenv("MANAGER_PASSPHRASE", ""),
        # ADR-0012: upload real de video — reemplaza tener que colocar el archivo a mano.
        video_storage_dir=os.getenv("VIDEO_STORAGE_DIR", "video_storage"),
        video_max_upload_bytes=int(os.getenv("VIDEO_MAX_UPLOAD_BYTES", str(2 * 1024**3))),
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
    )


def build_uvicorn_kwargs() -> dict:
    """Configuración de `uvicorn.run` — función pura (lee env, no llama a `uvicorn.run` en sí)
    para poder probar la decisión de TLS sin levantar un servidor real."""

    kwargs = {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", "8000")),
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
