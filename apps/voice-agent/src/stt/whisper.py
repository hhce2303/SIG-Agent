from faster_whisper import WhisperModel


class WhisperSTT:

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )

    def transcribe(self, audio_path: str) -> str:

        segments, info = self.model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500,
            },
            initial_prompt=(
                "This is a police emergency call. "
                "The caller may report stolen vehicles, "
                "vehicle descriptions, license plates, "
                "locations, times, names, and incidents. "
                "The conversation is in English."
            ),
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        )

        return text.strip()