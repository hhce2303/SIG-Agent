from core.ports import DispatcherError, DispatcherPort, MicrophonePort, SpeechToTextPort, TextToSpeechPort

# Línea de recuperación en el propio diálogo cuando el adaptador de LLM se agota (NFR-02): el
# dispatcher simulado "no escuchó bien" en vez de que la llamada se cuelgue en silencio. Esto es
# la versión mínima del estado — el manejo completo (timeout configurable, UI de turno) es
# trabajo de Fase 1 todavía pendiente, ver docs/architecture/PHASE1-PROGRESS.md.
DISPATCHER_RECOVERY_LINE = "Sorry, can you repeat that? I didn't catch it."


class VoiceConversation:

    def __init__(
        self,
        dispatcher: DispatcherPort,
        stt: SpeechToTextPort,
        tts: TextToSpeechPort,
        microphone: MicrophonePort,
        scenario: str,
    ):
        self.dispatcher = dispatcher
        self.stt = stt
        self.tts = tts
        self.microphone = microphone
        self.scenario = scenario

        self.conversation = []

    def run_turn(self):

        # -------------------------
        # 1. Record
        # -------------------------

        audio_path = self.microphone.record()

        # -------------------------
        # 2. Speech → Text
        # -------------------------

        result = self.stt.transcribe(audio_path)
        text = result.text

        # T2/T12 (docs/designs/motor-de-metricas.md): `transcribe()` ahora devuelve
        # `TranscriptionResult` (dataclass), no un `str` — un dataclass no tiene `__bool__`/
        # `__len__`, así que `if not result:` sería siempre falso y esta rama nunca se
        # ejecutaría. Chequear explícitamente `.text` (hallazgo de la voz independiente de
        # ingeniería en la revisión de `/autoplan`, Fase 3 Sección 2).
        if not text:
            # Sin emoji a propósito (encontrado en una sesión de pruebas reales): la consola de
            # Windows en su codepage por default (cp1252) no puede codificar estos caracteres y
            # el `print` tumbaba el turno con UnicodeEncodeError — riesgo directo para NFR-03
            # (este CLI es el fallback manual si el servidor LAN cae, tiene que funcionar en
            # Windows sin configuración especial de consola).
            print("No speech detected.")
            return

        print(f"\nYou: {text}")

        self.conversation.append({
            "role": "user",
            "content": text,
        })

        # -------------------------
        # 3. Claude
        # -------------------------

        try:
            response = self.dispatcher.respond(
                conversation=self.conversation,
                scenario=self.scenario,
            )
        except DispatcherError as error:
            # NFR-02: un error de la API de Claude no puede tumbar el turno en silencio — se
            # recupera en el propio diálogo en vez de propagar la excepción.
            print(f"Dispatcher error: {error}")
            response = DISPATCHER_RECOVERY_LINE

        self.conversation.append({
            "role": "assistant",
            "content": response,
        })

        print(f"\nDispatcher: {response}")

        # -------------------------
        # 4. Text → Speech
        # -------------------------

        self.tts.speak(response)

    def run(self):

        print()
        print("========================================")
        print("       POLICE TRAINING SIMULATOR")
        print("========================================")
        print()
        print("Press Ctrl+C to exit.")
        print()

        while True:
            self.run_turn()