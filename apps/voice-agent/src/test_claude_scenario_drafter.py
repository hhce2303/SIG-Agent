"""Unit tests de `ClaudeScenarioDrafter`, con el cliente de Anthropic mockeado — mismo patrón
que `test_claude_dispatcher.py`/`test_metrics_judge.py`.
"""

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from anthropic import APIConnectionError, RateLimitError

from core.ports import IncidentOutcome, ScenarioDraftingError
from llm.claude_scenario_drafter import ClaudeScenarioDrafter

_VALID_JSON = """{
  "title": "Vehicle Theft \\u2014 Dealership Lot",
  "category": "Vehicle Theft",
  "difficulty": "Medium",
  "language": "English",
  "description": "A caller reports a stolen vehicle from the dealership lot.",
  "briefing": "A caller reports a stolen 2021 Toyota Camry from the dealership lot.",
  "critical_data_points": [
    {"key": "vehicle_description", "label": "Vehicle description", "match_hints": ["camry", "toyota"]}
  ],
  "missing_information": ["exact time of the theft was not in the notes"]
}"""


def _response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _fake_request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _incident(**overrides) -> IncidentOutcome:
    fields = dict(
        id="incident-1",
        occurred_at=100.0,
        supervisor_id="sup-1",
        category="Vehicle Theft",
        outcome_rating=3,
        critical_data_captured=False,
        protocol_followed=True,
        notes="Caller described a stolen 2021 Toyota Camry from the lot overnight.",
        reported_by="manager-1",
    )
    fields.update(overrides)
    return IncidentOutcome(**fields)


@pytest.fixture
def drafter():
    with patch("llm.claude_scenario_drafter.Anthropic"):
        return ClaudeScenarioDrafter(
            api_key="test-key",
            model="claude-test",
            max_retries=2,
            retry_delay_seconds=0,
        )


def test_draft_returns_parsed_content_on_success(drafter):
    drafter.client.messages.create.return_value = _response(_VALID_JSON)

    content = drafter.draft(_incident())

    assert content.title == "Vehicle Theft — Dealership Lot"
    assert content.difficulty == "Medium"
    assert content.critical_data_points[0].key == "vehicle_description"
    assert content.missing_information == ["exact time of the theft was not in the notes"]


def test_draft_sends_incident_notes_in_the_user_prompt(drafter):
    drafter.client.messages.create.return_value = _response(_VALID_JSON)

    drafter.draft(_incident(notes="A specific detail unique to this incident."))

    _, kwargs = drafter.client.messages.create.call_args
    user_prompt = kwargs["messages"][0]["content"]
    assert "A specific detail unique to this incident." in user_prompt


def test_draft_retries_on_transient_error_then_succeeds(drafter):
    drafter.client.messages.create.side_effect = [
        APIConnectionError(request=_fake_request()),
        _response(_VALID_JSON),
    ]

    content = drafter.draft(_incident())

    assert content.title == "Vehicle Theft — Dealership Lot"
    assert drafter.client.messages.create.call_count == 2


def test_draft_raises_scenario_drafting_error_after_exhausting_retries(drafter):
    drafter.client.messages.create.side_effect = RateLimitError(
        message="rate limited",
        response=httpx.Response(429, request=_fake_request()),
        body=None,
    )

    with pytest.raises(ScenarioDraftingError):
        drafter.draft(_incident())

    assert drafter.client.messages.create.call_count == 3


def test_draft_raises_scenario_drafting_error_on_malformed_json(drafter):
    drafter.client.messages.create.return_value = _response("not json")

    with pytest.raises(ScenarioDraftingError):
        drafter.draft(_incident())


def test_draft_raises_scenario_drafting_error_on_unexpected_difficulty(drafter):
    bad_json = _VALID_JSON.replace('"Medium"', '"Impossible"')
    drafter.client.messages.create.return_value = _response(bad_json)

    with pytest.raises(ScenarioDraftingError):
        drafter.draft(_incident())


def test_draft_prompt_instructs_not_inventing_real_identifiers(drafter):
    drafter.client.messages.create.return_value = _response(_VALID_JSON)

    drafter.draft(_incident())

    _, kwargs = drafter.client.messages.create.call_args
    system_prompt = kwargs["system"]
    assert "VIN" in system_prompt or "vehicle identifier" in system_prompt
    assert "missing_information" in system_prompt
