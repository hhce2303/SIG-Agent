"""Unit tests de `TurnStateMachine` (roadmap Fase 1 — state machine de turnos explícito)."""

import pytest

from core.turn_state import InvalidTurnTransitionError, TurnState, TurnStateMachine


def make_clock():
    ticks = iter(range(1, 1000))
    return lambda: next(ticks)


def test_happy_path_full_turn_cycle():
    machine = TurnStateMachine(clock=make_clock())

    assert machine.state is TurnState.LISTENING

    machine.handle("supervisor_started_speaking")
    assert machine.state is TurnState.SUPERVISOR_SPEAKING

    machine.handle("supervisor_stopped_speaking")
    assert machine.state is TurnState.PROCESSING

    machine.handle("dispatcher_response_ready")
    assert machine.state is TurnState.DISPATCHER_SPEAKING

    machine.handle("dispatcher_finished_speaking")
    assert machine.state is TurnState.LISTENING

    assert [t.event for t in machine.history] == [
        "supervisor_started_speaking",
        "supervisor_stopped_speaking",
        "dispatcher_response_ready",
        "dispatcher_finished_speaking",
    ]
    # El reloj inyectado (server-side) es la única fuente de los timestamps — NFR-08.
    assert [t.at for t in machine.history] == [1, 2, 3, 4]


def test_processing_timeout_falls_back_to_dispatcher_speaking():
    machine = TurnStateMachine(clock=make_clock())
    machine.handle("supervisor_started_speaking")
    machine.handle("supervisor_stopped_speaking")

    machine.handle("processing_timed_out")

    assert machine.state is TurnState.DISPATCHER_SPEAKING


def test_false_cutoff_recovery_returns_to_supervisor_speaking():
    machine = TurnStateMachine(clock=make_clock())
    machine.handle("supervisor_started_speaking")

    machine.handle("false_cutoff_detected")
    assert machine.state is TurnState.FALSE_CUTOFF_RECOVERY

    machine.handle("resume_listening")
    assert machine.state is TurnState.SUPERVISOR_SPEAKING


@pytest.mark.parametrize(
    "starting_event",
    [
        "supervisor_started_speaking",
        None,  # sin transicionar — degradar directo desde LISTENING
    ],
)
def test_network_degraded_is_valid_from_any_non_terminal_state(starting_event):
    machine = TurnStateMachine(clock=make_clock())
    if starting_event:
        machine.handle(starting_event)

    machine.handle("network_degraded")
    assert machine.state is TurnState.DEGRADED_NETWORK

    machine.handle("network_restored")
    assert machine.state is TurnState.LISTENING


def test_disconnected_is_valid_from_any_non_terminal_state_and_only_reconnected_recovers():
    machine = TurnStateMachine(clock=make_clock())
    machine.handle("supervisor_started_speaking")
    machine.handle("supervisor_stopped_speaking")

    machine.handle("disconnected")
    assert machine.state is TurnState.DISCONNECTED

    with pytest.raises(InvalidTurnTransitionError):
        machine.handle("dispatcher_response_ready")

    machine.handle("reconnected")
    assert machine.state is TurnState.LISTENING


@pytest.mark.parametrize(
    "starting_event",
    [
        "supervisor_started_speaking",
        "supervisor_started_speaking,supervisor_stopped_speaking",
        None,
    ],
)
def test_pause_is_valid_from_any_active_state_and_resume_always_returns_to_listening(starting_event):
    """Roadmap Fase 2: control de pausa/abortar la práctica. Reanudar siempre vuelve a
    `listening`, la misma simplificación que ya usa `network_restored`."""
    machine = TurnStateMachine(clock=make_clock())
    for event in (starting_event or "").split(","):
        if event:
            machine.handle(event)

    machine.handle("pause_requested")
    assert machine.state is TurnState.PAUSED

    machine.handle("resume_requested")
    assert machine.state is TurnState.LISTENING


def test_dispatcher_greets_first_without_going_through_processing():
    """El dispatcher saluda antes de que el supervisor diga nada — única transición directa de
    `listening` a `dispatcher_speaking` (roadmap: orden mínimo de eventos de `call.start`)."""
    machine = TurnStateMachine(clock=make_clock())

    machine.handle("dispatcher_greeting")
    assert machine.state is TurnState.DISPATCHER_SPEAKING

    machine.handle("dispatcher_finished_speaking")
    assert machine.state is TurnState.LISTENING


def test_invalid_event_from_current_state_raises_and_does_not_change_state():
    machine = TurnStateMachine(clock=make_clock())

    with pytest.raises(InvalidTurnTransitionError):
        # No se puede "terminar de hablar" el dispatcher sin estar escuchándolo primero.
        machine.handle("dispatcher_finished_speaking")

    assert machine.state is TurnState.LISTENING
    assert machine.history == []
