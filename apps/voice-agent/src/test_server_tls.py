"""Unit tests de la generación de certificado autofirmado (NFR-05, server/tls.py)."""

import datetime

from cryptography import x509

from server.tls import ensure_self_signed_cert, generate_self_signed_cert


def test_generate_self_signed_cert_produces_parseable_pem_with_expected_common_name():
    cert_pem, key_pem = generate_self_signed_cert(common_name="test.local", valid_days=30)

    certificate = x509.load_pem_x509_certificate(cert_pem)
    common_name = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0]

    assert common_name.value == "test.local"
    assert b"BEGIN PRIVATE KEY" in key_pem
    assert b"BEGIN CERTIFICATE" in cert_pem


def test_generate_self_signed_cert_is_valid_now_and_expires_after_valid_days():
    cert_pem, _ = generate_self_signed_cert(common_name="test.local", valid_days=30)
    certificate = x509.load_pem_x509_certificate(cert_pem)

    now = datetime.datetime.now(datetime.timezone.utc)

    assert certificate.not_valid_before_utc <= now
    assert certificate.not_valid_after_utc > now + datetime.timedelta(days=29)
    assert certificate.not_valid_after_utc < now + datetime.timedelta(days=31)


def test_ensure_self_signed_cert_writes_both_files_when_missing(tmp_path):
    cert_path = str(tmp_path / "server.crt")
    key_path = str(tmp_path / "server.key")

    returned_cert, returned_key = ensure_self_signed_cert(cert_path, key_path)

    assert returned_cert == cert_path
    assert returned_key == key_path
    assert (tmp_path / "server.crt").exists()
    assert (tmp_path / "server.key").exists()


def test_ensure_self_signed_cert_is_idempotent(tmp_path):
    cert_path = str(tmp_path / "server.crt")
    key_path = str(tmp_path / "server.key")

    ensure_self_signed_cert(cert_path, key_path)
    first_cert_bytes = (tmp_path / "server.crt").read_bytes()

    ensure_self_signed_cert(cert_path, key_path)
    second_cert_bytes = (tmp_path / "server.crt").read_bytes()

    # No se regenera si ya existe — regenerar en cada arranque rompería la confianza que el
    # navegador de cada supervisor ya le dio al certificado anterior.
    assert first_cert_bytes == second_cert_bytes
