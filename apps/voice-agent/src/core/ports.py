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


# ---------------------------------------------------------------------------
# STT estructurado — motor de métricas, docs/designs/motor-de-metricas.md (T2/T12). Antes
# `transcribe()` devolvía un `str` a propósito (ver el docstring que tenía `stt/whisper.py`,
# "evita cambios en cascada") — la migración a un resultado estructurado es deliberada y
# ATÓMICA: todos los implementadores/stubs de `SpeechToTextPort` en este repo se actualizan en el
# mismo cambio (`stt/whisper.py`, `test_stt.py`, `test_conversation.py`, `test_server_app.py`,
# `test_server_video.py` vía import) — ver la revisión de `/autoplan`, Fase 3 Sección 2/5.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SttSegment:
    """Un segmento de faster-whisper, con la señal de confianza que antes se descartaba
    (Fase 1 0B de la revisión: "el dato ya existe en la librería, solo no se guardaba"). No
    incluye una señal de acento — ver el naming: `avg_logprob`/`no_speech_prob`/
    `compression_ratio` conflacionan ruido de fondo, calidad de mic, muletillas y acento sin
    poder separarlos (0A punto 1) — se agregan en `core/transcription_confidence.py` como
    "transcription confidence", nunca como "accent".
    """

    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    start_seconds: float
    end_seconds: float
    is_low_confidence: bool = False


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: list[SttSegment] = field(default_factory=list)
    language_probability: float | None = None


@runtime_checkable
class SpeechToTextPort(Protocol):
    def transcribe(self, audio_path: str) -> TranscriptionResult:
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
# Juez de métricas (LLM) — motor de métricas, docs/designs/motor-de-metricas.md (T3/T13).
# Adaptador con red (ver `llm/metrics_judge.py`), nunca importado dentro de `core/scoring.py`
# (ADR-0006 — la voz independiente de ingeniería en la revisión de `/autoplan` encontró que la
# ubicación original propuesta, `core/metrics_judge.py`, violaba esto). `finish_call`
# (`server/app.py`) es quien compone el resultado de este puerto con el dict puro que devuelve
# `score_session`, no `scoring.py` mismo.
# ---------------------------------------------------------------------------


class MetricsJudgeError(Exception):
    """El juez LLM no pudo producir un juicio válido (timeout, rate-limit, JSON malformado,
    faltan keys esperadas, fallo de auth). `finish_call` la captura y degrada a
    `communication_coaching.coherence`/`english_quality` en `None` — nunca tumba la sesión
    completa por esto (ver docs/designs/motor-de-metricas.md, Fase 1 Sección 2).
    """


@dataclass(frozen=True)
class MetricsJudgment:
    coherence_rating: str  # "good" | "improve" | "critical"
    coherence_tip: str
    english_quality_rating: str
    english_quality_tip: str
    # Diagnóstico interno, NUNCA una tip-card nueva (la Fase 2 de la revisión ya cerró el panel
    # de coaching en 4 tarjetas: latencia, confianza de transcripción, coherencia, inglés) — sirve
    # para detectar divergencias entre el keyword-matching de `_completeness` y una lectura
    # semántica real, sin reabrir esa categoría ponderada. Ver TODOS.md #1/#5 de la revisión.
    completeness_agrees_with_keyword_match: bool | None
    raw_response: str


@runtime_checkable
class MetricsJudgePort(Protocol):
    def judge(
        self,
        transcript: list[dict],
        critical_data_points: list["CriticalDataPoint"],
        collected: list[str],
        missing: list[str],
    ) -> MetricsJudgment:
        ...


