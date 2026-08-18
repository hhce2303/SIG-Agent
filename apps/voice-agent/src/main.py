import os

from dotenv import load_dotenv

from audio.microphone import MicrophoneRecorder
from core.conversation import VoiceConversation
from llm.claude import ClaudeDispatcher
from scenarios.vehicle_theft import SCENARIO
from stt.whisper import WhisperSTT
from tts.kokoro import KokoroTTS


load_dotenv()


dispatcher = ClaudeDispatcher(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    model=os.environ["CLAUDE_MODEL"],
)


stt = WhisperSTT(
    model_size="small",
    device="cpu",
    compute_type="int8",
)


tts = KokoroTTS(
    voice=os.getenv(
        "KOKORO_VOICE",
        "af_heart",
    )
)


microphone = MicrophoneRecorder()


conversation = VoiceConversation(
    dispatcher=dispatcher,
    stt=stt,
    tts=tts,
    microphone=microphone,
    scenario=SCENARIO,
)


conversation.run()