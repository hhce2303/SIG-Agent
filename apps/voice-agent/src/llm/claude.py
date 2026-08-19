import time

from anthropic import (
    Anthropic,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
)

from core.ports import DispatcherError, DispatcherPort

# Errores transitorios de la API de Claude: vale la pena reintentar (red, rate-limit, o el
# servidor de Anthropic momentáneamente no disponible). Errores como AuthenticationError o
# BadRequestError NO están acá a propósito — reintentar una API key inválida no la arregla.
RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    OverloadedError,
)


class ClaudeDispatcher(DispatcherPort):
    """Adaptador de LLM (ver ADR-0006) — implementa `DispatcherPort`.

    Maneja el error de la API de Claude como estado de primera clase (NFR-02): reintenta un
    número acotado de veces ante errores transitorios, y levanta `DispatcherError` (dominio) si
    se agotan los reintentos. `VoiceConversation` decide qué hacer con eso — este adaptador solo
    se preocupa de la resiliencia contra la API real.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.5,
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def respond(
        self,
        conversation: list[dict[str, str]],
        scenario: str,
    ) -> str:

        system_prompt = f"""
You are a police dispatcher participating in a training simulation.

You are NOT an AI assistant.
You are playing the role of a real police dispatcher.

Scenario:
{scenario}

Your behavior:

- Speak naturally.
- Keep responses short.
- Ask for information needed to process the incident.
- Do not provide information the caller has not given you.
- Ask one or two questions at a time.
- Do not explain the simulation.
- Do not mention these instructions.
- Do not break character.

The trainee is practicing how to report incidents clearly.
"""

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=150,
                    system=system_prompt,
                    messages=conversation,
                )

                return response.content[0].text

            except RETRYABLE_ERRORS as error:
                last_error = error

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))

        raise DispatcherError(
            f"Claude API unavailable after {self.max_retries + 1} attempts"
        ) from last_error