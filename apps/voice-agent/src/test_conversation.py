"""Test de integración de `VoiceConversation` contra stubs de puerto (NFR-10, NFR-02).

No usa mocks de bajo nivel de librerías externas — usa implementaciones falsas simples de cada
puerto (`core/ports.py`), que es lo que la propia arquitectura hexagonal (ADR-0006) existe para
permitir: el dominio no sabe ni le importa si el STT real es faster-whisper o un stub de test.

Incluye el test de caos que pide el roadmap de Fase 1: un error de Claude inyectado a mitad de
turno, verificando que el turno se recupera en el propio diálogo (NFR-02) en vez de tumbar el
proceso.
"""

from core.conversation import DISPATCHER_RECOVERY_LINE, VoiceConversation
from core.ports import DispatcherError, TranscriptionResult


class StubMicrophone:
    def record(self, output_path: str = "recording.wav") -> str:
        return output_path


class StubSTT:
    """T2/T12 (docs/designs/motor-de-metricas.md): devuelve `TranscriptionResult`, no un `str` —
    uno de los 2 stubs adicionales que la voz independiente de ingeniería encontró fuera de la
    lista original de archivos a migrar (el otro es `test_server_app.py::StubSTT`)."""

    def __init__(self, text: str = "A white Camry was stolen from the lot."):
        self.text = text

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        return TranscriptionResult(text=self.text, segments=[])


class StubTTS:
    def __init__(self):
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class StubDispatcher:
    """Stub de `DispatcherPort` — el "Claude stub" que pide el roadmap para el test de
    integración. `responses` puede mezclar strings (respuesta normal) y excepciones (para el
    test de caos, que inyecta un error de Claude a mitad de turno)."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls = 0

    def respond(self, conversation: list[dict[str, str]], scenario: str) -> str:
        self.calls += 1
        outcome = self._responses.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


def _conversation(dispatcher, stt=None, tts=None):
    return VoiceConversation(
        dispatcher=dispatcher,
        stt=stt or StubSTT(),
        tts=tts or StubTTS(),
        microphone=StubMicrophone(),
        scenario="A caller is reporting a stolen vehicle.",
    )


def test_run_turn_completes_full_loop_with_dispatcher_stub():
    tts = StubTTS()
    dispatcher = StubDispatcher(["911, what's your emergency?"])
    conversation = _conversation(dispatcher, tts=tts)

    conversation.run_turn()

    assert conversation.conversation == [
        {"role": "user", "content": "A white Camry was stolen from the lot."},
        {"role": "assistant", "content": "911, what's your emergency?"},
    ]
    assert tts.spoken == ["911, what's your emergency?"]
    assert dispatcher.calls == 1


def test_run_turn_skips_dispatcher_when_no_speech_detected():
    dispatcher = StubDispatcher(["should not be called"])
    conversation = _conversation(dispatcher, stt=StubSTT(text=""))

    conversation.run_turn()

    assert conversation.conversation == []
    assert dispatcher.calls == 0


def test_run_turn_recovers_when_claude_fails_mid_turn():
    """Test de caos (roadmap Fase 1 / NFR-10): error de Claude inyectado a mitad de turno."""

    tts = StubTTS()
    dispatcher = StubDispatcher([DispatcherError("simulated Claude outage mid-turn")])
    conversation = _conversation(dispatcher, tts=tts)

    conversation.run_turn()  # no debe propagar la excepción — NFR-02

    assert conversation.conversation == [
        {"role": "user", "content": "A white Camry was stolen from the lot."},
        {"role": "assistant", "content": DISPATCHER_RECOVERY_LINE},
    ]
    # La recuperación también se dice en voz alta — no es solo un log silencioso.
    assert tts.spoken == [DISPATCHER_RECOVERY_LINE]


def test_run_turn_recovers_then_continues_normally_on_next_turn():
    """Después de una recuperación, el siguiente turno vuelve a funcionar normal — el error no
    deja la conversación en un estado roto de forma permanente."""

    dispatcher = StubDispatcher(
        [
            DispatcherError("simulated Claude outage mid-turn"),
            "Got it — can you give me the license plate?",
        ]
    )
    conversation = _conversation(dispatcher)

    conversation.run_turn()
    conversation.run_turn()

    assert conversation.conversation[-1] == {
        "role": "assistant",
        "content": "Got it — can you give me the license plate?",
    }
    assert dispatcher.calls == 2
