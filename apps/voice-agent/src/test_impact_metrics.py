"""Unit tests de `core/impact_metrics.py` (roadmap Fase 3) — dominio puro, sin SQLite/FastAPI,
mismo patrón que `test_scoring.py`.
"""

from core.impact_metrics import MIN_SAMPLE_SIZE_FOR_CONFIDENCE, compute_impact_report
from core.ports import IncidentOutcome, SessionRecord


def _incident(supervisor_id, occurred_at, outcome_rating, **overrides) -> IncidentOutcome:
    fields = dict(
        id=f"incident-{supervisor_id}-{occurred_at}",
        occurred_at=occurred_at,
        supervisor_id=supervisor_id,
        category="Vehicle Theft",
        outcome_rating=outcome_rating,
        critical_data_captured=True,
        protocol_followed=True,
    )
    fields.update(overrides)
    return IncidentOutcome(**fields)


def _completed_session(supervisor_id, ended_at) -> SessionRecord:
    return SessionRecord(
        session_id=f"session-{supervisor_id}-{ended_at}",
        supervisor_id=supervisor_id,
        scenario_name="Vehicle Theft",
        started_at=ended_at - 60,
        ended_at=ended_at,
        outcome="ended",
    )


def test_empty_incident_list_is_not_conclusive_and_says_so():
    report = compute_impact_report([], {})

    assert report.total_incidents == 0
    assert report.is_conclusive is False
    assert "No real incidents" in report.caveat


def test_below_minimum_sample_size_is_not_conclusive():
    incidents = [_incident("sup-1", occurred_at=100, outcome_rating=5)]

    report = compute_impact_report(incidents, {})

    assert report.is_conclusive is False
    assert str(MIN_SAMPLE_SIZE_FOR_CONFIDENCE) in report.caveat


def test_supervisor_with_a_completed_session_before_the_incident_counts_as_trained():
    incidents = [
        _incident("sup-1", occurred_at=200 + i, outcome_rating=5)
        for i in range(MIN_SAMPLE_SIZE_FOR_CONFIDENCE)
    ]
    sessions_by_supervisor = {"sup-1": [_completed_session("sup-1", ended_at=100)]}

    report = compute_impact_report(incidents, sessions_by_supervisor)

    assert report.trained.sample_size == MIN_SAMPLE_SIZE_FOR_CONFIDENCE
    assert report.untrained.sample_size == 0


def test_session_completed_after_the_incident_does_not_count_as_trained():
    incidents = [_incident("sup-1", occurred_at=100 + i, outcome_rating=5) for i in range(5)]
    # la sesión se completó DESPUÉS del incidente — no puede haber influido en ese incidente.
    sessions_by_supervisor = {"sup-1": [_completed_session("sup-1", ended_at=500)]}

    report = compute_impact_report(incidents, sessions_by_supervisor)

    assert report.trained.sample_size == 0
    assert report.untrained.sample_size == 5


def test_network_drop_sessions_do_not_count_as_completed_training():
    incidents = [_incident("sup-1", occurred_at=200 + i, outcome_rating=5) for i in range(5)]
    dropped_session = SessionRecord(
        session_id="s1", supervisor_id="sup-1", scenario_name="x",
        started_at=50, ended_at=60, outcome="network_drop",
    )

    report = compute_impact_report(incidents, {"sup-1": [dropped_session]})

    assert report.untrained.sample_size == 5


def test_group_averages_are_computed_independently_per_group():
    trained = [_incident("trained-sup", occurred_at=200 + i, outcome_rating=5) for i in range(5)]
    untrained = [_incident("untrained-sup", occurred_at=200 + i, outcome_rating=1) for i in range(5)]
    sessions_by_supervisor = {"trained-sup": [_completed_session("trained-sup", ended_at=100)]}

    report = compute_impact_report(trained + untrained, sessions_by_supervisor)

    assert report.is_conclusive is True
    assert report.trained.avg_outcome_rating == 5.0
    assert report.untrained.avg_outcome_rating == 1.0
    assert report.caveat == ""


def test_capture_and_protocol_rates_are_fractions_of_the_group():
    incidents = [
        _incident("sup-1", occurred_at=200 + i, outcome_rating=3, critical_data_captured=(i % 2 == 0))
        for i in range(MIN_SAMPLE_SIZE_FOR_CONFIDENCE)
    ]

    report = compute_impact_report(incidents, {})

    assert report.untrained.critical_data_capture_rate == 3 / MIN_SAMPLE_SIZE_FOR_CONFIDENCE
