from stt.whisper import WhisperSTT


stt = WhisperSTT(
    model_size="small",
    device="cpu",
    compute_type="int8",
)


text = stt.transcribe("recording.wav")

print()
print("📝 Transcription:")
print(text)