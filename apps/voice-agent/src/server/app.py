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
import logging
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException
from pydantic import BaseModel, Field
from starlette import status

from core.conversation import DISPATCHER_RECOVERY_LINE
from core.observability import log_event
from core.ports import (
    CriticalDataPoint,
    DispatcherError,
    DispatcherPort,
    InvalidSessionTokenError,
    MicrophonePort,
    PersistencePort,
    Scenario,
    ScenarioPort,
    SessionRecord,
    SessionTokenClaims,
    SessionTokenPort,
    SettingsPort,
    SpeechToTextPort,
    TextToSpeechPort,
)
from core.scoring import score_session
from core.turn_state import InvalidTurnTransitionError, TurnStateMachine

logger = logging.getLogger("voice_agent.server")

PROTOCOL_VERSION = "0.3.0"  # Fase 2: protocolo completo de comandos/eventos, no solo turn-state
CLAUDE_TIMEOUT_SECONDS = 8.0


class LoginRequest(BaseModel):
    supervisor_id: str
    passphrase: str


class LoginResponse(BaseModel):
    session_id: str
    token: str


class CriticalDataPointModel(BaseModel):
    key: str
    label: str
    required: bool = True


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


class SettingsModel(BaseModel):
    tts_voice: str


def create_app(
    token_issuer: SessionTokenPort,
    session_store: PersistencePort,
    scenario_store: ScenarioPort,
    settings_store: SettingsPort,
    supervisor_passphrase: str,
    dispatcher: DispatcherPort,
    stt: SpeechToTextPort,
    tts: TextToSpeechPort,
    microphone: MicrophonePort,
    clock=time.time,
) -> FastAPI:
    """Factory (no una `app` global a nivel de módulo) para que los tests puedan inyectar
    dobles de prueba de cada puerto sin compartir estado entre tests ni depender de
    Whisper/Kokoro/Claude/sounddevice reales.
    """

    app = FastAPI(title="voice-agent server")

    def _bearer_claims(authorization: str | None = Header(default=None)) -> SessionTokenClaims:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")

        try:
            return token_issuer.verify(authorization.split(" ", 1)[1])
        except InvalidSessionTokenError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    # -----------------------------------------------------------------
    # REST — salud, auth (sin cambios de Fase 1), escenarios y ajustes (nuevo, Fase 2).
    # -----------------------------------------------------------------

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/login", response_model=LoginResponse)
    def login(body: LoginRequest):
        if body.passphrase != supervisor_passphrase:
            log_event(logger, "login_failed", supervisor_id=body.supervisor_id)
            raise HTTPException(status_code=401, detail="invalid credentials")

        session_id = str(uuid.uuid4())
        token = token_issuer.issue(supervisor_id=body.supervisor_id, session_id=session_id)

        log_event(
            logger, "login_succeeded", correlation_id=session_id, supervisor_id=body.supervisor_id
        )

        return LoginResponse(session_id=session_id, token=token)

    @app.get("/scenarios", response_model=list[ScenarioOut])
    def list_scenarios(claims: SessionTokenClaims = Depends(_bearer_claims)):
        return [_scenario_out(scenario) for scenario in scenario_store.list()]

    @app.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
    def get_scenario(scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        scenario = scenario_store.get(scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        return _scenario_out(scenario)

    @app.post("/scenarios", response_model=ScenarioOut, status_code=201)
    def create_scenario(body: ScenarioIn, claims: SessionTokenClaims = Depends(_bearer_claims)):
        scenario = Scenario(id="", **_scenario_fields(body))
        scenario_store.create(scenario)
        log_event(logger, "scenario_created", supervisor_id=claims.supervisor_id, scenario_id=scenario.id)
        return _scenario_out(scenario)

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
        return _scenario_out(existing)

    @app.delete("/scenarios/{scenario_id}", status_code=204)
    def delete_scenario(scenario_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        scenario_store.delete(scenario_id)
        log_event(logger, "scenario_deleted", supervisor_id=claims.supervisor_id, scenario_id=scenario_id)

    @app.get("/settings", response_model=SettingsModel)
    def get_settings(claims: SessionTokenClaims = Depends(_bearer_claims)):
        return SettingsModel(tts_voice=settings_store.get_tts_voice())

    @app.put("/settings", response_model=SettingsModel)
    def put_settings(body: SettingsModel, claims: SessionTokenClaims = Depends(_bearer_claims)):
        settings_store.set_tts_voice(body.tts_voice)
        return SettingsModel(tts_voice=settings_store.get_tts_voice())

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
        active_scenario: Scenario | None = None
        call_config = {"difficulty": "", "language": "", "training_type": ""}
        call_ended = False  # True una vez que un `call.end` explícito ya persistió la sesión.
        call_started_once = False  # Evita persistir un registro fantasma si nunca hubo `call.start`.

        async def send(payload: dict) -> None:
            await websocket.send_json(payload)

        async def send_scenarios() -> None:
            await send({
                "event": "scenarios.data",
                "scenarios": [_scenario_summary(s) for s in scenario_store.list()],
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
            nonlocal call_ended, active_scenario

            ended_at = clock()
            critical_data_points = active_scenario.critical_data_points if active_scenario else []
            evaluation = score_session(transcript, critical_data_points, started_at, ended_at, outcome)

            record = SessionRecord(
                session_id=session_id,
                supervisor_id=claims.supervisor_id,
                scenario_name=active_scenario.title if active_scenario else "unknown",
                scenario_id=active_scenario.id if active_scenario else "",
                started_at=started_at,
                ended_at=ended_at,
                turns=[
                    {"event": t.event, "from": t.from_state.value, "to": t.to_state.value}
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

                elif command == "call.start":
                    scenario = scenario_store.get(message.get("scenarioId", ""))
                    if scenario is None:
                        await send({"event": "error", "message": "Unknown scenario.", "recoverable": True})
                        continue

                    active_scenario = scenario
                    call_config = {
                        "difficulty": message.get("difficulty", ""),
                        "language": message.get("language", ""),
                        "training_type": message.get("trainingType", ""),
                    }
                    conversation = []
                    transcript = []
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
                        continue

                    call_started_once = True

                    await send({
                        "event": "call.started",
                        "sessionId": session_id,
                        "scenario": _scenario_summary(scenario),
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
                        text = await asyncio.to_thread(stt.transcribe, audio_path)
                    except Exception as error:  # noqa: BLE001 — falla real de hardware/mic (ej. "no audio grabado"): recuperable, no debe tumbar la sesión (contrato §7).
                        log_event(logger, "stt_failed", correlation_id=session_id, error=str(error))
                        await send({"event": "engine.activity", "message": None})
                        await send({"event": "error", "message": "No speech was detected. Please try again.", "recoverable": True})
                        await send({"event": "call.status", "status": "connected"})
                        continue

                    log_event(
                        logger,
                        "stt_completed",
                        correlation_id=session_id,
                        latency_ms=(clock() - stt_started) * 1000,
                        # NFR-09/NFR-08: confianza por segmento sin cambiar la firma de
                        # `SpeechToTextPort.transcribe()` (ver docstring de `stt/whisper.py`) —
                        # se deriva del marcador inline que ya produce el adaptador.
                        low_confidence_segment_count=text.count("[unclear:"),
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


def _scenario_summary(scenario: Scenario) -> dict:
    return {
        "id": scenario.id,
        "title": scenario.title,
        "category": scenario.category,
        "description": scenario.description,
        "difficulty": scenario.difficulty,
    }


def _scenario_out(scenario: Scenario) -> ScenarioOut:
    return ScenarioOut(
        id=scenario.id,
        title=scenario.title,
        category=scenario.category,
        difficulty=scenario.difficulty,
        language=scenario.language,
        description=scenario.description,
        briefing=scenario.briefing,
        critical_data_points=[
            CriticalDataPointModel(key=p.key, label=p.label, required=p.required)
            for p in scenario.critical_data_points
        ],
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
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
            CriticalDataPoint(key=p.key, label=p.label, required=p.required)
            for p in body.critical_data_points
        ],
    }


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
