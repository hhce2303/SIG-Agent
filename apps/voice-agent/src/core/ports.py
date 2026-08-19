"""Puertos del dominio (hexagonal) — ver ADR-0006.

El dominio (`core/conversation.py`) depende únicamente de estas interfaces, nunca de las
implementaciones concretas en `stt/`, `tts/`, `llm/` o `audio/`. Los adaptadores (`WhisperSTT`,
`KokoroTTS`, `ClaudeDispatcher`, `MicrophoneRecorder`) implementan estos puertos contra
tecnología real, y ahí viven las preocupaciones de resiliencia (retries, timeouts) — nunca aquí.

Son `Protocol` (tipado estructural): un adaptador los cumple por tener los métodos correctos,
sin necesidad de heredar. Las clases existentes heredan de ellos de forma explícita solo para
que el type-checker y los tests de contrato lo dejen documentado.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class DispatcherError(Exception):
    """Error de dominio: el adaptador de LLM no pudo producir una respuesta.

    Se levanta después de que el adaptador agotó sus propios reintentos (esa política vive en
    el adaptador, ver ADR-0006). El dominio (`VoiceConversation`) la captura como un estado de
    primera clase — ver NFR-02 — en vez de dejar que la excepción original tumbe el turno.
    """


@runtime_checkable
class MicrophonePort(Protocol):
    def record(self, output_path: str = ...) -> str:
        ...

    # Fase 2: el servidor real recibe `recording.start`/`recording.stop` como dos comandos WS
    # separados — no puede bloquear en `record()` esperando un `input()` de teclado. El
    # prototipo CLI (`core/conversation.py::VoiceConversation`) sigue usando solo `record()`.
    def start_recording(self, output_path: str = ...) -> None:
        ...

    def stop_recording(self) -> str:
        ...

    # Fase 2: estado de "conectando/chequeo de mic" (roadmap, pulido del loop en vivo) — el
    # servidor pregunta esto antes de aceptar `call.start`, en vez de descubrir que no hay
    # micrófono recién en el primer `recording.start`.
    def is_available(self) -> bool:
        ...


@runtime_checkable
class SpeechToTextPort(Protocol):
    def transcribe(self, audio_path: str) -> str:
        ...


@runtime_checkable
class TextToSpeechPort(Protocol):
    def speak(self, text: str, voice: str | None = None) -> None:
        ...


@runtime_checkable
class DispatcherPort(Protocol):
    def respond(
        self,
        conversation: list[dict[str, str]],
        scenario: str,
    ) -> str:
        ...


# ---------------------------------------------------------------------------
# Escenarios — Fase 2 (roadmap). TODO-11 resuelto: campos estructurados guiados + una
# narrativa libre, no texto libre puro (determina un formulario validado, no un editor de
# texto/plantillas). `critical_data_points` es el puente hacia el motor de métricas: la
# "completitud" de Fase 2 se mide contra esta lista, no adivinada del texto del escenario.
# ---------------------------------------------------------------------------


@dataclass
class CriticalDataPoint:
    key: str
    label: str
    required: bool = True


@dataclass
class Scenario:
    id: str
    title: str
    category: str
    difficulty: str
    language: str
    description: str
    briefing: str
    critical_data_points: list[CriticalDataPoint] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


DEFAULT_TTS_VOICE = "am_michael"


@runtime_checkable
class SettingsPort(Protocol):
    """Ajustes globales — roadmap Fase 2 ("la pieza más chica, alcance mínimo").

    Una sola fila global (concurrencia=1, NFR-11) — no hay ajustes por supervisor. Sensibilidad
    de VAD queda fuera a propósito: no hay VAD automático implementado (ver ADR-0005/roadmap),
    así que ese ajuste no tendría nada que controlar todavía.
    """

    def get_tts_voice(self) -> str:
        ...

    def set_tts_voice(self, voice: str) -> None:
        ...


@runtime_checkable
class ScenarioPort(Protocol):
    def list(self) -> list[Scenario]:
        ...

    def get(self, scenario_id: str) -> Scenario | None:
        ...

    def create(self, scenario: Scenario) -> None:
        ...

    def update(self, scenario: Scenario) -> None:
        ...

    def delete(self, scenario_id: str) -> None:
        ...


# ---------------------------------------------------------------------------
# Persistencia de sesión — ver ADR-0007 (motor de persistencia, accepted 2026-08-19).
# ---------------------------------------------------------------------------


@dataclass
class SessionRecord:
    """Registro de una sesión de práctica — lo que el hito de cierre de Fase 1 llama

    'la sesión queda registrada'. `started_at`/`ended_at` son timestamps del reloj del
    servidor (roadmap: "reloj del servidor como autoridad única para métricas de tiempo"), no
    del cliente — se pasan ya calculados, este dataclass no llama a ningún reloj.

    Fase 2 amplía el registro más allá de las transiciones de turno: `transcript` guarda el
    texto real de la llamada (antes solo se guardaban eventos de la máquina de estados),
    `evaluation` es la salida de `core/scoring.py::score_session` (`None` si `outcome` es
    `"network_drop"` — sin puntaje punitivo por una caída de red, ver roadmap Fase 2), y
    `outcome` distingue cómo terminó la sesión (`"ended"` | `"network_drop"`).
    """

    session_id: str
    supervisor_id: str
    scenario_name: str
    started_at: float
    ended_at: float | None = None
    turns: list[dict[str, str]] = field(default_factory=list)
    scenario_id: str = ""
    transcript: list[dict] = field(default_factory=list)
    evaluation: dict | None = None
    outcome: str = "ended"
    # Elegidos por el trainee en `call.start` (`EngineCommand` de `frontend/src/types.ts`) —
    # independientes de los metadatos propios del `Scenario` (un mismo escenario se puede
    # practicar en más de una dificultad/idioma).
    difficulty: str = ""
    language: str = ""
    training_type: str = ""


@runtime_checkable
class PersistencePort(Protocol):
    def save_session(self, session: SessionRecord) -> None:
        ...

    def get_session(self, session_id: str) -> SessionRecord | None:
        ...

    def list_sessions(self, supervisor_id: str) -> list[SessionRecord]:
        ...


# ---------------------------------------------------------------------------
# Auth por sesión — ver ADR-0008 (mecanismo de autenticación, accepted 2026-08-19), NFR-04.
# ---------------------------------------------------------------------------


class InvalidSessionTokenError(Exception):
    """Token de sesión ausente, corrupto, con firma inválida, o expirado.

    Error de dominio (no una excepción específica de la librería de firma que use el
    adaptador) — quien valida una conexión WebSocket entrante captura esto, nunca una excepción
    de bajo nivel de HMAC/JSON.
    """


@dataclass(frozen=True)
class SessionTokenClaims:
    supervisor_id: str
    session_id: str
    issued_at: float


@runtime_checkable
class SessionTokenPort(Protocol):
    def issue(self, supervisor_id: str, session_id: str) -> str:
        ...

    def verify(self, token: str) -> SessionTokenClaims:
        ...


# ---------------------------------------------------------------------------
# Incidentes reales — roadmap Fase 3 ("cierre del lazo de impacto real"). Captura manual
# (decisión del usuario: no existe ningún sistema de post-mortems/incidentes con el que
# integrar todavía) de un incidente real ya resuelto, para dos fines separados del roadmap:
# 1. Métrica de resultado real: `core/impact_metrics.py` correlaciona esto contra
#    `PersistencePort.list_sessions` (¿el supervisor había completado entrenamiento antes de la
#    fecha del incidente?) — la etiqueta "entrenado/no entrenado" nunca se captura a mano, se
#    deriva de sesiones reales para no depender de que alguien la recuerde bien.
# 2. Lazo de retroalimentación: `notes` (el post-mortem en texto libre) es la fuente de la que
#    se puede promover un `Scenario` nuevo — ver `promoted_scenario_id` y el endpoint
#    `POST /incidents/{id}/promote-to-scenario` en `server/app.py`.
#
# Sin control de acceso por rol (no existe ese concepto en este repo — ver TODO-15): cualquier
# sesión autenticada puede crear/leer/promover incidentes, igual que ya pasa hoy con el CRUD de
# escenarios. Documentado como brecha conocida, no como omisión silenciosa.
# ---------------------------------------------------------------------------


@dataclass
class IncidentOutcome:
    id: str
    occurred_at: float
    supervisor_id: str
    category: str
    outcome_rating: int  # 1-5, asignado por quien registra el incidente (manager/RRHH)
    critical_data_captured: bool
    protocol_followed: bool
    notes: str = ""  # post-mortem en texto libre — fuente del lazo de retroalimentación
    reported_by: str = ""
    promoted_scenario_id: str = ""  # no vacío una vez que alimentó la librería de escenarios
    created_at: float = 0.0


@runtime_checkable
class IncidentOutcomePort(Protocol):
    def list(self) -> list[IncidentOutcome]:
        ...

    def get(self, incident_id: str) -> IncidentOutcome | None:
        ...

    def create(self, incident: IncidentOutcome) -> None:
        ...

    def delete(self, incident_id: str) -> None:
        ...

    def mark_promoted(self, incident_id: str, scenario_id: str) -> None:
        ...
