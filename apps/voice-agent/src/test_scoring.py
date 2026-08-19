"""Unit tests del motor de métricas/ponderado (roadmap Fase 2, TODO-10 resuelto).

Dominio puro — sin FastAPI, sin SQLite, sin reloj real (todos los timestamps son literales
inyectados, igual que en `test_turn_state.py`).
"""

from core.ports import CriticalDataPoint
from core.scoring import ScoreWeights, score_session

VEHICLE_THEFT_POINTS = [
    CriticalDataPoint(key="incident_description", label="What happened"),
    CriticalDataPoint(key="vehicle_description", label="Vehicle description"),
    CriticalDataPoint(key="license_plate", label="License plate"),
    CriticalDataPoint(key="last_location", label="Last known location"),
]


def _operator(text: str, at: float) -> dict:
    return {"role": "operator", "text": text, "at": at}


def test_network_drop_outcome_returns_no_evaluation_regardless_of_content():
    transcript = [_operator("My car was stolen, license plate ABC123.", at=1010.0)]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1100.0, outcome="network_drop")

    assert result is None


def test_ended_outcome_scores_even_with_an_empty_transcript():
    result = score_session([], VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1010.0, outcome="ended")

    assert result is not None
    assert result["category_scores"]["completeness"] == 0
    assert result["missing"] == [point.label for point in VEHICLE_THEFT_POINTS]


def test_full_completeness_and_quick_response_score_near_the_top():
    transcript = [_operator(
        "Here's what happened: a vehicle was stolen, a white Toyota Camry, license plate "
        "ABC123, last seen near the shopping center.",
        at=1010.0,  # 10s después de empezar, bien dentro del target de 60s
    )]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["completeness"] == 100
    assert result["category_scores"]["time_to_critical_data"] == 100
    assert result["missing"] == []
    assert result["overall_score"] > 80


def test_missing_points_are_listed_and_lower_completeness():
    # A propósito sin las palabras "vehicle"/"description"/"what"/"happened"/"location" — el
    # matching es por palabra clave (ver docstring del módulo), así que el texto de prueba debe
    # evitar coincidencias accidentales para que el resultado sea significativo.
    transcript = [_operator("A car was taken, license plate ABC123.", at=1010.0)]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert "License plate" in result["collected"]
    assert "Vehicle description" in result["missing"]
    assert "Last known location" in result["missing"]
    assert 0 < result["category_scores"]["completeness"] < 100


def test_no_critical_data_never_mentioned_scores_zero_time_to_critical():
    transcript = [_operator("I don't have anything else to add right now.", at=1010.0)]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["time_to_critical_data"] == 0


def test_scenario_without_critical_data_points_does_not_penalize_completeness_or_time():
    result = score_session([_operator("Hello", at=1005.0)], [], started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["completeness"] == 100
    assert result["category_scores"]["time_to_critical_data"] == 100


def test_filler_words_lower_the_clarity_score():
    clean = [_operator("The vehicle was a white sedan parked near the mall.", at=1010.0)]
    fillers = [_operator("Um, so, like, the vehicle was, uh, a white sedan, you know, near the mall.", at=1010.0)]

    clean_result = score_session(clean, [], started_at=1000.0, ended_at=1090.0, outcome="ended")
    fillers_result = score_session(fillers, [], started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert fillers_result["category_scores"]["clarity"] < clean_result["category_scores"]["clarity"]


def test_custom_weights_change_the_composite_score():
    transcript = [_operator("License plate ABC123.", at=1010.0)]

    default = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")
    completeness_only = score_session(
        transcript,
        VEHICLE_THEFT_POINTS,
        started_at=1000.0,
        ended_at=1090.0,
        outcome="ended",
        weights=ScoreWeights(completeness=1.0, time_to_critical_data=0.0, clarity=0.0, total_time=0.0),
    )

    assert default["overall_score"] != completeness_only["overall_score"]
    # Solo 1/4 de los datos críticos mencionados -> con completitud=100% del peso, ~25.
    assert completeness_only["overall_score"] == 25


def test_score_weights_from_env_override_defaults(monkeypatch):
    monkeypatch.setenv("METRICS_WEIGHT_COMPLETENESS", "1")
    monkeypatch.setenv("METRICS_WEIGHT_TIME_TO_CRITICAL", "0")
    monkeypatch.setenv("METRICS_WEIGHT_CLARITY", "0")
    monkeypatch.setenv("METRICS_WEIGHT_TOTAL_TIME", "0")

    weights = ScoreWeights.from_env()

    assert weights == ScoreWeights(completeness=1.0, time_to_critical_data=0.0, clarity=0.0, total_time=0.0)
