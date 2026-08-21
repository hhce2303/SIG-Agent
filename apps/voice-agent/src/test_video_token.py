"""Unit tests de `HmacVideoTokenIssuer` (ADR-0009, TODO-19) — sin red, sin servidor real."""

import pytest

from auth.video_token import HmacVideoTokenIssuer
from core.ports import InvalidVideoTokenError


def make_clock(start=1000.0):
    box = {"now": start}

    def clock():
        return box["now"]

    def advance(seconds):
        box["now"] += seconds

    return clock, advance


def test_issue_then_verify_round_trips_claims():
    clock, _ = make_clock()
    issuer = HmacVideoTokenIssuer(secret_key=b"test-secret", clock=clock)

    token = issuer.issue(scenario_id="robbery_001", supervisor_id="sup-42")
    claims = issuer.verify(token, scenario_id="robbery_001")

    assert claims.scenario_id == "robbery_001"
    assert claims.supervisor_id == "sup-42"
    assert claims.issued_at == 1000.0


def test_verify_rejects_a_token_issued_for_a_different_scenario():
    issuer = HmacVideoTokenIssuer(secret_key=b"test-secret")
    token = issuer.issue(scenario_id="robbery_001", supervisor_id="sup-42")

    with pytest.raises(InvalidVideoTokenError, match="scenario_id"):
        issuer.verify(token, scenario_id="robbery_002")


def test_verify_rejects_token_signed_with_a_different_secret():
    issuer = HmacVideoTokenIssuer(secret_key=b"correct-secret")
    forged_issuer = HmacVideoTokenIssuer(secret_key=b"wrong-secret")

    forged_token = forged_issuer.issue(scenario_id="robbery_001", supervisor_id="sup-42")

    with pytest.raises(InvalidVideoTokenError, match="signature"):
        issuer.verify(forged_token, scenario_id="robbery_001")


def test_verify_rejects_malformed_token():
    issuer = HmacVideoTokenIssuer(secret_key=b"test-secret")

    with pytest.raises(InvalidVideoTokenError, match="malformed"):
        issuer.verify("not-a-real-token", scenario_id="robbery_001")


def test_verify_rejects_expired_token():
    # TTL corto a propósito (ADR-0009: minutos, no horas) — default real es 5 minutos.
    clock, advance = make_clock()
    issuer = HmacVideoTokenIssuer(secret_key=b"test-secret", ttl_seconds=300, clock=clock)

    token = issuer.issue(scenario_id="robbery_001", supervisor_id="sup-42")
    advance(301)

    with pytest.raises(InvalidVideoTokenError, match="expired"):
        issuer.verify(token, scenario_id="robbery_001")


def test_constructor_rejects_empty_secret_key():
    with pytest.raises(ValueError):
        HmacVideoTokenIssuer(secret_key=b"")