@runtime_checkable
class SttMetricsPort(Protocol):
    """Persistencia del detalle por-segmento de confianza de Whisper (T4, docs/designs/
    motor-de-metricas.md) — tabla nueva (`TODO-20`: nunca `ALTER TABLE` sobre `sessions`),
    detalle de auditoría/depuración para `communication_coaching.transcription_confidence`
    (el agregado en sí ya vive en `evaluation_json`, esto es la evidencia por-segmento detrás)."""

    def save_segments(self, session_id: str, segments: list[SttSegment]) -> None:
        ...

    def get_segments(self, session_id: str) -> list[SttSegment]:
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
    # TODO-17 (docs/architecture/TODOS.md): `label` es una etiqueta de UI ("Vehicle
    # description"), no vocabulario que un reporte en lenguaje natural repita — el matching por
    # palabra clave contra el label solo puntuó 17/100 un reporte real perfecto. `match_hints`
    # son frases de CONTENIDO que quien autora el escenario espera escuchar de verdad (ej.
    # ["toyota camry", "camry", "sedan"] para "Vehicle description") — opcional, retrocompatible
    # (default vacío = mismo comportamiento que antes de este campo), pero se recomienda
    # completarlo para cualquier escenario nuevo. Ver `core/scoring.py::_matches_point`.
    match_hints: list[str] = field(default_factory=list)
    # docs/designs/ubicacion-del-incidente.md (autoplan 2026-08-21/22), Fase 3 Sección 1 —
    # agregados tras un hallazgo crítico de la voz independiente de ingeniería: usar el valor real
    # configurado (ej. "5th Avenue") como `label` para evitar nombres genéricos (0A-5) activaba el
    # fallback de palabra suelta de abajo — "avenue"/"street" sueltos en CUALQUIER transcript
    # marcarían el punto como cumplido. `word_fallback=False` apaga ese último recurso para puntos
    # cuyo label es contenido real, no una etiqueta de UI genérica (default `True` = cero cambio de
    # comportamiento para cualquier punto ya autorado). `counts_toward_timing=False` excluye el
    # punto de `_time_to_critical_data` — cualquier punto nuevo en `all_points` solo puede adelantar
    # o igualar esa categoría (30% del peso total), nunca atrasarla; para datos que no deben
    # re-ponderar silenciosamente esa categoría (ver ubicación del incidente), se apaga (default
    # `True` = cero cambio de comportamiento existente).
    word_fallback: bool = True
    counts_toward_timing: bool = True


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


# ---------------------------------------------------------------------------
# Escenarios de video — ver docs/designs/escenarios-de-video.md (autoplan 2026-08-21) y
# ADR-0009/ADR-0010. `Scenario` queda SIN CAMBIOS a propósito (ver hallazgo de ingeniería 1.1/1.2
# de esa revisión): la tabla `scenarios` ya tiene datos reales de Gate 0 y `CREATE TABLE IF NOT
# EXISTS` es un no-op contra una tabla existente (TODO-20) — cualquier dato nuevo de video vive
# en una tabla propia (`scenario_videos`), nunca en una columna agregada a `scenarios`.
# ---------------------------------------------------------------------------


@dataclass
class VideoGroundTruthPoint:
    """Un hecho verificable dentro del video (ADR-0010) — no reusa `CriticalDataPoint` porque
    necesita un rango de tiempo visible y vive en un `ScenarioVideo`, no en un `Scenario`.
    `match_hints` es obligatorio en la práctica (ver ADR-0010, Negative) aunque no a nivel de
    tipo — el editor de escenarios de video debe exigirlo en la UI, no solo en el dataclass.
    """

    key: str
    label: str
    match_hints: list[str] = field(default_factory=list)
    visible_from_seconds: float = 0.0
    visible_to_seconds: float = 0.0
    required: bool = True


@dataclass
class ScenarioVideo:
    """El video adjunto a un `Scenario` (relación 1:1, PK = scenario_id — ver
    `SQLiteScenarioVideoStore`). `video_checksum` liga el ground truth a un archivo específico:
    si alguien reemplaza el archivo en `video_path` sin volver a autorar el ground truth, el
    checksum ya no coincide y `verify_checksum()` (adaptador) lo puede detectar en vez de fallar
    en silencio con timestamps desincronizados.
    """

    scenario_id: str
    video_path: str
    video_checksum: str
    duration_seconds: float
    content_type: str
    ground_truth_points: list[VideoGroundTruthPoint] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


@runtime_checkable
class ScenarioVideoPort(Protocol):
    def get(self, scenario_id: str) -> ScenarioVideo | None:
        ...

    def upsert(self, video: ScenarioVideo) -> None:
        ...

    def delete(self, scenario_id: str) -> None:
        ...


