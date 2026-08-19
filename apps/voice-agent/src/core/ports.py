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


@runtime_checkable
class SpeechToTextPort(Protocol):
    def transcribe(self, audio_path: str) -> str:
        ...


@runtime_checkable
class TextToSpeechPort(Protocol):
    def speak(self, text: str) -> None:
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
# Persistencia de sesión — ver ADR-0007 (motor de persistencia, accepted 2026-08-19).
# ---------------------------------------------------------------------------


@dataclass
class SessionRecord:
    """Registro de una sesión de práctica — lo que el hito de cierre de Fase 1 llama

    'la sesión queda registrada'. `started_at`/`ended_at` son timestamps del reloj del
    servidor (roadmap: "reloj del servidor como autoridad única para métricas de tiempo"), no
    del cliente — se pasan ya calculados, este dataclass no llama a ningún reloj.
    """

    session_id: str
    supervisor_id: str
    scenario_name: str
    started_at: float
    ended_at: float | None = None
    turns: list[dict[str, str]] = field(default_factory=list)


@runtime_checkable
class PersistencePort(Protocol):
    def save_session(self, session: SessionRecord) -> None:
        ...

    def get_session(self, session_id: str) -> SessionRecord | None:
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
