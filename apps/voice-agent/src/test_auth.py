"""Unit tests de `HmacSessionTokenIssuer` (ADR-0008) — sin red, sin servidor real."""

import pytest

from auth.session_token import HmacSessionTokenIssuer
from core.ports import InvalidSessionTokenError


def make_clock(start=1000.0):
    box = {"now": start}

    def clock():
        return box["now"]

    def advance(seconds):
        box["now"] += seconds

    return clock, advance


def test_issue_then_verify_round_trips_claims():
    clock, _ = make_clock()
    issuer = HmacSessionTokenIssuer(secret_key=b"test-secret", clock=clock)

    token = issuer.issue(supervisor_id="sup-42", session_id="sess-1")
    claims = issuer.verify(token)

    assert claims.supervisor_id == "sup-42"
    assert claims.session_id == "sess-1"
    assert claims.issued_at == 1000.0


def test_verify_rejects_token_signed_with_a_different_secret():
    clock, _ = make_clock()
    issuer = HmacSessionTokenIssuer(secret_key=b"correct-secret", clock=clock)
    forged_issuer = HmacSessionTokenIssuer(secret_key=b"wrong-secret", clock=clock)

    forged_token = forged_issuer.issue(supervisor_id="sup-42", session_id="sess-1")

    with pytest.raises(InvalidSessionTokenError, match="signature"):
        issuer.verify(forged_token)


def test_verify_rejects_malformed_token():
    issuer = HmacSessionTokenIssuer(secret_key=b"test-secret")

    with pytest.raises(InvalidSessionTokenError, match="malformed"):
        issuer.verify("not-a-real-token")


def test_verify_rejects_expired_token():
    clock, advance = make_clock()
    issuer = HmacSessionTokenIssuer(secret_key=b"test-secret", ttl_seconds=60, clock=clock)

    token = issuer.issue(supervisor_id="sup-42", session_id="sess-1")
    advance(61)

    with pytest.raises(InvalidSessionTokenError, match="expired"):
        issuer.verify(token)


def test_verify_accepts_token_right_at_the_ttl_boundary():
    clock, advance = make_clock()
    issuer = HmacSessionTokenIssuer(secret_key=b"test-secret", ttl_seconds=60, clock=clock)

    token = issuer.issue(supervisor_id="sup-42", session_id="sess-1")
    advance(60)

    issuer.verify(token)  # no debe levantar


def test_constructor_rejects_empty_secret_key():
    with pytest.raises(ValueError):
        HmacSessionTokenIssuer(secret_key=b"")
