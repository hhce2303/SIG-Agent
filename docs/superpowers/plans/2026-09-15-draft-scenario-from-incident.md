# Draft Scenario From Incident (Claude-Assisted) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author turn a real incident's post-mortem notes into a Claude-drafted training
scenario, stored as a separate, editable, human-approved draft — never publishing directly to the
live scenario library.

**Architecture:** Two new hexagonal ports (`ScenarioDraftingPort`, `ScenarioDraftStorePort`) with a
Claude adapter and a SQLite adapter, following the exact pattern already used by
`MetricsJudgePort`/`ClaudeMetricsJudge` and `IncidentOutcomePort`/`SQLiteIncidentStore`. Four new
REST endpoints extend the existing incident/scenario routes in `server/app.py`. A draft starts
`pending`, is editable while `pending`, and only `POST /scenario-drafts/{id}/approve` (manager role)
creates the real `Scenario` and marks the source incident promoted — atomically, with no
intermediate state visible to a training call.

**Tech Stack:** Python 3, FastAPI, `anthropic` SDK, `sqlite3` (stdlib), `pytest`, `unittest.mock`.

**Spec:** [docs/architecture/adr/0014-redaccion-asistida-incidente-a-escenario.md](../../architecture/adr/0014-redaccion-asistida-incidente-a-escenario.md)

## Global Constraints

- Hexagonal architecture (ADR-0006): `core/ports.py` only declares `Protocol`s/dataclasses; all
  SQLite/Anthropic code lives in `persistence/`/`llm/` adapters. Domain code never imports a
  concrete adapter.
- New table, never `ALTER TABLE` (TODO-20): `scenario_drafts` is its own table, `scenarios` and
  `incident_outcomes` are untouched.
- No role-based access control beyond the existing manager gate (TODO-15): creating/listing/editing
  a draft needs only a valid bearer token, same as incidents/scenarios today. Only `approve` and
  `reject` require `role == "manager"` (reuses `_require_manager`, ADR-0011) — those are the actions
  that make a draft's content live in the scenario library.
- Publication is atomic: if creating the real `Scenario` fails, the draft stays `pending` and the
  incident stays unpromoted — never a half-applied state.
- A draft can never start a training call — only an approved `Scenario` (existing `ScenarioPort`)
  can. The scenario call-flow endpoints are untouched by this plan.
- Feature is optional and fails closed (matches `scenario_video_store`/`video_token_issuer` and
  `metrics_judge` in `create_app`): with `scenario_drafting`/`scenario_draft_store` unset, every new
  endpoint returns `503`, no `AttributeError`.
