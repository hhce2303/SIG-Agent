from audio.microphone import MicrophoneRecorder


recorder = MicrophoneRecorder()

recorder.record(
    duration=5,
    output_path="recording.wav",
)