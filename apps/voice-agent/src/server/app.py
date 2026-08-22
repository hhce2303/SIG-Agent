"""Servidor FastAPI/WebSocket — roadmap Fase 1 + Fase 2.

Cubre el ciclo de vida de una conexión de sesión: login (ADR-0008) → handshake de WebSocket
autenticado (NFR-04: una conexión no puede apuntar a la sesión de otra) → protocolo completo de
comandos/eventos que ya consume el frontend (`frontend/BACKEND_REQUIREMENTS.md`,
`frontend/src/types.ts`) → registro de la sesión con transcript y evaluación reales al terminar
o desconectar (ADR-0007, PersistencePort) → CRUD de escenarios y ajustes por REST.

**Lo que este módulo NO decide todavía, a propósito:** VAD automático (ADR-0005 lo pide "sin
botón", pero el usuario confirmó mantener `recording.start`/`recording.stop` explícitos por
ahora) y el protocolo de streaming de audio binario para un despliegue LAN remoto real (el
modelo de audio sigue siendo "el backend corre en la misma máquina que el mic", ver
`frontend/BACKEND_REQUIREMENTS.md` §2) — ninguno de los dos tiene ADR, inventarlos acá violaría
la regla "ADR-first" de CONTRIBUTING.md.
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette import status

from core.conversation import DISPATCHER_RECOVERY_LINE
from core.impact_metrics import compute_impact_report
from core.observability import log_event
from core.ports import (
    CriticalDataPoint,
    DispatcherError,
    DispatcherPort,
    IncidentOutcome,
    IncidentOutcomePort,
    InvalidSessionTokenError,
    InvalidVideoTokenError,
    MetricsJudgeError,
    MetricsJudgePort,
    MicrophonePort,
    PersistencePort,
    Scenario,
    ScenarioPort,
    ScenarioVideo,
    ScenarioVideoPort,
    SessionRecord,
    SessionTokenClaims,
    SessionTokenPort,
    SettingsPort,
    SpeechToTextPort,
    SttMetricsPort,
    TextToSpeechPort,
    VideoGroundTruthPoint,
    VideoTokenPort,
)
from core.scoring import score_session
from core.transcription_confidence import aggregate_transcription_confidence, rate_transcription_confidence
from core.turn_state import InvalidTurnTransitionError, TurnStateMachine
from server.video_probe import probe_mp4_duration_seconds
from server.video_streaming import iter_file_range, parse_range_header

logger = logging.getLogger("voice_agent.server")

PROTOCOL_VERSION = "0.3.0"  # Fase 2: protocolo completo de comandos/eventos, no solo turn-state
CLAUDE_TIMEOUT_SECONDS = 8.0
VIDEO_STREAM_CHUNK_SIZE = 1024 * 1024  # 1 MiB — ver server/video_streaming.py
VIDEO_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB — ver ADR-0012
DEFAULT_VIDEO_MAX_UPLOAD_BYTES = 2 * 1024**3  # 2 GiB
# ADR-0012 — allowlist explícito de contenedor: rechazar con 4xx en vez de "aceptar y fallar
# después" (Eng, requisito del plan de tests). `server/video_probe.py` solo entiende MP4/MOV.
ALLOWED_VIDEO_EXTENSIONS = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v"}


class LoginRequest(BaseModel):
    supervisor_id: str
    passphrase: str


class LoginResponse(BaseModel):
    session_id: str
    token: str
    # ADR-0011 — puramente informativo para que el frontend sepa qué UI mostrar (ej. "adjuntar
    # video al promover un incidente"); la aplicación real del rol vive en el servidor
    # (`_require_manager`, re-deriva el rol del token verificado, nunca confía en lo que un
    # cliente mande de vuelta), así que exponerlo acá no debilita nada.
    role: str


class CriticalDataPointModel(BaseModel):
    key: str
    label: str
    required: bool = True
    match_hints: list[str] = Field(default_factory=list)  # TODO-17 — ver core/scoring.py


class ScenarioIn(BaseModel):
    title: str
    category: str
    difficulty: str
    language: str = "English"
    description: str
    briefing: str
    critical_data_points: list[CriticalDataPointModel] = Field(default_factory=list)


class ScenarioOut(ScenarioIn):
    id: str
    created_at: float
    updated_at: float
    has_video: bool = False  # docs/designs/escenarios-de-video.md — sin cambiar Scenario en sí


class VideoGroundTruthPointModel(BaseModel):
    key: str
    label: str
    match_hints: list[str] = Field(default_factory=list)
    visible_from_seconds: float = 0.0
    visible_to_seconds: float = 0.0
    required: bool = True


class ScenarioVideoIn(BaseModel):
    """Cuerpo de `PUT /scenarios/{id}/video` — `video_path` puede venir de `POST /videos/upload`
    (ADR-0012, el camino normal) o seguir siendo una ruta ya colocada a mano en el servidor (v1,
    todavía soportado, ver "Scope Decision" del plan original)."""

    video_path: str
    duration_seconds: float = Field(gt=0)
    content_type: str = "video/mp4"
    ground_truth_points: list[VideoGroundTruthPointModel] = Field(default_factory=list)


class ScenarioVideoOut(BaseModel):
    """Vista de autoría (editor) — SÍ incluye `match_hints` porque quien la lee ya es quien
    autora el escenario. Nunca se manda esta forma al camino de acceso del entrenando antes/
    durante la llamada (`GET /scenarios/{id}/video`), que se queda con `ScenarioVideoAccessOut`.
    """

    scenario_id: str
    video_path: str
    video_checksum: str
    duration_seconds: float
    content_type: str
    ground_truth_points: list[VideoGroundTruthPointModel]
    created_at: float
    updated_at: float


class ScenarioVideoUploadOut(BaseModel):
    """Respuesta de `POST /videos/upload` (ADR-0012) — el frontend usa esto para completar el
    formulario de `PUT /scenarios/{id}/video` o de `promote-to-scenario` con `video` (que siguen
    siendo la única forma de fijar el ground truth), no para adjuntar el video directamente en
    un solo paso.
    """

    video_path: str
    video_checksum: str
    duration_seconds: float | None  # `None` = no se pudo detectar automáticamente, pedir a mano
    content_type: str


class ScenarioVideoAccessOut(BaseModel):
    """Lo mínimo que necesita el entrenando para reproducir el video antes de la llamada — sin
    `ground_truth_points` (sería filtrar la respuesta correcta antes de que hable, ver ADR-0010).
    """

    content_type: str
    duration_seconds: float
    stream_url: str


class PromoteVideoIn(BaseModel):
    video_path: str
    duration_seconds: float = Field(gt=0)
    content_type: str = "video/mp4"
    ground_truth_points: list[VideoGroundTruthPointModel] = Field(default_factory=list)


class PromoteIn(BaseModel):
    # ADR-0011: adjuntar video real de un incidente exige role=="manager" — promover sin video
    # (`video=None`, el body entero es opcional) sigue igual que antes de este ADR.
    video: PromoteVideoIn | None = None


class SettingsModel(BaseModel):
    tts_voice: str


class IncidentIn(BaseModel):
    occurred_at: float
    supervisor_id: str
    category: str = ""
    outcome_rating: int = Field(ge=1, le=5)
    critical_data_captured: bool
    protocol_followed: bool
    notes: str = ""


class IncidentOut(IncidentIn):
    id: str
    reported_by: str
    promoted_scenario_id: str
    created_at: float


class GroupStatsModel(BaseModel):
    sample_size: int
    avg_outcome_rating: float | None = None
    critical_data_capture_rate: float | None = None
    protocol_followed_rate: float | None = None


class ImpactReportModel(BaseModel):
    trained: GroupStatsModel
    untrained: GroupStatsModel
    total_incidents: int
    is_conclusive: bool
    caveat: str


def create_app(
    token_issuer: SessionTokenPort,
    session_store: PersistencePort,
    scenario_store: ScenarioPort,
    settings_store: SettingsPort,
    incident_store: IncidentOutcomePort,
    supervisor_passphrase: str,
    dispatcher: DispatcherPort,
    stt: SpeechToTextPort,
    tts: TextToSpeechPort,
    microphone: MicrophonePort,
    clock=time.time,
    scenario_video_store: ScenarioVideoPort | None = None,
    video_token_issuer: VideoTokenPort | None = None,
    manager_passphrase: str = "",
    video_storage_dir: str | None = None,
    video_max_upload_bytes: int = DEFAULT_VIDEO_MAX_UPLOAD_BYTES,
    # T13 (docs/designs/motor-de-metricas.md): `None` por default, mismo patrón que
    # `scenario_video_store`/`video_token_issuer` — sin configurar, el panel de "Communication
    # Coaching" simplemente no incluye coherencia/calidad de inglés (`judge_unavailable=True`),
    # nunca un `AttributeError` sobre `None` ni un caller existente roto.
    metrics_judge: MetricsJudgePort | None = None,
    # T4: idem — sin configurar, el detalle por-segmento de confianza de Whisper simplemente no
    # se persiste (el agregado en `evaluation_json` sigue funcionando igual, es independiente).
    stt_metrics_store: SttMetricsPort | None = None,
) -> FastAPI:
    """Factory (no una `app` global a nivel de módulo) para que los tests puedan inyectar
    dobles de prueba de cada puerto sin compartir estado entre tests ni depender de
    Whisper/Kokoro/Claude/sounddevice reales.

    `scenario_video_store`/`video_token_issuer` son `None` por default para no romper cualquier
    caller existente (tests, `server_main.py` antes de que se configuren) — las rutas de video
    responden 503 "video feature not configured" en vez de un `AttributeError` sobre `None`.
    `manager_passphrase` vacío (default) es "no hay login de manager posible" — ADR-0011 exige
    fallar cerrado, no abierto. `video_storage_dir=None` deshabilita específicamente el upload
    (`/videos/upload` responde 503) sin afectar `PUT /scenarios/{id}/video` (referencia manual de
    path, sigue funcionando igual — ver ADR-0012, el upload complementa esa v1, no la reemplaza).
    """

    app = FastAPI(title="voice-agent server")

    # El frontend siempre llama por REST desde un origen distinto al del backend (Vite en
    # `npm run dev`, o el cliente Electron empaquetado sirviendo la UI desde `file://`) — sin
    # esto, el navegador bloquea el `fetch` entero con un error de CORS antes de que la request
    # llegue acá (no es un 401/403, ni siquiera hay respuesta que loguear). Wildcard es seguro
    # en este caso porque la auth real (ADR-0008) viaja en el header `Authorization: Bearer`,
    # nunca en una cookie (`allow_credentials` queda False) — no hay sesión de navegador que un
    # origen ajeno pueda montar, solo un origen que ya tiene el token puede leer la respuesta.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _bearer_claims(authorization: str | None = Header(default=None)) -> SessionTokenClaims:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")

        try:
            return token_issuer.verify(authorization.split(" ", 1)[1])
        except InvalidSessionTokenError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    def _require_manager(claims: SessionTokenClaims = Depends(_bearer_claims)) -> SessionTokenClaims:
        """ADR-0011 — gate de rol mínimo antes de exponer/adjuntar video de un incidente real.
        No reemplaza `_bearer_claims` (ya corrió), solo agrega el chequeo de rol encima.
        """

        if claims.role != "manager":
            raise HTTPException(status_code=403, detail="requires the manager role")
        return claims

    # -----------------------------------------------------------------
    # REST — salud, auth (sin cambios de Fase 1), escenarios y ajustes (nuevo, Fase 2).
    # -----------------------------------------------------------------

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/login", response_model=LoginResponse)
    def login(body: LoginRequest):
        # ADR-0011: `manager_passphrase` vacío (default) hace que esta rama sea inalcanzable —
        # sin esa env var configurada, nadie puede autenticarse como manager (falla cerrado).
        if manager_passphrase and body.passphrase == manager_passphrase:
            role = "manager"
        elif body.passphrase == supervisor_passphrase:
            role = "supervisor"
        else:
            log_event(logger, "login_failed", supervisor_id=body.supervisor_id)
            raise HTTPException(status_code=401, detail="invalid credentials")

        session_id = str(uuid.uuid4())
        token = token_issuer.issue(supervisor_id=body.supervisor_id, session_id=session_id, role=role)

        log_event(
            logger,
            "login_succeeded",
            correlation_id=session_id,
            supervisor_id=body.supervisor_id,
            role=role,
        )

        return LoginResponse(session_id=session_id, token=token, role=role)

    @app.get("/scenarios", response_model=list[ScenarioOut])
    def list_scenarios(claims: SessionTokenClaims = Depends(_bearer_claims)):
        return [_scenario_out(scenario, scenario_video_store) for scenario in scenario_store.list()]

    @app.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
    def get_scenario(scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        scenario = scenario_store.get(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        return _scenario_out(scenario, scenario_video_store)

    @app.post("/scenarios", response_model=ScenarioOut, status_code=201)
    def create_scenario(body: ScenarioIn, claims: SessionTokenClaims = Depends(_bearer_claims)):
        scenario = Scenario(id="", **_scenario_fields(body))
        scenario_store.create(scenario)
        log_event(logger, "scenario_created", supervisor_id=claims.supervisor_id, scenario_id=scenario.id)
        return _scenario_out(scenario, scenario_video_store)

    @app.put("/scenarios/{scenario_id}", response_model=ScenarioOut)
    def update_scenario(
        scenario_id: str, body: ScenarioIn, claims: SessionTokenClaims = Depends(_bearer_claims)
    ):
        existing = scenario_store.get(scenario_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="scenario not found")

        for field_name, value in _scenario_fields(body).items():
            setattr(existing, field_name, value)

        scenario_store.update(existing)
        log_event(logger, "scenario_updated", supervisor_id=claims.supervisor_id, scenario_id=scenario_id)
        return _scenario_out(existing, scenario_video_store)

    @app.delete("/scenarios/{scenario_id}", status_code=204)
    def delete_scenario(scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        scenario_store.delete(scenario_id)
        if scenario_video_store is not None:
            # Eng finding 2.3: no dejar la referencia de video colgando de un escenario borrado.
            # El archivo en disco solo se borra si lo subimos nosotros (ADR-0012,
            # `_delete_owned_video_file`) — una referencia manual de v1 (fuera de
            # `video_storage_dir`) nunca se toca, no es nuestra para borrar.
            _delete_owned_video_file(scenario_video_store.get(scenario_id))
            scenario_video_store.delete(scenario_id)
        log_event(logger, "scenario_deleted", supervisor_id=claims.supervisor_id, scenario_id=scenario_id)

    # -----------------------------------------------------------------
    # Video de escenarios — docs/designs/escenarios-de-video.md, ADR-0009/ADR-0010.
    # -----------------------------------------------------------------

    def _require_video_feature() -> None:
        if scenario_video_store is None or video_token_issuer is None:
            raise HTTPException(status_code=503, detail="video scenarios are not configured on this server")

    @app.get("/scenarios/{scenario_id}/video", response_model=ScenarioVideoAccessOut)
    def get_scenario_video_access(
        scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)
    ):
        """Lo que necesita el entrenando para reproducir el video antes de la llamada — emite
        un token de streaming de vida corta (ADR-0009), nunca el ground truth (ADR-0010)."""

        _require_video_feature()
        video = scenario_video_store.get(scenario_id)
        if video is None:
            raise HTTPException(status_code=404, detail="scenario has no video")

        stream_token = video_token_issuer.issue(scenario_id=scenario_id, supervisor_id=claims.supervisor_id)
        return ScenarioVideoAccessOut(
            content_type=video.content_type,
            duration_seconds=video.duration_seconds,
            stream_url=f"/scenarios/{scenario_id}/video/stream?token={stream_token}",
        )

    @app.get("/scenarios/{scenario_id}/video/ground-truth", response_model=ScenarioVideoOut)
    def get_scenario_video_ground_truth(
        scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)
    ):
        """Vista de autoría (editor) — SÍ incluye `match_hints`/timestamps. Ruta separada a
        propósito de `get_scenario_video_access` para que la respuesta correcta nunca viaje por
        el camino que también usa el entrenando antes de la llamada."""

        _require_video_feature()
        video = scenario_video_store.get(scenario_id)
        if video is None:
            raise HTTPException(status_code=404, detail="scenario has no video")
        return _scenario_video_out(video)

    @app.put("/scenarios/{scenario_id}/video", response_model=ScenarioVideoOut)
    def put_scenario_video(
        scenario_id: str, body: ScenarioVideoIn, claims: SessionTokenClaims = Depends(_bearer_claims)
    ):
        _require_video_feature()
        if scenario_store.get(scenario_id) is None:
            raise HTTPException(status_code=404, detail="scenario not found")

        for point in body.ground_truth_points:
            if not (0 <= point.visible_from_seconds <= point.visible_to_seconds <= body.duration_seconds):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"ground truth point {point.key!r} has a visibility range outside "
                        f"[0, {body.duration_seconds}]"
                    ),
                )

        try:
            checksum = _sha256_of_file(body.video_path)
        except OSError as error:
            # No es un path controlado por el cliente en el sentido de traversal (ver ADR-0009 —
            # es una referencia manual de admin, no una request de un entrenando), pero sí debe
            # dar un error claro si el archivo no existe, no un 500 crudo.
            raise HTTPException(status_code=400, detail=f"video_path is not readable: {error}") from error

        video = ScenarioVideo(
            scenario_id=scenario_id,
            video_path=body.video_path,
            video_checksum=checksum,
            duration_seconds=body.duration_seconds,
            content_type=body.content_type,
            ground_truth_points=[
                VideoGroundTruthPoint(
                    key=p.key,
                    label=p.label,
                    match_hints=p.match_hints,
                    visible_from_seconds=p.visible_from_seconds,
                    visible_to_seconds=p.visible_to_seconds,
                    required=p.required,
                )
                for p in body.ground_truth_points
            ],
        )
        scenario_video_store.upsert(video)
        log_event(
            logger, "scenario_video_attached", supervisor_id=claims.supervisor_id, scenario_id=scenario_id
        )
        return _scenario_video_out(scenario_video_store.get(scenario_id))

    @app.post("/videos/upload", response_model=ScenarioVideoUploadOut)
    async def upload_video(
        file: UploadFile = File(...),
        claims: SessionTokenClaims = Depends(_bearer_claims),
    ):
        """ADR-0012 — reemplaza tener que colocar el archivo a mano en el disco del servidor
        (v1, `PUT`/`promote-to-scenario` seguían pidiendo un `video_path` ya existente). El
        nombre en disco es siempre generado por el servidor (UUID), nunca el nombre que mandó el
        cliente (Eng 4.3, path traversal).

        Deliberadamente NO scopeado a un `scenario_id`: el archivo no pertenece a ningún
        escenario todavía en el momento de subirlo — dos callers distintos lo usan antes de que
        exista una relación (`PUT /scenarios/{id}/video` para un escenario ya creado, y
        `POST /incidents/{id}/promote-to-scenario` con `video`, donde el escenario recién se
        crea en esa misma llamada). Ambos completan el mismo `video_path`/`duration_seconds` que
        esto devuelve en su propio formulario — este endpoint solo resuelve "¿cómo llega el
        archivo al servidor?", nunca decide a qué se adjunta.
        """

        if video_storage_dir is None:
            raise HTTPException(status_code=503, detail="video upload is not configured on this server")
        _require_video_feature()

        extension = os.path.splitext(file.filename or "")[1].lower()
        content_type = ALLOWED_VIDEO_EXTENSIONS.get(extension)
        if content_type is None:
            raise HTTPException(
                status_code=415,
                detail=f"unsupported video file type {extension!r} — allowed: {sorted(ALLOWED_VIDEO_EXTENSIONS)}",
            )

        os.makedirs(video_storage_dir, exist_ok=True)
        final_path = os.path.join(video_storage_dir, f"{uuid.uuid4()}{extension}")
        temp_path = f"{final_path}.part"

        total_bytes = 0
        try:
            with open(temp_path, "wb") as out:
                while True:
                    chunk = await file.read(VIDEO_UPLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > video_max_upload_bytes:
                        raise HTTPException(status_code=413, detail="video file exceeds the upload size limit")
                    out.write(chunk)
            # Eng 2.2: write-temp -> rename atómico — nunca deja un archivo a medio escribir con
            # el nombre final que otro request podría leer mientras se sube.
            os.replace(temp_path, final_path)
        except HTTPException:
            _remove_if_exists(temp_path)
            raise
        finally:
            await file.close()

        checksum = _sha256_of_file(final_path)
        duration = probe_mp4_duration_seconds(final_path)

        log_event(
            logger,
            "video_uploaded",
            supervisor_id=claims.supervisor_id,
            bytes=total_bytes,
            duration_detected=duration is not None,
        )

        return ScenarioVideoUploadOut(
            video_path=final_path,
            video_checksum=checksum,
            duration_seconds=duration,
            content_type=content_type,
        )

    def _delete_owned_video_file(video: ScenarioVideo | None) -> None:
        """Eng 2.3 (huérfanos en disco): solo borra el archivo si vive DENTRO de
        `video_storage_dir` — es decir, si lo subimos nosotros vía `/videos/upload` (ADR-0012).
        Un `video_path` de la v1 manual (colocado por un admin fuera de ese directorio) nunca se
        borra automáticamente — no es nuestro para borrar."""

        if video is None or video_storage_dir is None:
            return
        try:
            video_dir_real = os.path.realpath(video_storage_dir)
            video_path_real = os.path.realpath(video.video_path)
            same_tree = os.path.commonpath([video_dir_real, video_path_real]) == video_dir_real
        except (OSError, ValueError):
            # ValueError: paths en distinta unidad de Windows — no puede ser el mismo árbol.
            return
        if same_tree:
            _remove_if_exists(video.video_path)

    @app.delete("/scenarios/{scenario_id}/video", status_code=204)
    def delete_scenario_video(scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        _require_video_feature()
        _delete_owned_video_file(scenario_video_store.get(scenario_id))
        scenario_video_store.delete(scenario_id)
        log_event(
            logger, "scenario_video_detached", supervisor_id=claims.supervisor_id, scenario_id=scenario_id
        )

    @app.get("/scenarios/{scenario_id}/video/stream")
    def stream_scenario_video(scenario_id: str, token: str, request: Request):
        """Sin `_bearer_claims` a propósito — un `<video src>` HTML no puede mandar el header
        `Authorization` (ver ADR-0009). Se autentica con el token de vida corta que emite
        `get_scenario_video_access` en su lugar."""

        _require_video_feature()
        try:
            video_token_issuer.verify(token, scenario_id)
        except InvalidVideoTokenError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

        video = scenario_video_store.get(scenario_id)
        if video is None:
            raise HTTPException(status_code=404, detail="scenario has no video")

        try:
            file_size = os.path.getsize(video.video_path)
        except OSError as error:
            # Eng finding 2.5: archivo referenciado pero ausente en disco — estado explícito.
            log_event(
                logger, "scenario_video_missing_on_disk", correlation_id=scenario_id, error=str(error)
            )
            raise HTTPException(status_code=404, detail="video file is missing on disk") from error

        range_bounds = parse_range_header(request.headers.get("range"), file_size)

        if range_bounds is None and request.headers.get("range") is not None:
            # Había un header Range, pero no es satisfacible (ej. start >= file_size).
            raise HTTPException(status_code=416, detail="invalid range")

        start, end = range_bounds if range_bounds is not None else (0, file_size - 1)
        headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1)}

        if range_bounds is not None:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        return StreamingResponse(
            iter_file_range(video.video_path, start, end, chunk_size=VIDEO_STREAM_CHUNK_SIZE),
            status_code=206 if range_bounds is not None else 200,
            media_type=video.content_type,
            headers=headers,
        )

    @app.get("/settings", response_model=SettingsModel)
    def get_settings(claims: SessionTokenClaims = Depends(_bearer_claims)):
        return SettingsModel(tts_voice=settings_store.get_tts_voice())

    @app.put("/settings", response_model=SettingsModel)
    def put_settings(body: SettingsModel, claims: SessionTokenClaims = Depends(_bearer_claims)):
        settings_store.set_tts_voice(body.tts_voice)
        return SettingsModel(tts_voice=settings_store.get_tts_voice())

    # -----------------------------------------------------------------
    # Incidentes reales — roadmap Fase 3. Ver docstring de `IncidentOutcome` (core/ports.py)
    # sobre por qué no hay control de acceso por rol (TODO-15): cualquier sesión autenticada
    # puede registrar/leer/promover, igual que ya pasa con el CRUD de escenarios.
    # -----------------------------------------------------------------

    @app.get("/incidents", response_model=list[IncidentOut])
    def list_incidents(claims: SessionTokenClaims = Depends(_bearer_claims)):
        return [_incident_out(incident) for incident in incident_store.list()]

    @app.post("/incidents", response_model=IncidentOut, status_code=201)
    def create_incident(body: IncidentIn, claims: SessionTokenClaims = Depends(_bearer_claims)):
        incident = IncidentOutcome(id="", reported_by=claims.supervisor_id, **body.model_dump())
        incident_store.create(incident)
        log_event(
            logger, "incident_logged", supervisor_id=claims.supervisor_id, incident_id=incident.id
        )
        return _incident_out(incident)

    @app.delete("/incidents/{incident_id}", status_code=204)
    def delete_incident(incident_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        incident_store.delete(incident_id)
        log_event(logger, "incident_deleted", supervisor_id=claims.supervisor_id, incident_id=incident_id)

    @app.post("/incidents/{incident_id}/promote-to-scenario", response_model=ScenarioOut, status_code=201)
    def promote_incident_to_scenario(
        incident_id: str,
        body: PromoteIn = PromoteIn(),
        claims: SessionTokenClaims = Depends(_bearer_claims),
    ):
        """Lazo de retroalimentación (roadmap Fase 3): convierte el post-mortem de un incidente
        real (`notes`) en un borrador de `Scenario` — se crea vacío de `critical_data_points` a
        propósito, el editor CRUD ya existente (Fase 2) es donde se termina de completar, no se
        inventa un segundo formulario para lo mismo.

        Escenarios de video (docs/designs/escenarios-de-video.md): `body.video`, si viene, adjunta
        el video real del incidente al escenario nuevo — exige `role == "manager"` (ADR-0011),
        promover sin `video` sigue exactamente igual que antes de ese ADR, sin chequeo de rol.
        """

        if body.video is not None and claims.role != "manager":
            raise HTTPException(status_code=403, detail="attaching incident video requires the manager role")

        incident = incident_store.get(incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        if incident.promoted_scenario_id:
            raise HTTPException(status_code=409, detail="incident was already promoted to a scenario")

        scenario = Scenario(
            id="",
            title=f"Real incident — {incident.category or 'Uncategorized'}",
            category=incident.category or "Real incident",
            difficulty="Medium",
            language="English",
            description="Drafted from a real incident post-mortem — complete before use.",
            briefing=incident.notes or "(no post-mortem notes were recorded for this incident)",
            critical_data_points=[],
        )
        scenario_store.create(scenario)
        incident_store.mark_promoted(incident_id, scenario.id)

        if body.video is not None:
            _require_video_feature()
            try:
                checksum = _sha256_of_file(body.video.video_path)
            except OSError as error:
                raise HTTPException(status_code=400, detail=f"video_path is not readable: {error}") from error

            scenario_video_store.upsert(ScenarioVideo(
                scenario_id=scenario.id,
                video_path=body.video.video_path,
                video_checksum=checksum,
                duration_seconds=body.video.duration_seconds,
                content_type=body.video.content_type,
                ground_truth_points=[
                    VideoGroundTruthPoint(
                        key=p.key,
                        label=p.label,
                        match_hints=p.match_hints,
                        visible_from_seconds=p.visible_from_seconds,
                        visible_to_seconds=p.visible_to_seconds,
                        required=p.required,
                    )
                    for p in body.video.ground_truth_points
                ],
            ))

        log_event(
            logger,
            "incident_promoted_to_scenario",
            supervisor_id=claims.supervisor_id,
            incident_id=incident_id,
            scenario_id=scenario.id,
            with_video=body.video is not None,
        )
        return _scenario_out(scenario, scenario_video_store)

    @app.get("/impact-report", response_model=ImpactReportModel)
    def get_impact_report(claims: SessionTokenClaims = Depends(_bearer_claims)):
        incidents = incident_store.list()
        sessions_by_supervisor = {
            supervisor_id: session_store.list_sessions(supervisor_id)
            for supervisor_id in {incident.supervisor_id for incident in incidents}
        }
        report = compute_impact_report(incidents, sessions_by_supervisor)
        return ImpactReportModel(
            trained=GroupStatsModel(**report.trained.__dict__),
            untrained=GroupStatsModel(**report.untrained.__dict__),
            total_incidents=report.total_incidents,
            is_conclusive=report.is_conclusive,
            caveat=report.caveat,
        )

    # -----------------------------------------------------------------
    # WebSocket — el loop de llamada en vivo real.
    # -----------------------------------------------------------------

    @app.websocket("/ws/session/{session_id}")
    async def session_socket(websocket: WebSocket, session_id: str, token: str):
        try:
            claims = token_issuer.verify(token)
        except InvalidSessionTokenError as error:
            log_event(logger, "websocket_rejected", correlation_id=session_id, reason=str(error))
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION, reason=str(error)
            ) from error

        if claims.session_id != session_id:
            # NFR-04: una conexión no puede apuntar a la sesión de audio de otra.
            log_event(
                logger,
                "websocket_rejected",
                correlation_id=session_id,
                reason="token does not match session_id",
            )
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION, reason="token does not match session_id"
            )

        await websocket.accept()
        log_event(
            logger, "session_connected", correlation_id=session_id, supervisor_id=claims.supervisor_id
        )

        machine = TurnStateMachine(clock=clock)
        started_at = clock()
        conversation: list[dict[str, str]] = []
        transcript: list[dict] = []
        # T2/T4 (docs/designs/motor-de-metricas.md): segmentos de confianza de Whisper
        # acumulados a lo largo de toda la llamada — antes se descartaban después de decidir el
        # marcador inline `[unclear: ...]`. Se resetea junto con `transcript` en cada
        # `call.start` (ver más abajo), igual que el resto del estado por-llamada.
        stt_segments: list = []
        active_scenario: Scenario | None = None
        active_video: ScenarioVideo | None = None
        call_config = {"difficulty": "", "language": "", "training_type": ""}
        call_ended = False  # True una vez que un `call.end` explícito ya persistió la sesión.
        call_started_once = False  # Evita persistir un registro fantasma si nunca hubo `call.start`.
        # Eng finding 5c: el reloj de "tiempo de reacción" es cuándo terminó el video pre-llamada,
        # NUNCA `started_at`/`call.start` — un entrenando puede ver el video, tomarse un café, y
        # arrancar la llamada mucho después. `video_ended_scenario_id` evita el bug de staleness
        # de usar el timestamp de un escenario de video ANTERIOR si la llamada siguiente es de un
        # escenario distinto (con o sin video) en la misma conexión WS.
        video_ended_at: float | None = None
        video_ended_scenario_id: str = ""

        async def send(payload: dict) -> None:
            await websocket.send_json(payload)

        async def send_scenarios() -> None:
            await send({
                "event": "scenarios.data",
                "scenarios": [_scenario_summary(s, scenario_video_store) for s in scenario_store.list()],
            })

        async def send_history() -> None:
            sessions = session_store.list_sessions(claims.supervisor_id)
            await send({
                "event": "history.data",
                "sessions": [_training_session(s) for s in sessions],
            })

        async def speak_dispatcher_line(text: str) -> None:
            await send({"event": "dispatcher.speaking", "value": True})

            tts_started = clock()
            warning = None
            try:
                await asyncio.to_thread(tts.speak, text, settings_store.get_tts_voice())
            except Exception as error:  # noqa: BLE001 — falla de audio/hardware, no debe tumbar la sesión (contrato §7: warning, no error).
                log_event(logger, "tts_failed", correlation_id=session_id, error=str(error))
                warning = "The transcript is available, but audio playback failed."

            log_event(
                logger,
                "tts_completed",
                correlation_id=session_id,
                latency_ms=(clock() - tts_started) * 1000,
            )
            await send({"event": "dispatcher.speaking", "value": False})

            seconds = round(clock() - started_at)
            transcript.append({"role": "dispatcher", "text": text, "at": clock(), "seconds": seconds})
            await send({"event": "transcript.dispatcher", "text": text, "seconds": seconds})

            if warning:
                await send({"event": "warning", "message": warning})

        async def get_dispatcher_reply(briefing: str) -> tuple[str, bool]:
            call_started = clock()
            timed_out = False
            try:
                reply = await asyncio.wait_for(
                    asyncio.to_thread(dispatcher.respond, conversation, briefing),
                    timeout=CLAUDE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # NFR-02: un timeout de Claude se recupera en el propio diálogo, no tumba la
                # sesión — el hilo del intento original puede seguir corriendo en background,
                # su resultado simplemente se descarta (ClaudeDispatcher ya tiene su propio
                # backoff acotado, un timeout real acá es el caso raro, no el común).
                reply = DISPATCHER_RECOVERY_LINE
                timed_out = True
            except DispatcherError as error:
                log_event(logger, "dispatcher_error", correlation_id=session_id, error=str(error))
                reply = DISPATCHER_RECOVERY_LINE

            log_event(
                logger,
                "dispatcher_completed",
                correlation_id=session_id,
                latency_ms=(clock() - call_started) * 1000,
                timed_out=timed_out,
            )
            conversation.append({"role": "assistant", "content": reply})
            return reply, timed_out

        def handle_turn(event: str) -> str | None:
            """Aplica una transición de turno con el mismo logging estructurado que Fase 1 ya
            tenía (`turn_transition`/`turn_transition_rejected`, NFR-08) — ahora reusado desde
            cada comando en vez de un solo lugar genérico, porque el protocolo real tiene un
            comando distinto por evento en vez de un JSON de evento crudo. Devuelve `None` si la
            transición fue válida, o el mensaje de error si no.
            """

            try:
                new_state = machine.handle(event)
            except InvalidTurnTransitionError as error:
                log_event(
                    logger,
                    "turn_transition_rejected",
                    correlation_id=session_id,
                    event=event,
                    state=machine.state.value,
                    error=str(error),
                )
                return str(error)

            log_event(
                logger,
                "turn_transition",
                correlation_id=session_id,
                event=event,
                from_state=machine.history[-1].from_state.value,
                to_state=new_state.value,
            )
            return None

        async def finish_call(outcome: str) -> None:
            nonlocal call_ended, active_scenario, active_video

            # T15 — guarda de carrera de 2 conexiones (docs/designs/motor-de-metricas.md, hallazgo
            # de la voz independiente de ingeniería): el frontend reconecta automáticamente tras
            # una caída de red reusando el mismo `session_id`/token (no revocable, TTL 8h) — nada
            # en `session_socket` impide 2 conexiones WS concurrentes para la misma sesión. Si la
            # reconexión ya completó y guardó `outcome="ended"` con evaluación real, un
            # `network_drop` tardío de la conexión vieja NO debe sobrescribirlo (`ON CONFLICT DO
            # UPDATE` en `sqlite_store.py` es last-write-wins por defecto — esta lectura previa es
            # la única guarda). Antes esta ventana de carrera era de milisegundos (scoring puro);
            # el judge LLM (más abajo) la amplía a segundos, así que deja de ser solo teórica.
            if outcome == "network_drop":
                existing = session_store.get_session(session_id)
                if existing is not None and existing.outcome == "ended" and existing.evaluation is not None:
                    log_event(
                        logger,
                        "finish_call_skipped_stale_network_drop",
                        correlation_id=session_id,
                    )
                    call_ended = True
                    return

            ended_at = clock()
            critical_data_points = active_scenario.critical_data_points if active_scenario else []
            video_ground_truth = active_video.ground_truth_points if active_video else []
            # Ver comentario en la inicialización de `video_ended_at` sobre por qué se valida
            # contra `video_ended_scenario_id` en vez de usarse tal cual.
            reaction_video_ended_at = (
                video_ended_at
                if active_scenario and video_ended_scenario_id == active_scenario.id
                else None
            )
            evaluation = score_session(
                transcript,
                critical_data_points,
                started_at,
                ended_at,
                outcome,
                video_ground_truth=video_ground_truth,
                video_ended_at=reaction_video_ended_at,
                turn_history=machine.history,
            )

            # T4/T13/T14 (docs/designs/motor-de-metricas.md): `score_session` es puro (ADR-0006)
            # y ya deja `communication_coaching` con `transcription_confidence`/`coherence`/
            # `english_quality` en `None` — se completan aquí, en `finish_call`, que sí puede
            # tocar adaptadores con red. Todo detrás de `if evaluation is not None`: cuando
            # `outcome=="network_drop"`, `score_session` devuelve `None` y esto se salta por
            # completo — ni el juez LLM ni el cómputo de confianza de transcripción corren en una
            # desconexión trivial (gate explícito que la voz independiente marcó como CRÍTICO:
            # sin él, se quema costo/latencia de Claude en cada "conectó y se cayó").
            if evaluation is not None:
                evaluation["communication_coaching"]["transcription_confidence"] = (
                    rate_transcription_confidence(aggregate_transcription_confidence(stt_segments))
                )
                if stt_metrics_store is not None:
                    # Riesgo aceptado y documentado (Fase 3 Sección 1/5 del plan): esta escritura
                    # y `session_store.save_session()` más abajo no son atómicas entre sí — ver
                    # `persistence/sqlite_stt_metrics_store.py`.
                    stt_metrics_store.save_segments(session_id, stt_segments)

                if metrics_judge is not None:
                    try:
                        judgment = await asyncio.wait_for(
                            asyncio.to_thread(
                                metrics_judge.judge,
                                transcript,
                                critical_data_points,
                                evaluation["collected"],
                                evaluation["missing"],
                            ),
                            timeout=CLAUDE_TIMEOUT_SECONDS,
                        )
                        evaluation["communication_coaching"]["coherence"] = {
                            "rating": judgment.coherence_rating,
                            "tip": judgment.coherence_tip,
                        }
                        evaluation["communication_coaching"]["english_quality"] = {
                            "rating": judgment.english_quality_rating,
                            "tip": judgment.english_quality_tip,
                        }
                        evaluation["judge_unavailable"] = False
                        log_event(
                            logger,
                            "metrics_judge_completed",
                            correlation_id=session_id,
                            completeness_agrees_with_keyword_match=judgment.completeness_agrees_with_keyword_match,
                        )
                    except (asyncio.TimeoutError, MetricsJudgeError) as error:
                        # Degradación explícita (Fase 1 Sección 2 del plan) — nunca tumba
                        # `finish_call`: la sesión se guarda igual con las 4 categorías
                        # rule-based + latencia de turno + confianza de transcripción intactas.
                        log_event(
                            logger,
                            "metrics_judge_unavailable",
                            correlation_id=session_id,
                            error=str(error),
                        )
                        evaluation["judge_unavailable"] = True
                else:
                    evaluation["judge_unavailable"] = True

            record = SessionRecord(
                session_id=session_id,
                supervisor_id=claims.supervisor_id,
                scenario_name=active_scenario.title if active_scenario else "unknown",
                scenario_id=active_scenario.id if active_scenario else "",
                started_at=started_at,
                ended_at=ended_at,
                turns=[
                    # `at` agregado (T1, docs/designs/motor-de-metricas.md): antes se descartaba
                    # al persistir aunque `machine.history` siempre lo tuvo — permite recalcular/
                    # auditar la latencia de turno después sin re-instrumentar nada.
                    {"event": t.event, "from": t.from_state.value, "to": t.to_state.value, "at": t.at}
                    for t in machine.history
                ],
                transcript=transcript,
                evaluation=evaluation,
                outcome=outcome,
                difficulty=call_config["difficulty"],
                language=call_config["language"],
                training_type=call_config["training_type"],
            )
            session_store.save_session(record)
            call_ended = True

            if outcome == "ended":
                await send({"event": "call.status", "status": "completed"})
                await send({"event": "session.completed", "session": _training_session(record)})

            active_scenario = None
            active_video = None

        try:
            await send({"event": "system.ready", "version": PROTOCOL_VERSION})
            await send_scenarios()
            await send_history()

            while True:
                message = await websocket.receive_json()
                command = message.get("command")

                if command == "system.ping":
                    await send({"event": "system.ready", "version": PROTOCOL_VERSION})

                elif command == "scenarios.list":
                    await send_scenarios()

                elif command == "history.list":
                    await send_history()

                elif command == "video.ended":
                    # Ver docs/designs/escenarios-de-video.md (Design, hallazgo 2): el cliente
                    # manda esto cuando el entrenando terminó de ver el video pre-llamada (o lo
                    # saltó) — antes de `call.start`, nunca durante la llamada. Sin auto-avance:
                    # esto solo registra el timestamp, el cliente decide cuándo mandar
                    # `call.start` después (interstitial de calma, no auto-avanzante).
                    video_ended_scenario_id = message.get("scenarioId", "")
                    video_ended_at = clock()

                elif command == "call.start":
                    scenario = scenario_store.get(message.get("scenarioId", ""))
                    if scenario is None:
                        await send({"event": "error", "message": "Unknown scenario.", "recoverable": True})
                        continue

                    active_scenario = scenario
                    active_video = scenario_video_store.get(scenario.id) if scenario_video_store else None
                    call_config = {
                        "difficulty": message.get("difficulty", ""),
                        "language": message.get("language", ""),
                        "training_type": message.get("trainingType", ""),
                    }
                    conversation = []
                    transcript = []
                    stt_segments = []
                    started_at = clock()
                    machine = TurnStateMachine(clock=clock)
                    call_ended = False

                    await send({"event": "call.status", "status": "connecting"})
                    await send({"event": "engine.activity", "message": "Checking microphone…"})

                    mic_ok = await asyncio.to_thread(microphone.is_available)

                    await send({"event": "engine.activity", "message": None})

                    if not mic_ok:
                        await send({"event": "error", "message": "No microphone was detected.", "recoverable": True})
                        await send({"event": "call.status", "status": "error"})
                        active_scenario = None
                        active_video = None
                        continue

                    call_started_once = True

                    await send({
                        "event": "call.started",
                        "sessionId": session_id,
                        "scenario": _scenario_summary(scenario, scenario_video_store),
                    })
                    await send({"event": "call.status", "status": "connected"})

                    handle_turn("dispatcher_greeting")
                    # La API de Claude exige que el primer mensaje sea "user" y alterne desde
                    # ahí — este mensaje sintético nunca toca `transcript` (solo `conversation`,
                    # lo que se le manda a Claude), así que no aparece en la UI ni en el scoring.
                    conversation.append({
                        "role": "user",
                        "content": "[The call has just connected. Greet the caller.]",
                    })
                    greeting, _ = await get_dispatcher_reply(scenario.briefing)
                    await speak_dispatcher_line(greeting)
                    handle_turn("dispatcher_finished_speaking")

                elif command == "recording.start":
                    if active_scenario is None:
                        await send({"event": "error", "message": "Call has not started.", "recoverable": True})
                        continue

                    error = handle_turn("supervisor_started_speaking")
                    if error:
                        await send({"event": "error", "message": error, "recoverable": True})
                        continue

                    await asyncio.to_thread(microphone.start_recording)
                    await send({"event": "operator.speaking", "value": True})

                elif command == "recording.stop":
                    await send({"event": "operator.speaking", "value": False})

                    error = handle_turn("supervisor_stopped_speaking")
                    if error:
                        await send({"event": "error", "message": error, "recoverable": True})
                        continue

                    await send({"event": "call.status", "status": "processing"})
                    await send({"event": "engine.activity", "message": "Transcribing…"})

                    stt_started = clock()
                    try:
                        audio_path = await asyncio.to_thread(microphone.stop_recording)
                        transcription = await asyncio.to_thread(stt.transcribe, audio_path)
                    except Exception as error:  # noqa: BLE001 — falla real de hardware/mic (ej. "no audio grabado"): recuperable, no debe tumbar la sesión (contrato §7).
                        log_event(logger, "stt_failed", correlation_id=session_id, error=str(error))
                        await send({"event": "engine.activity", "message": None})
                        await send({"event": "error", "message": "No speech was detected. Please try again.", "recoverable": True})
                        await send({"event": "call.status", "status": "connected"})
                        continue

                    text = transcription.text
                    # T2/T4 (docs/designs/motor-de-metricas.md): antes de este cambio,
                    # `low_confidence_segment_count` se derivaba del marcador inline
                    # `[unclear: ...]` porque `transcribe()` solo devolvía un `str` — ahora
                    # `TranscriptionResult.segments` ya trae `is_low_confidence` calculado, y se
                    # acumulan para la tip-card de confianza de transcripción al terminar la
                    # llamada (nunca llamada "acento" — ver `core/transcription_confidence.py`).
                    stt_segments.extend(transcription.segments)

                    log_event(
                        logger,
                        "stt_completed",
                        correlation_id=session_id,
                        latency_ms=(clock() - stt_started) * 1000,
                        low_confidence_segment_count=sum(1 for s in transcription.segments if s.is_low_confidence),
                    )

                    await send({"event": "engine.activity", "message": None})

                    if not text:
                        await send({"event": "error", "message": "No speech was detected. Please try again.", "recoverable": True})
                        await send({"event": "call.status", "status": "connected"})
                        continue

                    seconds = round(clock() - started_at)
                    conversation.append({"role": "user", "content": text})
                    transcript.append({"role": "operator", "text": text, "at": clock(), "seconds": seconds})
                    await send({"event": "transcript.operator", "text": text, "seconds": seconds})

                    reply, _ = await get_dispatcher_reply(active_scenario.briefing)
                    handle_turn("dispatcher_response_ready")
                    await speak_dispatcher_line(reply)
                    handle_turn("dispatcher_finished_speaking")
                    await send({"event": "call.status", "status": "connected"})

                elif command == "call.pause":
                    error = handle_turn("pause_requested")
                    if error:
                        await send({"event": "error", "message": error, "recoverable": True})
                        continue
                    await send({"event": "call.status", "status": "paused"})

                elif command == "call.resume":
                    error = handle_turn("resume_requested")
                    if error:
                        await send({"event": "error", "message": error, "recoverable": True})
                        continue
                    await send({"event": "call.status", "status": "connected"})

                elif command == "call.end":
                    await finish_call(outcome="ended")

                else:
                    await send({"event": "error", "message": f"Unknown command: {command!r}", "recoverable": True})

        except WebSocketDisconnect:
            pass
        finally:
            # NFR-02/roadmap: "la sesión queda registrada" incluso si la conexión se cae en
            # cualquier estado, no solo en el camino feliz de fin de llamada. Si ya se procesó
            # un `call.end` explícito, `call_ended` es `True` y no hay nada más que persistir;
            # si nunca hubo un `call.start` (solo se conectó y se desconectó), no hay sesión de
            # práctica real que registrar — evita un registro fantasma con un score fabricado.
            if not call_ended and call_started_once:
                await finish_call(outcome="network_drop")

            ended_at = clock()
            log_event(
                logger,
                "session_disconnected",
                correlation_id=session_id,
                supervisor_id=claims.supervisor_id,
                duration_seconds=ended_at - started_at,
                turn_count=len(machine.history),
            )

    return app


def _remove_if_exists(path: str) -> None:
    # Limpieza de un `.part` a medio escribir si el upload falla (tamaño excedido, etc.) — no
    # hay nada que hacer si ya no está ahí, así que se ignora ese caso puntual.
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _sha256_of_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Checksum server-side del archivo de video (ADR-0009/ADR-0010) — nunca confía en un
    checksum que mandara el cliente. Levanta `OSError` tal cual si el archivo no existe/no se
    puede leer; el caller decide cómo traducir eso a una respuesta HTTP."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scenario_video_out(video: ScenarioVideo) -> ScenarioVideoOut:
    return ScenarioVideoOut(
        scenario_id=video.scenario_id,
        video_path=video.video_path,
        video_checksum=video.video_checksum,
        duration_seconds=video.duration_seconds,
        content_type=video.content_type,
        ground_truth_points=[
            VideoGroundTruthPointModel(
                key=p.key,
                label=p.label,
                match_hints=p.match_hints,
                visible_from_seconds=p.visible_from_seconds,
                visible_to_seconds=p.visible_to_seconds,
                required=p.required,
            )
            for p in video.ground_truth_points
        ],
        created_at=video.created_at,
        updated_at=video.updated_at,
    )


def _has_video(scenario_video_store: ScenarioVideoPort | None, scenario_id: str) -> bool:
    return scenario_video_store is not None and scenario_video_store.get(scenario_id) is not None


def _scenario_summary(scenario: Scenario, scenario_video_store: ScenarioVideoPort | None = None) -> dict:
    return {
        "id": scenario.id,
        "title": scenario.title,
        "category": scenario.category,
        "description": scenario.description,
        "difficulty": scenario.difficulty,
        "has_video": _has_video(scenario_video_store, scenario.id),
    }


def _scenario_out(scenario: Scenario, scenario_video_store: ScenarioVideoPort | None = None) -> ScenarioOut:
    return ScenarioOut(
        id=scenario.id,
        title=scenario.title,
        category=scenario.category,
        difficulty=scenario.difficulty,
        language=scenario.language,
        description=scenario.description,
        briefing=scenario.briefing,
        critical_data_points=[
            CriticalDataPointModel(key=p.key, label=p.label, required=p.required, match_hints=p.match_hints)
            for p in scenario.critical_data_points
        ],
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
        has_video=_has_video(scenario_video_store, scenario.id),
    )


def _scenario_fields(body: ScenarioIn) -> dict:
    return {
        "title": body.title,
        "category": body.category,
        "difficulty": body.difficulty,
        "language": body.language,
        "description": body.description,
        "briefing": body.briefing,
        "critical_data_points": [
            CriticalDataPoint(key=p.key, label=p.label, required=p.required, match_hints=p.match_hints)
            for p in body.critical_data_points
        ],
    }


def _incident_out(incident: IncidentOutcome) -> IncidentOut:
    return IncidentOut(
        id=incident.id,
        occurred_at=incident.occurred_at,
        supervisor_id=incident.supervisor_id,
        category=incident.category,
        outcome_rating=incident.outcome_rating,
        critical_data_captured=incident.critical_data_captured,
        protocol_followed=incident.protocol_followed,
        notes=incident.notes,
        reported_by=incident.reported_by,
        promoted_scenario_id=incident.promoted_scenario_id,
        created_at=incident.created_at,
    )


def _training_session(record: SessionRecord) -> dict:
    return {
        "id": record.session_id,
        "scenario_id": record.scenario_id,
        "difficulty": record.difficulty,
        "language": record.language,
        "training_type": record.training_type,
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "status": "completed" if record.outcome == "ended" else "error",
        "transcript": [
            {"role": turn["role"], "text": turn["text"], "seconds": turn.get("seconds", 0)}
            for turn in record.transcript
        ],
        "evaluation": record.evaluation,
    }
