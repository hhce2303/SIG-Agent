import sounddevice as sd
import soundfile as sf


class MicrophoneRecorder:

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        self.sample_rate = sample_rate
        self.channels = channels

    def record(
        self,
        output_path: str = "recording.wav",
    ) -> str:

        input("Press ENTER to start speaking...")

        print("🎤 Listening... Press ENTER when finished.")

        frames = []

        def callback(indata, frames_count, time, status):
            if status:
                print(status)

            frames.append(indata.copy())

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback,
        ):
            input()

        if not frames:
            raise RuntimeError("No audio was recorded.")

        audio = b"".join(
            frame.tobytes()
            for frame in frames
        )

        import numpy as np

        audio = np.frombuffer(
            audio,
            dtype=np.float32,
        )

        sf.write(
            output_path,
            audio,
            self.sample_rate,
        )

        print(f"💾 Audio saved to: {output_path}")

        return output_path