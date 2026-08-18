from llm.claude import ClaudeDispatcher
from stt.whisper import WhisperSTT
from tts.kokoro import KokoroTTS
from audio.microphone import MicrophoneRecorder


class VoiceConversation:

    def __init__(
        self,
        dispatcher: ClaudeDispatcher,
        stt: WhisperSTT,
        tts: KokoroTTS,
        microphone: MicrophoneRecorder,
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

        text = self.stt.transcribe(audio_path)

        if not text:
            print("⚠️ No speech detected.")
            return

        print(f"\n📝 You: {text}")

        self.conversation.append({
            "role": "user",
            "content": text,
        })

        # -------------------------
        # 3. Claude
        # -------------------------

        response = self.dispatcher.respond(
            conversation=self.conversation,
            scenario=self.scenario,
        )

        self.conversation.append({
            "role": "assistant",
            "content": response,
        })

        print(f"\n🚓 Dispatcher: {response}")

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