from anthropic import Anthropic


class ClaudeDispatcher:
    def __init__(self, api_key: str, model: str):
        self.client = Anthropic(api_key=api_key)
        self.model = model

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

        response = self.client.messages.create(
            model=self.model,
            max_tokens=150,
            system=system_prompt,
            messages=conversation,
        )

        return response.content[0].text