# ---------------------------------------------------------------------------
# Ubicación del incidente — docs/designs/ubicacion-del-incidente.md (autoplan 2026-08-21/22).
# Relación 1:1 con `Scenario` (PK = scenario_id), mismo patrón que `ScenarioVideo` — tabla propia
# (`SQLiteScenarioLocationStore`), nunca `ALTER TABLE scenarios` (TODO-20). A diferencia de
# `VideoGroundTruthPoint`, la ubicación NO introduce una entidad de ground-truth paralela para
# scoring: `core/scoring.py::_location_critical_points()` deriva `CriticalDataPoint`s planos
# (uno por campo de texto no vacío) a partir de este dataclass — reusa el mecanismo existente en
# vez de duplicar `key`/`label`/`match_hints` en una clase nueva (hallazgo de la voz independiente
# de ingeniería: una clase con los mismos 4 campos que `CriticalDataPoint` ya tiene es una clase de
# más). El mini-mapa (frontend) es el único lugar que interpreta `marker_x`/`marker_y` como
# geometría — el backend los persiste como floats opacos, sin significado espacial de este lado.
# ---------------------------------------------------------------------------


@dataclass
class ScenarioLocation:
    scenario_id: str
    street: str = ""
    cross_street: str = ""
    landmark: str = ""
    city_or_zone: str = ""
    # Narrativo — nunca entra a `match_hints`/scoring (ver Fase 2 Pass 7 decisión #3 del design
    # doc): texto libre sin match_hints es garantía de falsos negativos en `_matches_point`.
    additional_directions: str = ""
    # Sinónimos/frases alternativas extra, autor-editable, aplicados a los 3 campos de texto de
    # arriba en conjunto (no por campo — mantiene el shape simple; ver design doc Fase 3).
    match_hints: list[str] = field(default_factory=list)
    # `None` = "sin posicionar" — distingue "el autor no colocó el marcador" de "el marcador está
    # en el default 0.5/0.5" (hallazgo B10 del design doc: sin esto, la regla de "marcador sin
    # texto no cuenta como configurado" no es expresable).
    marker_x: float | None = None
    marker_y: float | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


@runtime_checkable
class ScenarioLocationPort(Protocol):
    def get(self, scenario_id: str) -> ScenarioLocation | None:
        ...

    def upsert(self, location: ScenarioLocation) -> None:
        ...

    def delete(self, scenario_id: str) -> None:
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
    # ADR-0011 (gate de rol mínimo para video de incidentes reales, TODO-16 acotado): default
    # "supervisor" preserva el comportamiento de cada token ya emitido antes de este campo —
    # nadie se vuelve manager por accidente. Solo `login()` con `MANAGER_PASSPHRASE` produce
    # `"manager"`.
    role: str = "supervisor"


@runtime_checkable
class SessionTokenPort(Protocol):
    def issue(self, supervisor_id: str, session_id: str, role: str = "supervisor") -> str:
        ...

    def verify(self, token: str) -> SessionTokenClaims:
        ...


# ---------------------------------------------------------------------------
# Auth de streaming de video — ver ADR-0009. Puerto separado de `SessionTokenPort` a propósito
# (no reusar `SessionTokenClaims`/`session_id` — un token de video no representa una sesión de
# llamada, representa acceso de corta duración a UN escenario específico): mismo tipo de
# conflación que ADR-0010/hallazgo 1.1 evita para `CriticalDataPoint` vs. `VideoGroundTruthPoint`.
# ---------------------------------------------------------------------------


class InvalidVideoTokenError(Exception):
    """Token de streaming de video ausente, corrupto, con firma inválida, expirado, o emitido
    para un `scenario_id` distinto del que se está pidiendo (ver `verify`).
    """


@dataclass(frozen=True)
class VideoTokenClaims:
    scenario_id: str
    supervisor_id: str
    issued_at: float


@runtime_checkable
class VideoTokenPort(Protocol):
    def issue(self, scenario_id: str, supervisor_id: str) -> str:
        ...

    def verify(self, token: str, scenario_id: str) -> VideoTokenClaims:
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