- `ScenarioDraft.critical_data_points` reuses the existing `CriticalDataPoint` dataclass — no
  parallel type (same reasoning as ADR-0010's rejection of a parallel ground-truth class).

---

### Task 1: Domain types + `ScenarioDraftStorePort` + SQLite adapter

**Files:**
- Modify: `apps/voice-agent/src/core/ports.py` (append at end of file)
- Create: `apps/voice-agent/src/persistence/sqlite_scenario_draft_store.py`
- Test: `apps/voice-agent/src/test_scenario_drafts.py`

**Interfaces:**
- Produces: `ScenarioDraft` (dataclass), `ScenarioDraftContent` (dataclass), `ScenarioDraftingError`
  (exception), `ScenarioDraftingPort.draft(incident: IncidentOutcome) -> ScenarioDraftContent`,
  `ScenarioDraftStorePort` with `create(draft) -> None`, `get(draft_id) -> ScenarioDraft | None`,
  `get_pending_for_incident(incident_id) -> ScenarioDraft | None`, `list() -> list[ScenarioDraft]`,
  `update(draft) -> None`, `mark_approved(draft_id, scenario_id) -> None`,
  `mark_rejected(draft_id) -> None`. `SQLiteScenarioDraftStore(db_path: str, clock=time.time)`
  implementing `ScenarioDraftStorePort`.

- [ ] **Step 1: Append the new domain types to `core/ports.py`**

Add at the end of `apps/voice-agent/src/core/ports.py`:

```python
# ---------------------------------------------------------------------------
# Borradores de escenario asistidos por Claude — ver ADR-0014. Extiende el lazo de
# retroalimentación de `IncidentOutcome` (arriba): en vez de crear un `Scenario` vacío de
# `critical_data_points` directamente, Claude propone un borrador completo que un humano revisa y
# aprueba antes de publicarlo. `ScenarioDraftContent` es la salida efímera del LLM (mismo rol que
# `MetricsJudgment` para `MetricsJudgePort` — no se guarda tal cual, se copia a `ScenarioDraft`
# antes de persistir). `ScenarioDraft` es el registro con estado de aprobación.
# ---------------------------------------------------------------------------


class ScenarioDraftingError(Exception):
    """El adaptador de LLM no pudo producir un borrador válido (timeout, rate-limit, JSON
    malformado, faltan keys esperadas, fallo de auth). El endpoint la captura y no crea ni
    modifica ningún borrador ni incidente — ver ADR-0014, "publicación atómica".
    """


@dataclass(frozen=True)
class ScenarioDraftContent:
    title: str
    category: str
    difficulty: str
    language: str
    description: str
    briefing: str
    critical_data_points: list[CriticalDataPoint]
    missing_information: list[str]
    raw_response: str


@runtime_checkable
class ScenarioDraftingPort(Protocol):
    def draft(self, incident: IncidentOutcome) -> ScenarioDraftContent:
        ...


@dataclass
class ScenarioDraft:
    """Borrador editable, nunca usable en una llamada de entrenamiento hasta que
    `status == "approved"` (ver `ScenarioDraftStorePort.mark_approved`, `server/app.py`)."""

    id: str
    incident_id: str
    status: str  # "pending" | "approved" | "rejected"
    title: str
    category: str
    difficulty: str
    language: str
    description: str
    briefing: str
    critical_data_points: list[CriticalDataPoint] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    raw_response: str = ""
    approved_scenario_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@runtime_checkable
class ScenarioDraftStorePort(Protocol):
    def create(self, draft: ScenarioDraft) -> None:
        ...

    def get(self, draft_id: str) -> ScenarioDraft | None:
        ...

    def get_pending_for_incident(self, incident_id: str) -> ScenarioDraft | None:
        ...

    def list(self) -> list[ScenarioDraft]:
        ...

    def update(self, draft: ScenarioDraft) -> None:
        ...

    def mark_approved(self, draft_id: str, scenario_id: str) -> None:
        ...

    def mark_rejected(self, draft_id: str) -> None:
        ...
```

`IncidentOutcome` is already defined earlier in the same file (no new import needed) — it is used
unquoted above because it is already defined above this point in the module.

- [ ] **Step 2: Write the failing test for the SQLite draft store**

Create `apps/voice-agent/src/test_scenario_drafts.py`:

```python
"""Unit tests de `SQLiteScenarioDraftStore` (ADR-0014) — mismo patrón que `test_incidents.py`:
SQLite real contra un archivo temporal, se prueba el contrato de `ScenarioDraftStorePort`.
"""

from core.ports import CriticalDataPoint, ScenarioDraft
from persistence.sqlite_scenario_draft_store import SQLiteScenarioDraftStore


def _draft(**overrides) -> ScenarioDraft:
    fields = dict(
        id="",
        incident_id="incident-1",
        status="pending",
        title="Vehicle Theft — Real Incident",
        category="Vehicle Theft",
        difficulty="Medium",
        language="English",
        description="Drafted from a real incident post-mortem.",
        briefing="A caller reports a stolen vehicle from the dealership lot.",
        critical_data_points=[
            CriticalDataPoint(key="vehicle_description", label="Vehicle description", match_hints=["camry"]),
        ],
        missing_information=["exact time of theft was not in the notes"],
    )
    fields.update(overrides)
    return ScenarioDraft(**fields)


def test_create_assigns_an_id_and_timestamps(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"), clock=lambda: 42.0)
    draft = _draft()

    store.create(draft)

    assert draft.id
    assert draft.created_at == 42.0
    assert draft.updated_at == 42.0


def test_get_returns_none_for_unknown_id(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    assert store.get("does-not-exist") is None


def test_get_round_trips_critical_data_points_and_missing_information(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft()
    store.create(draft)

    reloaded = store.get(draft.id)

    assert reloaded.critical_data_points == draft.critical_data_points
    assert reloaded.missing_information == draft.missing_information
    assert reloaded.status == "pending"


def test_get_pending_for_incident_ignores_non_pending_drafts(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft(incident_id="incident-9")
    store.create(draft)

    assert store.get_pending_for_incident("incident-9").id == draft.id

    store.mark_rejected(draft.id)

    assert store.get_pending_for_incident("incident-9") is None


def test_list_orders_newest_first(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    older = _draft(incident_id="incident-1")
    store.create(older)
    newer = _draft(incident_id="incident-2")
    store.create(newer)

    assert [d.id for d in store.list()] == [newer.id, older.id]


def test_update_persists_edited_fields(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"), clock=lambda: 99.0)
    draft = _draft()
    store.create(draft)

    draft.title = "Edited title"
    draft.critical_data_points = [
        CriticalDataPoint(key="location", label="Location", match_hints=["5th avenue"]),
    ]
    store.update(draft)

    reloaded = store.get(draft.id)
    assert reloaded.title == "Edited title"
    assert reloaded.critical_data_points[0].key == "location"
    assert reloaded.updated_at == 99.0


def test_mark_approved_sets_status_and_scenario_id(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft()
    store.create(draft)

    store.mark_approved(draft.id, "scenario-abc")

    reloaded = store.get(draft.id)
    assert reloaded.status == "approved"
    assert reloaded.approved_scenario_id == "scenario-abc"


def test_mark_rejected_sets_status(tmp_path):
    store = SQLiteScenarioDraftStore(str(tmp_path / "drafts.db"))
    draft = _draft()
    store.create(draft)

    store.mark_rejected(draft.id)

    assert store.get(draft.id).status == "rejected"
```

- [ ] **Step 3: Run the test to confirm it fails**

Run: `cd apps/voice-agent && pytest src/test_scenario_drafts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'persistence.sqlite_scenario_draft_store'`

- [ ] **Step 4: Implement `SQLiteScenarioDraftStore`**

Create `apps/voice-agent/src/persistence/sqlite_scenario_draft_store.py`:

```python
"""Adaptador de persistencia de borradores de escenario — ver ADR-0014.

Implementa `ScenarioDraftStorePort` (`core/ports.py`) contra el mismo motor SQLite embebido de
ADR-0007. Mismo patrón que `SQLiteIncidentStore`/`SQLiteScenarioStore`: una conexión por
operación, sin pool, sin capa de migraciones (no existe una todavía en este repo).
"""

import json
import sqlite3
import time
import uuid
from contextlib import closing

from core.ports import CriticalDataPoint, ScenarioDraft, ScenarioDraftStorePort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenario_drafts (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    language TEXT NOT NULL,
    description TEXT NOT NULL,
    briefing TEXT NOT NULL,
    critical_data_points_json TEXT NOT NULL,
    missing_information_json TEXT NOT NULL,
    raw_response TEXT NOT NULL DEFAULT '',
    approved_scenario_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""

_COLUMNS = (
    "id, incident_id, status, title, category, difficulty, language, description, briefing, "
    "critical_data_points_json, missing_information_json, raw_response, approved_scenario_id, "
    "created_at, updated_at"
)


class SQLiteScenarioDraftStore(ScenarioDraftStorePort):

    def __init__(self, db_path: str, clock=time.time):
        self.db_path = db_path
        self._clock = clock

        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def create(self, draft: ScenarioDraft) -> None:
        if not draft.id:
            draft.id = str(uuid.uuid4())
        now = self._clock()
        draft.created_at = draft.created_at or now
        draft.updated_at = now

        with closing(self._connect()) as conn:
            conn.execute(
                f"INSERT INTO scenario_drafts ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._to_row(draft),
            )
            conn.commit()

    def get(self, draft_id: str) -> ScenarioDraft | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM scenario_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def get_pending_for_incident(self, incident_id: str) -> ScenarioDraft | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM scenario_drafts "
                "WHERE incident_id = ? AND status = 'pending'",
                (incident_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[ScenarioDraft]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM scenario_drafts ORDER BY created_at DESC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(self, draft: ScenarioDraft) -> None:
        draft.updated_at = self._clock()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE scenario_drafts SET
                    status = ?, title = ?, category = ?, difficulty = ?, language = ?,
                    description = ?, briefing = ?, critical_data_points_json = ?,
                    missing_information_json = ?, approved_scenario_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    draft.status,
                    draft.title,
                    draft.category,
                    draft.difficulty,
                    draft.language,
                    draft.description,
                    draft.briefing,
                    json.dumps([p.__dict__ for p in draft.critical_data_points]),
                    json.dumps(draft.missing_information),
                    draft.approved_scenario_id,
                    draft.updated_at,
                    draft.id,
                ),
            )
            conn.commit()

    def mark_approved(self, draft_id: str, scenario_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE scenario_drafts SET status = 'approved', approved_scenario_id = ?, "
                "updated_at = ? WHERE id = ?",
                (scenario_id, self._clock(), draft_id),
            )
            conn.commit()

    def mark_rejected(self, draft_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE scenario_drafts SET status = 'rejected', updated_at = ? WHERE id = ?",
                (self._clock(), draft_id),
            )
            conn.commit()

    @staticmethod
    def _to_row(draft: ScenarioDraft) -> tuple:
        return (
            draft.id,
            draft.incident_id,
            draft.status,
            draft.title,
            draft.category,
            draft.difficulty,
            draft.language,
            draft.description,
            draft.briefing,
            json.dumps([p.__dict__ for p in draft.critical_data_points]),
            json.dumps(draft.missing_information),
            draft.raw_response,
            draft.approved_scenario_id,
            draft.created_at,
            draft.updated_at,
        )

    @staticmethod
    def _from_row(row) -> ScenarioDraft:
        return ScenarioDraft(
            id=row[0],
            incident_id=row[1],
            status=row[2],
            title=row[3],
            category=row[4],
            difficulty=row[5],
            language=row[6],
            description=row[7],
            briefing=row[8],
            critical_data_points=[CriticalDataPoint(**p) for p in json.loads(row[9])],
            missing_information=json.loads(row[10]),
            raw_response=row[11],
            approved_scenario_id=row[12],
            created_at=row[13],
            updated_at=row[14],
        )
```

- [ ] **Step 5: Run the test to confirm it passes**

Run: `cd apps/voice-agent && pytest src/test_scenario_drafts.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add apps/voice-agent/src/core/ports.py apps/voice-agent/src/persistence/sqlite_scenario_draft_store.py apps/voice-agent/src/test_scenario_drafts.py
git commit -m "feat: add ScenarioDraft domain type and SQLite draft store (ADR-0014)"
```

---

### Task 2: `ClaudeScenarioDrafter` adapter

**Files:**
- Create: `apps/voice-agent/src/llm/claude_scenario_drafter.py`
- Test: `apps/voice-agent/src/test_claude_scenario_drafter.py`

**Interfaces:**
- Consumes: `IncidentOutcome` (from Task 1's context, already in `core/ports.py`),
  `ScenarioDraftContent`, `ScenarioDraftingError`, `ScenarioDraftingPort` (Task 1).
- Produces: `ClaudeScenarioDrafter(api_key: str, model: str, max_retries: int = 2,
  retry_delay_seconds: float = 0.5)` implementing `ScenarioDraftingPort.draft(incident) ->
  ScenarioDraftContent`.

- [ ] **Step 1: Write the failing tests**

Create `apps/voice-agent/src/test_claude_scenario_drafter.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd apps/voice-agent && pytest src/test_claude_scenario_drafter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.claude_scenario_drafter'`

- [ ] **Step 3: Implement `ClaudeScenarioDrafter`**

Create `apps/voice-agent/src/llm/claude_scenario_drafter.py`:

```python
"""Adaptador de redacción de borradores de escenario — ver ADR-0014.

Implementa `ScenarioDraftingPort` (`core/ports.py`). Mismo cliente/patrón de reintentos que
`llm/claude.py::ClaudeDispatcher` y `llm/metrics_judge.py::ClaudeMetricsJudge` — reusa la misma
dependencia (`anthropic.Anthropic`), no una nueva.
"""

import json
import time

from anthropic import (
    Anthropic,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
)

from core.ports import (
    CriticalDataPoint,
    IncidentOutcome,
    ScenarioDraftContent,
    ScenarioDraftingError,
    ScenarioDraftingPort,
)

RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    OverloadedError,
)

_VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}

_SYSTEM_PROMPT = """You are helping a training-scenario author turn a real incident's post-mortem \
notes into a draft training scenario for a police-dispatch call simulator. You are NOT approving \
anything — a human reviewer will edit and approve or reject your draft before it is ever used in \
training.

You will receive the post-mortem notes of a real incident. Propose a training scenario based on \
those notes.

Rules:
- Only mark something as a confirmed fact if it is actually stated in the notes. Anything you add \
to make the scenario playable (additional dialogue, a plausible detail) is fictional training \
material, not a record of what really happened — never present it as verified fact.
- Never invent real police protocol, legal procedure, or a specific vehicle identifier (VIN or \
license plate) that was not in the notes.
- If the notes do not mention something a scenario normally needs (e.g. no location, no vehicle \
description), add a short description of that gap to "missing_information" instead of inventing a \
value for it.
- `critical_data_points` are the pieces of information a trainee must report during the call — \
each needs a short snake_case `key`, a human-readable `label`, and 2-5 `match_hints` (real \
phrases a trainee might actually say, not just the label reworded).

Respond with ONLY valid JSON, no other text, in exactly this shape:
{
  "title": "<short scenario title>",
  "category": "<incident category>",
  "difficulty": "Easy" | "Medium" | "Hard",
  "language": "English" | "Spanish",
  "description": "<one-sentence summary for the scenario library>",
  "briefing": "<the narrative a trainee reads before the call>",
  "critical_data_points": [
    {"key": "<snake_case_id>", "label": "<UI label>", "match_hints": ["<phrase>", "..."]}
  ],
  "missing_information": ["<short description of what the notes did not cover>"]
}"""


class ClaudeScenarioDrafter(ScenarioDraftingPort):

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

    def draft(self, incident: IncidentOutcome) -> ScenarioDraftContent:
        user_prompt = self._build_user_prompt(incident)

        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw_text = response.content[0].text
                return self._parse(raw_text)

            except RETRYABLE_ERRORS as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))

            except (json.JSONDecodeError, KeyError, ValueError) as error:
                # Malformado/incompleto no es transitorio de red — no vale la pena reintentar con
                # el mismo prompt (mismo criterio que `ClaudeMetricsJudge._parse`).
                raise ScenarioDraftingError(
                    f"Drafter returned an unparseable response: {error}"
                ) from error

        raise ScenarioDraftingError(
            f"Scenario drafter unavailable after {self.max_retries + 1} attempts"
        ) from last_error

    @staticmethod
    def _build_user_prompt(incident: IncidentOutcome) -> str:
        return f"""Incident category: {incident.category or "(not categorized)"}
Outcome rating (1-5, as logged by the reviewer): {incident.outcome_rating}
Critical data captured during the real call: {incident.critical_data_captured}
Protocol followed: {incident.protocol_followed}

Post-mortem notes:
{incident.notes or "(no post-mortem notes were recorded for this incident)"}
"""

    @staticmethod
    def _parse(raw_text: str) -> ScenarioDraftContent:
        payload = json.loads(raw_text)

        difficulty = payload["difficulty"]
        if difficulty not in _VALID_DIFFICULTIES:
            raise ValueError(f"unexpected difficulty value in drafter response: {payload!r}")

        return ScenarioDraftContent(
            title=payload["title"],
            category=payload["category"],
            difficulty=difficulty,
            language=payload["language"],
            description=payload["description"],
            briefing=payload["briefing"],
            critical_data_points=[
                CriticalDataPoint(
                    key=point["key"],
                    label=point["label"],
                    match_hints=point.get("match_hints", []),
                )
                for point in payload["critical_data_points"]
            ],
            missing_information=payload.get("missing_information", []),
            raw_response=raw_text,
        )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd apps/voice-agent && pytest src/test_claude_scenario_drafter.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/voice-agent/src/llm/claude_scenario_drafter.py apps/voice-agent/src/test_claude_scenario_drafter.py
git commit -m "feat: add ClaudeScenarioDrafter adapter (ADR-0014)"
```

---

### Task 3: `POST /incidents/{id}/draft-scenario` + list/get draft endpoints

**Files:**
- Modify: `apps/voice-agent/src/server/app.py`
- Test: `apps/voice-agent/src/test_server_app.py`

**Interfaces:**
- Consumes: `ScenarioDraft`, `ScenarioDraftingError`, `ScenarioDraftingPort`, `ScenarioDraftStorePort`
  (Task 1/2), existing `create_app(...)` factory, existing `IncidentOutcomePort`/`incident_store`,
  existing `_bearer_claims` dependency.
- Produces: `create_app(..., scenario_draft_store: ScenarioDraftStorePort | None = None,
  scenario_drafting: ScenarioDraftingPort | None = None)`; routes
  `POST /incidents/{incident_id}/draft-scenario`, `GET /scenario-drafts`,
  `GET /scenario-drafts/{draft_id}`; Pydantic model `ScenarioDraftOut`; helper `_draft_out(draft)
  -> ScenarioDraftOut` and `_require_scenario_drafting_feature() -> None` (both module/closure-level
  in `server/app.py`, reused by Task 4).

- [ ] **Step 1: Write the failing tests**

Add to `apps/voice-agent/src/test_server_app.py`, right after
`test_promote_incident_creates_a_draft_scenario_from_the_post_mortem` (after line 657 in the
current file):

```python
class StubScenarioDrafter:
    """Stub de `ScenarioDraftingPort` — ADR-0014. `error` inyecta una `ScenarioDraftingError`
    para probar que un fallo de Claude no deja ningún borrador ni incidente a medio modificar."""

    def __init__(self, content=None, error: Exception | None = None):
        self._content = content
        self._error = error
        self.calls = 0

    def draft(self, incident):
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._content is not None:
            return self._content

        from core.ports import CriticalDataPoint, ScenarioDraftContent
        return ScenarioDraftContent(
            title="Vehicle Theft — Dealership Lot",
            category="Vehicle Theft",
            difficulty="Medium",
            language="English",
            description="A caller reports a stolen vehicle from the dealership lot.",
            briefing="A caller reports a stolen 2021 Toyota Camry.",
            critical_data_points=[
                CriticalDataPoint(key="vehicle_description", label="Vehicle description", match_hints=["camry"]),
            ],
            missing_information=["exact time of the theft was not in the notes"],
            raw_response="{}",
        )


def _make_client_with_drafting(app_components, scenario_drafting, tmp_path):
    from persistence.sqlite_scenario_draft_store import SQLiteScenarioDraftStore

    token_issuer, session_store, scenario_store, settings_store, incident_store = app_components
    app = create_app(
        token_issuer=token_issuer,
        session_store=session_store,
        scenario_store=scenario_store,
        settings_store=settings_store,
        incident_store=incident_store,
        supervisor_passphrase=PASSPHRASE,
        dispatcher=StubDispatcher(["911, what is your emergency?"]),
        stt=StubSTT([""]),
        tts=StubTTS(),
        microphone=StubMicrophone(),
        clock=make_clock(),
        # NUNCA `SQLiteScenarioDraftStore(":memory:")`: el adaptador abre una conexión nueva por
        # operación (mismo patrón que el resto de `persistence/`), y cada `sqlite3.connect(":memory:")`
        # abre una base en blanco distinta — perdería todo lo escrito entre un `create()` y el
        # siguiente `get()`. Un archivo real en `tmp_path` persiste entre conexiones.
        scenario_draft_store=SQLiteScenarioDraftStore(str(tmp_path / "scenario_drafts.db")),
        scenario_drafting=scenario_drafting,
    )
    return TestClient(app)


def test_draft_scenario_endpoint_is_503_when_not_configured(client):
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post("/incidents", json=_incident_payload(), headers=headers).json()["id"]

    response = client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers)
    assert response.status_code == 503


def test_draft_scenario_creates_a_pending_draft(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post(
        "/incidents", json=_incident_payload(notes="Caller described a stolen Camry."), headers=headers
    ).json()["id"]

    response = client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers)
    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "pending"
    assert draft["incident_id"] == incident_id
    assert draft["critical_data_points"][0]["key"] == "vehicle_description"
    assert draft["missing_information"] == ["exact time of the theft was not in the notes"]

    # el incidente NO queda promovido solo por pedir un borrador — recién al aprobarlo (Task 4).
    incident = client.get("/incidents", headers=headers).json()[0]
    assert incident["promoted_scenario_id"] == ""


def test_draft_scenario_rejects_a_second_pending_draft_for_the_same_incident(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post("/incidents", json=_incident_payload(), headers=headers).json()["id"]
    client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers)

    again = client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers)
    assert again.status_code == 409


def test_draft_scenario_leaves_nothing_changed_when_claude_fails(app_components, tmp_path):
    from core.ports import ScenarioDraftingError

    client = _make_client_with_drafting(
        app_components, StubScenarioDrafter(error=ScenarioDraftingError("boom")), tmp_path
    )
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post("/incidents", json=_incident_payload(), headers=headers).json()["id"]

    response = client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers)
    assert response.status_code == 502

    drafts = client.get("/scenario-drafts", headers=headers).json()
    assert drafts == []
    incident = client.get("/incidents", headers=headers).json()[0]
    assert incident["promoted_scenario_id"] == ""


def test_get_scenario_draft_returns_404_for_unknown_id(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/scenario-drafts/does-not-exist", headers=headers)
    assert response.status_code == 404
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd apps/voice-agent && pytest src/test_server_app.py -k draft_scenario -v`
Expected: FAIL — `create_app() got an unexpected keyword argument 'scenario_draft_store'`

- [ ] **Step 3: Add the import and Pydantic model**

In `apps/voice-agent/src/server/app.py`, modify the `from core.ports import (...)` block
(currently lines 33-60) to add the four new names, keeping the existing alphabetical-ish grouping:

```python
from core.ports import (
    CriticalDataPoint,
    DispatcherError,
    DispatcherPort,
    IncidentOutcome,
    IncidentOutcomePort,
    InvalidSessionTokenError,
    InvalidVideoTokenError,
    MetricsJudgeError,
    MetricsJudgePort,
    MicrophonePort,
    PersistencePort,
    Scenario,
    ScenarioDraft,
    ScenarioDraftingError,
    ScenarioDraftingPort,
    ScenarioDraftStorePort,
    ScenarioLocation,
    ScenarioLocationPort,
    ScenarioPort,
    ScenarioVideo,
    ScenarioVideoPort,
    SessionRecord,
    SessionTokenClaims,
    SessionTokenPort,
    SettingsPort,
    SpeechToTextPort,
    SttMetricsPort,
    TextToSpeechPort,
    VideoGroundTruthPoint,
    VideoTokenPort,
)
```

Add this new Pydantic model right after `class IncidentOut(IncidentIn):` (after line 269, before
`class GroupStatsModel(BaseModel):`):

```python
class ScenarioDraftOut(BaseModel):
    id: str
    incident_id: str
    status: str
    title: str
    category: str
    difficulty: str
    language: str
    description: str
    briefing: str
    critical_data_points: list[CriticalDataPointModel]
    missing_information: list[str]
    approved_scenario_id: str
    created_at: float
    updated_at: float
```

- [ ] **Step 4: Add the two new `create_app` parameters**

In `apps/voice-agent/src/server/app.py`, modify the `create_app(...)` signature (around line
287-315) to add two new optional parameters at the end, right after `scenario_location_store`:

```python
    scenario_location_store: ScenarioLocationPort | None = None,
    # ADR-0014: idem — sin configurar, `POST /incidents/{id}/draft-scenario` y las rutas de
    # `/scenario-drafts` responden 503, cero cambio de comportamiento para instalaciones que no
    # configuran redacción asistida.
    scenario_draft_store: ScenarioDraftStorePort | None = None,
    scenario_drafting: ScenarioDraftingPort | None = None,
) -> FastAPI:
```

(This replaces the current `scenario_location_store: ScenarioLocationPort | None = None,\n) -> FastAPI:` two-line ending of the signature.)

- [ ] **Step 5: Add the feature-gate helper and the three endpoints**

In `apps/voice-agent/src/server/app.py`, right after the `promote_incident_to_scenario` function
body ends (after the `return _scenario_out(...)` line that currently ends at line 863, before
`@app.get("/impact-report", ...)`), add:

```python
    # -----------------------------------------------------------------
    # Borradores de escenario asistidos por Claude — ver ADR-0014. Un borrador nunca es un
    # `Scenario` real (no puede iniciar una llamada de entrenamiento) hasta que se aprueba
    # explícitamente — ver `approve_scenario_draft`/`reject_scenario_draft` (Task 4).
    # -----------------------------------------------------------------

    def _require_scenario_drafting_feature() -> None:
        if scenario_draft_store is None or scenario_drafting is None:
            raise HTTPException(status_code=503, detail="scenario drafting is not configured on this server")

    def _draft_out(draft: ScenarioDraft) -> ScenarioDraftOut:
        return ScenarioDraftOut(
            id=draft.id,
            incident_id=draft.incident_id,
            status=draft.status,
            title=draft.title,
            category=draft.category,
            difficulty=draft.difficulty,
            language=draft.language,
            description=draft.description,
            briefing=draft.briefing,
            critical_data_points=[
                CriticalDataPointModel(key=p.key, label=p.label, required=p.required, match_hints=p.match_hints)
                for p in draft.critical_data_points
            ],
            missing_information=draft.missing_information,
            approved_scenario_id=draft.approved_scenario_id,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )

    @app.post("/incidents/{incident_id}/draft-scenario", response_model=ScenarioDraftOut, status_code=201)
    def draft_scenario_from_incident(incident_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        """Pide a Claude un borrador completo a partir de las notas de un incidente — ADR-0014.
        A diferencia de `promote_incident_to_scenario`, esto NO crea un `Scenario` ni marca el
        incidente como promovido: eso solo pasa al aprobar el borrador (Task 4)."""

        _require_scenario_drafting_feature()

        incident = incident_store.get(incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        if incident.promoted_scenario_id:
            raise HTTPException(status_code=409, detail="incident was already promoted to a scenario")
        if scenario_draft_store.get_pending_for_incident(incident_id) is not None:
            raise HTTPException(status_code=409, detail="incident already has a pending draft")

        try:
            content = scenario_drafting.draft(incident)
        except ScenarioDraftingError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

        draft = ScenarioDraft(
            id="",
            incident_id=incident_id,
            status="pending",
            title=content.title,
            category=content.category,
            difficulty=content.difficulty,
            language=content.language,
            description=content.description,
            briefing=content.briefing,
            critical_data_points=content.critical_data_points,
            missing_information=content.missing_information,
            raw_response=content.raw_response,
        )
        scenario_draft_store.create(draft)

        log_event(
            logger, "scenario_draft_created", supervisor_id=claims.supervisor_id,
            incident_id=incident_id, draft_id=draft.id,
        )
        return _draft_out(draft)

    @app.get("/scenario-drafts", response_model=list[ScenarioDraftOut])
    def list_scenario_drafts(claims: SessionTokenClaims = Depends(_bearer_claims)):
        _require_scenario_drafting_feature()
        return [_draft_out(draft) for draft in scenario_draft_store.list()]

    @app.get("/scenario-drafts/{draft_id}", response_model=ScenarioDraftOut)
    def get_scenario_draft(draft_id: str, claims: SessionTokenClaims = Depends(_bearer_claims)):
        _require_scenario_drafting_feature()
        draft = scenario_draft_store.get(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="scenario draft not found")
        return _draft_out(draft)

```

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `cd apps/voice-agent && pytest src/test_server_app.py -v`
Expected: PASS (all existing tests still pass, plus the 5 new ones from Step 1)

- [ ] **Step 7: Commit**

```bash
git add apps/voice-agent/src/server/app.py apps/voice-agent/src/test_server_app.py
git commit -m "feat: add POST /incidents/{id}/draft-scenario and GET /scenario-drafts endpoints (ADR-0014)"
```

---

### Task 4: Edit, approve, and reject a scenario draft

**Files:**
- Modify: `apps/voice-agent/src/server/app.py`
- Test: `apps/voice-agent/src/test_server_app.py`

**Interfaces:**
- Consumes: everything from Task 3 (`ScenarioDraftOut`, `_draft_out`,
  `_require_scenario_drafting_feature`, `scenario_draft_store`, `scenario_store`, `incident_store`,
  existing `_require_manager` dependency, existing `_scenario_out` helper).
- Produces: routes `PUT /scenario-drafts/{draft_id}`, `POST /scenario-drafts/{draft_id}/approve`,
  `POST /scenario-drafts/{draft_id}/reject`; Pydantic model `ScenarioDraftPatchIn`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/voice-agent/src/test_server_app.py`, right after the tests added in Task 3:

```python
def _draft_patch_payload(**overrides):
    payload = {
        "title": "Edited Vehicle Theft",
        "category": "Vehicle Theft",
        "difficulty": "Hard",
        "language": "English",
        "description": "A caller reports a stolen vehicle from the dealership lot.",
        "briefing": "A caller reports a stolen 2021 Toyota Camry, edited by a reviewer.",
        "critical_data_points": [
            {"key": "vehicle_description", "label": "Vehicle description", "match_hints": ["camry", "toyota"]},
        ],
    }
    payload.update(overrides)
    return payload


def test_update_pending_draft_persists_edits(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post("/incidents", json=_incident_payload(), headers=headers).json()["id"]
    draft_id = client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers).json()["id"]

    response = client.put(f"/scenario-drafts/{draft_id}", json=_draft_patch_payload(), headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Edited Vehicle Theft"
    assert response.json()["difficulty"] == "Hard"


def test_approve_scenario_draft_requires_manager_role(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    token = _login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    incident_id = client.post("/incidents", json=_incident_payload(), headers=headers).json()["id"]
    draft_id = client.post(f"/incidents/{incident_id}/draft-scenario", headers=headers).json()["id"]

    response = client.post(f"/scenario-drafts/{draft_id}/approve", headers=headers)
    assert response.status_code == 403


def test_approve_scenario_draft_creates_scenario_and_promotes_incident(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    supervisor_token = _login(client).json()["token"]
    supervisor_headers = {"Authorization": f"Bearer {supervisor_token}"}

    incident_id = client.post(
        "/incidents", json=_incident_payload(), headers=supervisor_headers
    ).json()["id"]
    draft_id = client.post(
        f"/incidents/{incident_id}/draft-scenario", headers=supervisor_headers
    ).json()["id"]

    manager_token = _login(client, supervisor_id="mgr-1", passphrase=MANAGER_PASSPHRASE).json()["token"]
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    approved = client.post(f"/scenario-drafts/{draft_id}/approve", headers=manager_headers)
    assert approved.status_code == 201
    scenario = approved.json()
    assert scenario["title"] == "Vehicle Theft — Dealership Lot"
    assert scenario["critical_data_points"][0]["key"] == "vehicle_description"

    draft = client.get(f"/scenario-drafts/{draft_id}", headers=supervisor_headers).json()
    assert draft["status"] == "approved"
    assert draft["approved_scenario_id"] == scenario["id"]

    incident = client.get("/incidents", headers=supervisor_headers).json()[0]
    assert incident["promoted_scenario_id"] == scenario["id"]

    # aprobar un borrador ya aprobado sería un duplicado silencioso en la librería de escenarios.
    again = client.post(f"/scenario-drafts/{draft_id}/approve", headers=manager_headers)
    assert again.status_code == 409


def test_reject_scenario_draft_leaves_incident_unpromoted(app_components, tmp_path):
    client = _make_client_with_drafting(app_components, StubScenarioDrafter(), tmp_path)
    supervisor_token = _login(client).json()["token"]
    supervisor_headers = {"Authorization": f"Bearer {supervisor_token}"}

    incident_id = client.post("/incidents", json=_incident_payload(), headers=supervisor_headers).json()["id"]
    draft_id = client.post(
        f"/incidents/{incident_id}/draft-scenario", headers=supervisor_headers
    ).json()["id"]

    manager_token = _login(client, supervisor_id="mgr-1", passphrase=MANAGER_PASSPHRASE).json()["token"]
    manager_headers = {"Authorization": f"Bearer {manager_token}"}

    rejected = client.post(f"/scenario-drafts/{draft_id}/reject", headers=manager_headers)
    assert rejected.status_code == 204

    draft = client.get(f"/scenario-drafts/{draft_id}", headers=supervisor_headers).json()
    assert draft["status"] == "rejected"

    incident = client.get("/incidents", headers=supervisor_headers).json()[0]
    assert incident["promoted_scenario_id"] == ""

    # un incidente con un borrador rechazado puede pedir un borrador nuevo.
    retried = client.post(f"/incidents/{incident_id}/draft-scenario", headers=supervisor_headers)
    assert retried.status_code == 201
```

This test file needs `MANAGER_PASSPHRASE` and `_make_client_with_drafting` to pass
`manager_passphrase` through. Update `_make_client_with_drafting` (added in Task 3) to accept and
forward it:

```python
MANAGER_PASSPHRASE = "manager-passphrase"


def _make_client_with_drafting(app_components, scenario_drafting, tmp_path):
    from persistence.sqlite_scenario_draft_store import SQLiteScenarioDraftStore

    token_issuer, session_store, scenario_store, settings_store, incident_store = app_components
    app = create_app(
        token_issuer=token_issuer,
        session_store=session_store,
        scenario_store=scenario_store,
        settings_store=settings_store,
        incident_store=incident_store,
        supervisor_passphrase=PASSPHRASE,
        manager_passphrase=MANAGER_PASSPHRASE,
        dispatcher=StubDispatcher(["911, what is your emergency?"]),
        stt=StubSTT([""]),
        tts=StubTTS(),
        microphone=StubMicrophone(),
        clock=make_clock(),
        # Ver el comentario de Task 3 sobre por qué nunca `":memory:"` acá.
        scenario_draft_store=SQLiteScenarioDraftStore(str(tmp_path / "scenario_drafts.db")),
        scenario_drafting=scenario_drafting,
    )
    return TestClient(app)
```

(This replaces the version of `_make_client_with_drafting` written in Task 3, Step 1 — same
function, now with `manager_passphrase` and `tmp_path` added.)

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `cd apps/voice-agent && pytest src/test_server_app.py -k "draft" -v`
Expected: FAIL with 404/405 on `PUT /scenario-drafts/{id}` and the `/approve`/`/reject` routes
(routes do not exist yet)

- [ ] **Step 3: Add `ScenarioDraftPatchIn` and the three endpoints**

In `apps/voice-agent/src/server/app.py`, add this Pydantic model right after `ScenarioDraftOut`
(added in Task 3, Step 3):

```python
class ScenarioDraftPatchIn(BaseModel):
    title: str
    category: str
    difficulty: str
    language: str = "English"
    description: str
    briefing: str
    critical_data_points: list[CriticalDataPointModel] = Field(default_factory=list)
```

Add these three endpoints right after `get_scenario_draft` (added in Task 3, Step 5), still before
`@app.get("/impact-report", ...)`:

```python
    @app.put("/scenario-drafts/{draft_id}", response_model=ScenarioDraftOut)
    def update_scenario_draft(
        draft_id: str, body: ScenarioDraftPatchIn, claims: SessionTokenClaims = Depends(_bearer_claims)
    ):
        _require_scenario_drafting_feature()
        draft = scenario_draft_store.get(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="scenario draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail=f"draft is already {draft.status}, cannot edit")

        draft.title = body.title
        draft.category = body.category
        draft.difficulty = body.difficulty
        draft.language = body.language
        draft.description = body.description
        draft.briefing = body.briefing
        draft.critical_data_points = [
            CriticalDataPoint(key=p.key, label=p.label, required=p.required, match_hints=p.match_hints)
            for p in body.critical_data_points
        ]
        scenario_draft_store.update(draft)

        log_event(logger, "scenario_draft_edited", supervisor_id=claims.supervisor_id, draft_id=draft_id)
        return _draft_out(draft)

    @app.post("/scenario-drafts/{draft_id}/approve", response_model=ScenarioOut, status_code=201)
    def approve_scenario_draft(draft_id: str, claims: SessionTokenClaims = Depends(_require_manager)):
        """Publicación atómica (ADR-0014): crea el `Scenario` real, marca el borrador `approved`
        y el incidente promovido, en ese orden — si `scenario_store.create` falla, ni el borrador
        ni el incidente cambian de estado."""

        _require_scenario_drafting_feature()
        draft = scenario_draft_store.get(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="scenario draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail=f"draft is already {draft.status}")

        scenario = Scenario(
            id="",
            title=draft.title,
            category=draft.category,
            difficulty=draft.difficulty,
            language=draft.language,
            description=draft.description,
            briefing=draft.briefing,
            critical_data_points=draft.critical_data_points,
        )
        scenario_store.create(scenario)
        scenario_draft_store.mark_approved(draft.id, scenario.id)
        incident_store.mark_promoted(draft.incident_id, scenario.id)

        log_event(
            logger, "scenario_draft_approved", supervisor_id=claims.supervisor_id,
            draft_id=draft.id, scenario_id=scenario.id,
        )
        return _scenario_out(scenario, scenario_video_store, scenario_location_store)

    @app.post("/scenario-drafts/{draft_id}/reject", status_code=204)
    def reject_scenario_draft(draft_id: str, claims: SessionTokenClaims = Depends(_require_manager)):
        _require_scenario_drafting_feature()
        draft = scenario_draft_store.get(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="scenario draft not found")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail=f"draft is already {draft.status}")

        scenario_draft_store.mark_rejected(draft.id)
        log_event(logger, "scenario_draft_rejected", supervisor_id=claims.supervisor_id, draft_id=draft.id)

```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd apps/voice-agent && pytest src/test_server_app.py -v`
Expected: PASS (all tests, including every test added in Task 3 and Task 4)

- [ ] **Step 5: Commit**

```bash
git add apps/voice-agent/src/server/app.py apps/voice-agent/src/test_server_app.py
git commit -m "feat: add scenario draft edit/approve/reject endpoints (ADR-0014)"
```

---

### Task 5: Wire `ClaudeScenarioDrafter`/`SQLiteScenarioDraftStore` into `server_main.py`

**Files:**
- Modify: `apps/voice-agent/src/server_main.py`
- Modify: `apps/voice-agent/backend.env.example`

**Interfaces:**
- Consumes: `SQLiteScenarioDraftStore` (Task 1), `ClaudeScenarioDrafter` (Task 2),
  `create_app(..., scenario_draft_store=..., scenario_drafting=...)` (Task 3).
- Produces: nothing new — this task only wires existing pieces into the real entry point.

- [ ] **Step 1: Add the imports**

In `apps/voice-agent/src/server_main.py`, modify the import block (around lines 59-62) to add:

```python
from llm.claude import ClaudeDispatcher
from llm.claude_scenario_drafter import ClaudeScenarioDrafter
from llm.metrics_judge import ClaudeMetricsJudge
from persistence.sqlite_incident_store import SQLiteIncidentStore
from persistence.sqlite_scenario_draft_store import SQLiteScenarioDraftStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore
```

(Only the two new lines — `from llm.claude_scenario_drafter import ClaudeScenarioDrafter` and
`from persistence.sqlite_scenario_draft_store import SQLiteScenarioDraftStore` — are additions;
keep the existing four lines in their current alphabetical position.)

- [ ] **Step 2: Wire the new store and adapter into `build_app`**

In `apps/voice-agent/src/server_main.py`, modify the `create_app(...)` call inside `build_app()`
(around lines 161-211) to add two new keyword arguments right after `scenario_location_store`:

```python
        scenario_location_store=SQLiteScenarioLocationStore(sessions_db_path),
        # ADR-0014: mismo patrón opt-out que `METRICS_JUDGE_ENABLED` — `SCENARIO_DRAFTING_ENABLED=0`
        # apaga la redacción asistida sin afectar el resto del servidor. Reusa las mismas
        # credenciales que ya usan `ClaudeDispatcher`/`ClaudeMetricsJudge`.
        scenario_draft_store=SQLiteScenarioDraftStore(sessions_db_path),
        scenario_drafting=(
            ClaudeScenarioDrafter(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                model=os.environ["CLAUDE_MODEL"],
            )
            if os.getenv("SCENARIO_DRAFTING_ENABLED", "1") == "1"
            else None
        ),
    )
```

(This replaces the current `scenario_location_store=SQLiteScenarioLocationStore(sessions_db_path),\n    )` two-line ending of the `create_app(...)` call.)

- [ ] **Step 3: Document the new environment variable**

In `apps/voice-agent/src/server_main.py`, add to the module docstring's "Opcionales" list
(right after the existing `METRICS_JUDGE_ENABLED` bullet):

```
- `SCENARIO_DRAFTING_ENABLED` (default `1`) — redacción de borradores de escenario asistida por
  Claude a partir de incidentes reales (ADR-0014): `0` apaga `POST /incidents/{id}/draft-scenario`
  y las rutas de `/scenario-drafts` (503) sin afectar el resto del servidor. Reusa
  `ANTHROPIC_API_KEY`/`CLAUDE_MODEL`, las mismas credenciales que ya usan `ClaudeDispatcher` y
  `ClaudeMetricsJudge`.
```

In `apps/voice-agent/backend.env.example`, add right after the existing `METRICS_JUDGE_ENABLED=1`
line:

```
SCENARIO_DRAFTING_ENABLED=1
```

- [ ] **Step 4: Run the full backend test suite to confirm nothing broke**

Run: `cd apps/voice-agent && pytest src -v`
Expected: PASS — every existing test plus every test added in Tasks 1-4. This exercises
`server_main.py`'s module-level `build_app()` indirectly through `test_server_main.py`'s import
(see that file's docstring), confirming the new wiring does not break app construction.

- [ ] **Step 5: Commit**

```bash
git add apps/voice-agent/src/server_main.py apps/voice-agent/backend.env.example
git commit -m "feat: wire ClaudeScenarioDrafter and SQLiteScenarioDraftStore into server_main (ADR-0014)"
```

---

## Out of scope (follow-ups, not part of this plan)

- **Frontend review/approve UI.** There is no dedicated Incidents page in `frontend/src/pages`
  yet — incident CRUD is only wired at the API-client level (`frontend/src/lib/api.ts`). Building
  a draft-review screen is a separate, UI-focused plan once this backend capability is validated.
- **RAG/semantic memory, aggregate analytics, prompt caching** (ADR-0014 options 1/3/4) — each is
  its own follow-up, gated on this flow producing enough reviewed scenarios/evidence first.
- **Cross-installation aggregation** (ADR-0014 option 5) — explicitly deferred in the ADR.
