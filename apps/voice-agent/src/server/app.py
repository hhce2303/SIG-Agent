"""Servidor FastAPI/WebSocket — roadmap Fase 1 ("Core async de servidor + pipeline de audio").

Cubre el ciclo de vida de una conexión de sesión: login (ADR-0008) → handshake de WebSocket
autenticado (NFR-04: una conexión no puede apuntar a la sesión de otra) → sincronización de
eventos de turno contra `TurnStateMachine` (core/turn_state.py) → registro de la sesión al
desconectar (ADR-0007, PersistencePort).

**Lo que este módulo NO decide todavía, a propósito:** el protocolo de streaming de audio en sí
(formato de chunk PCM, punto exacto de integración de VAD, tamaño de buffer). Eso depende del
resultado del spike de latencia de Gate 0 (TODO-08) y no está fijado en ningún ADR — inventarlo
aquí violaría la regla "ADR-first" de CONTRIBUTING.md. Este servidor sincroniza *eventos de
turno* como JSON sobre WebSocket; el día que exista un ADR de protocolo de audio, ese transporte
se agrega junto al mismo `TurnStateMachine`, no reemplazándolo.
"""

import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException
from pydantic import BaseModel
from starlette import status

from core.observability import log_event
from core.ports import (
    InvalidSessionTokenError,
    PersistencePort,
    SessionRecord,
    SessionTokenPort,
)
from core.turn_state import InvalidTurnTransitionError, TurnStateMachine

logger = logging.getLogger("voice_agent.server")


class LoginRequest(BaseModel):
    supervisor_id: str
    passphrase: str


class LoginResponse(BaseModel):
    session_id: str
    token: str


def create_app(
    token_issuer: SessionTokenPort,
    session_store: PersistencePort,
    supervisor_passphrase: str,
    clock=time.time,
) -> FastAPI:
    """Factory (no una `app` global a nivel de módulo) para que los tests puedan inyectar un
    `SQLiteSessionStore`/`HmacSessionTokenIssuer` de prueba sin compartir estado entre tests.

    `supervisor_passphrase` es el mecanismo mínimo de ADR-0008: credenciales propias del sistema,
    sin directorio externo (TODO-02 sigue sin dueño para confirmar si hace falta SSO en su
    lugar). Para 1 sola ubicación / concurrencia=1 (NFR-11) esto es "el supervisor demuestra que
    tiene acceso autorizado a la caja", no un sistema de identidad multi-tenant.
    """

    app = FastAPI(title="voice-agent server (Fase 1)")

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
            logger,
            "login_succeeded",
            correlation_id=session_id,
            supervisor_id=body.supervisor_id,
        )

        return LoginResponse(session_id=session_id, token=token)

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
            logger,
            "session_connected",
            correlation_id=session_id,
            supervisor_id=claims.supervisor_id,
        )

        machine = TurnStateMachine(clock=clock)
        started_at = clock()

        try:
            while True:
                message = await websocket.receive_json()
                event = message.get("event")

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
                    await websocket.send_json({"error": str(error), "state": machine.state.value})
                    continue

                log_event(
                    logger,
                    "turn_transition",
                    correlation_id=session_id,
                    event=event,
                    from_state=machine.history[-1].from_state.value,
                    to_state=new_state.value,
                )
                await websocket.send_json({"state": new_state.value})
        except WebSocketDisconnect:
            pass
        finally:
            # NFR-02/roadmap: "la sesión queda registrada" incluso si la conexión se cae en
            # cualquier estado, no solo en el camino feliz de fin de llamada.
            ended_at = clock()
            session_store.save_session(
                SessionRecord(
                    session_id=session_id,
                    supervisor_id=claims.supervisor_id,
                    # Escenario todavía hardcodeado: el mecanismo de escenario intercambiable
                    # de Fase 1 (roadmap) no está construido — ver PHASE1-PROGRESS.md.
                    scenario_name="unknown",
                    started_at=started_at,
                    ended_at=ended_at,
                    turns=[
                        {"event": t.event, "from": t.from_state.value, "to": t.to_state.value}
                        for t in machine.history
                    ],
                )
            )
            log_event(
                logger,
                "session_disconnected",
                correlation_id=session_id,
                supervisor_id=claims.supervisor_id,
                duration_seconds=ended_at - started_at,
                turn_count=len(machine.history),
            )

    return app
