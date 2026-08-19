"""Máquina de estados de turno — roadmap Fase 1 ("State machine de turnos explícito").

Dominio puro: no importa FastAPI, WebSocket, ni ningún adaptador (ADR-0006). El server que
todavía no existe (ver `docs/architecture/PHASE1-PROGRESS.md`) es quien conecta esto a una
conexión real y a los puertos de `core/ports.py`.

Estados explícitos que pide el roadmap: listening / supervisor_speaking / processing (con
timeout y fallback) / dispatcher_speaking / false_cutoff_recovery / degraded_network /
disconnected. El reloj (`clock`, inyectado) es la autoridad única para las métricas de tiempo
(NFR-08) — nunca un timestamp de cliente.
"""

import time
from dataclasses import dataclass
from enum import Enum


class TurnState(Enum):
    LISTENING = "listening"
    SUPERVISOR_SPEAKING = "supervisor_speaking"
    PROCESSING = "processing"
    DISPATCHER_SPEAKING = "dispatcher_speaking"
    FALSE_CUTOFF_RECOVERY = "false_cutoff_recovery"
    DEGRADED_NETWORK = "degraded_network"
    DISCONNECTED = "disconnected"
    # Fase 2 (roadmap: "control de pausa/abortar la práctica") — `call.pause`/`call.resume`
    # del protocolo WS no tenían dónde vivir en la máquina de estados hasta ahora.
    PAUSED = "paused"


class InvalidTurnTransitionError(Exception):
    """Se pidió un evento que la máquina de estados no permite desde el estado actual.

    No es un detalle interno a ignorar — un evento inesperado (ej. "dispatcher_response_ready"
    mientras se está en `listening`) indica un bug en quien orquesta la conexión, y NFR-02 pide
    que ningún error quede sin un estado de recuperación definido; dejar que esto explote en
    vez de transicionar en silencio a un estado incorrecto es la recuperación correcta acá.
    """


@dataclass(frozen=True)
class TurnTransition:
    from_state: TurnState
    to_state: TurnState
    event: str
    at: float


# Transiciones normales, una por estado de origen. PROCESSING → DISPATCHER_SPEAKING también
# ante "processing_timed_out": el fallback de un timeout es la misma línea de recuperación en
# diálogo que un error de Claude (ver `core/conversation.py`), no un estado nuevo separado.
_TRANSITIONS: dict[TurnState, dict[str, TurnState]] = {
    TurnState.LISTENING: {
        "supervisor_started_speaking": TurnState.SUPERVISOR_SPEAKING,
        "pause_requested": TurnState.PAUSED,
        # El dispatcher saluda primero al iniciar la llamada (roadmap: orden mínimo de eventos
        # de `frontend/BACKEND_REQUIREMENTS.md` §6) — única forma de llegar a
        # `dispatcher_speaking` sin pasar por `processing` primero.
        "dispatcher_greeting": TurnState.DISPATCHER_SPEAKING,
    },
    TurnState.SUPERVISOR_SPEAKING: {
        "supervisor_stopped_speaking": TurnState.PROCESSING,
        "false_cutoff_detected": TurnState.FALSE_CUTOFF_RECOVERY,
        "pause_requested": TurnState.PAUSED,
    },
    TurnState.PROCESSING: {
        "dispatcher_response_ready": TurnState.DISPATCHER_SPEAKING,
        "processing_timed_out": TurnState.DISPATCHER_SPEAKING,
        "pause_requested": TurnState.PAUSED,
    },
    TurnState.DISPATCHER_SPEAKING: {
        "dispatcher_finished_speaking": TurnState.LISTENING,
        "pause_requested": TurnState.PAUSED,
    },
    TurnState.FALSE_CUTOFF_RECOVERY: {
        "resume_listening": TurnState.SUPERVISOR_SPEAKING,
    },
    TurnState.DEGRADED_NETWORK: {
        "network_restored": TurnState.LISTENING,
    },
    # Fase 2: reanudar siempre vuelve a `listening`, nunca al estado exacto de antes de la
    # pausa — es la misma simplificación que ya hace `network_restored`, y evita tener que
    # recordar/serializar "en qué estaba" mientras estuvo pausada.
    TurnState.PAUSED: {
        "resume_requested": TurnState.LISTENING,
    },
}

# Una caída de red o una desconexión no esperan su turno — válidas desde cualquier estado no
# terminal, no solo desde los que las listan explícitamente arriba.
_GLOBAL_EVENTS: dict[str, TurnState] = {
    "network_degraded": TurnState.DEGRADED_NETWORK,
    "disconnected": TurnState.DISCONNECTED,
}


class TurnStateMachine:

    def __init__(self, clock=time.time):
        self._clock = clock
        self.state = TurnState.LISTENING
        self.history: list[TurnTransition] = []

    def handle(self, event: str) -> TurnState:
        next_state = self._resolve(event)
        self._record(event, next_state)

        return self.state

    def _resolve(self, event: str) -> TurnState:
        if self.state is TurnState.DISCONNECTED:
            if event == "reconnected":
                return TurnState.LISTENING

            raise InvalidTurnTransitionError(
                f"cannot handle '{event}' — session is disconnected, only 'reconnected' is valid"
            )

        next_state = _GLOBAL_EVENTS.get(event) or _TRANSITIONS.get(self.state, {}).get(event)

        if next_state is None:
            raise InvalidTurnTransitionError(
                f"event '{event}' is not valid from state '{self.state.value}'"
            )

        return next_state

    def _record(self, event: str, next_state: TurnState) -> None:
        self.history.append(
            TurnTransition(
                from_state=self.state,
                to_state=next_state,
                event=event,
                at=self._clock(),
            )
        )
        self.state = next_state
