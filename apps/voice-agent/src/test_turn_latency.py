"""Unit tests de `compute_response_latency` (T1, docs/designs/motor-de-metricas.md).

Dominio puro — `TurnTransition` se construye a mano con timestamps literales, igual que
`test_scoring.py`/`test_turn_state.py`.
"""

from core.turn_latency import compute_response_latency, rate_response_latency
from core.turn_state import TurnState, TurnTransition


def _transition(event: str, at: float, from_state=TurnState.LISTENING, to_state=TurnState.LISTENING) -> TurnTransition:
    return TurnTransition(from_state=from_state, to_state=to_state, event=event, at=at)


def test_no_history_returns_none():
    assert compute_response_latency([]) is None


def test_dispatcher_finished_without_a_following_response_yields_no_sample():
    # La llamada termina mientras el dispatcher todavía habla o justo después — no hay muestra,
    # nunca se inventa un 0.
    history = [_transition("dispatcher_finished_speaking", at=100.0)]

    assert compute_response_latency(history) is None


def test_single_turn_computes_the_gap_in_milliseconds():
    history = [
        _transition("dispatcher_finished_speaking", at=100.0),
        _transition("supervisor_started_speaking", at=101.5),
    ]

    result = compute_response_latency(history)

    assert result is not None
    assert result.average_ms == 1500
    assert result.sample_count == 1
    assert result.fastest_ms == result.slowest_ms == 1500
    assert result.clamped_negative_count == 0


def test_multiple_turns_average_and_track_fastest_slowest():
    history = [
        _transition("dispatcher_finished_speaking", at=0.0),
        _transition("supervisor_started_speaking", at=1.0),  # 1000ms
        _transition("dispatcher_finished_speaking", at=10.0),
        _transition("supervisor_started_speaking", at=13.0),  # 3000ms
    ]

    result = compute_response_latency(history)

    assert result.sample_count == 2
    assert result.fastest_ms == 1000
    assert result.slowest_ms == 3000
    assert result.average_ms == 2000


def test_negative_delta_clamps_to_zero_instead_of_raising():
    # Clock skew o un futuro barge-in — no debe explotar ni descartarse la muestra.
    history = [
        _transition("dispatcher_finished_speaking", at=100.0),
        _transition("supervisor_started_speaking", at=99.0),
    ]

    result = compute_response_latency(history)

    assert result.average_ms == 0
    assert result.clamped_negative_count == 1


def test_unrelated_transitions_are_ignored():
    history = [
        _transition("network_degraded", at=5.0),
        _transition("dispatcher_finished_speaking", at=10.0),
        _transition("pause_requested", at=11.0),
        _transition("supervisor_started_speaking", at=12.0),
    ]

    result = compute_response_latency(history)

    assert result.sample_count == 1
    assert result.average_ms == 2000


def test_rate_response_latency_returns_none_when_no_samples():
    assert rate_response_latency(None) is None


def test_rate_response_latency_good_band():
    history = [
        _transition("dispatcher_finished_speaking", at=0.0),
        _transition("supervisor_started_speaking", at=1.0),  # 1000ms
    ]
    tip = rate_response_latency(compute_response_latency(history))

    assert tip["rating"] == "good"
    assert tip["average_ms"] == 1000
    assert "1000ms" in tip["tip"]


def test_rate_response_latency_improve_band():
    history = [
        _transition("dispatcher_finished_speaking", at=0.0),
        _transition("supervisor_started_speaking", at=5.0),  # 5000ms
    ]
    tip = rate_response_latency(compute_response_latency(history))

    assert tip["rating"] == "improve"


def test_rate_response_latency_critical_band():
    history = [
        _transition("dispatcher_finished_speaking", at=0.0),
        _transition("supervisor_started_speaking", at=9.0),  # 9000ms
    ]
    tip = rate_response_latency(compute_response_latency(history))

    assert tip["rating"] == "critical"
