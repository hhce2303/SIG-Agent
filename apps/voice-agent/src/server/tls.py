"""TLS del servidor — NFR-05 ("WSS/TLS como mínimo de Fase 1, ni siquiera en LAN interna").

Genera (si no existen) un certificado autofirmado + su clave privada para poder levantar el
servidor con WSS/TLS sin depender de una CA externa — razonable para una caja LAN interna de un
solo concesionario (NFR-11: una sola ubicación, concurrencia=1). Quien sea el dueño operativo de
la caja (ver TODO-03) puede reemplazar este certificado autofirmado por uno de una CA interna
real sin tocar `server_main.py` — solo apuntando `TLS_CERT_PATH`/`TLS_KEY_PATH` a esos archivos.

Los supervisores van a necesitar confiar en este certificado autofirmado una vez por máquina
cliente (o correr un reverse proxy con un certificado real delante) — eso es un paso operativo
que este módulo no puede resolver por sí solo.
"""

import datetime
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

DEFAULT_COMMON_NAME = "voice-agent.local"
DEFAULT_VALID_DAYS = 825  # tope aceptado por la mayoría de navegadores para certs autofirmados


def generate_self_signed_cert(
    common_name: str = DEFAULT_COMMON_NAME,
    valid_days: int = DEFAULT_VALID_DAYS,
) -> tuple[bytes, bytes]:
    """Genera un par (cert PEM, key PEM) autofirmado. No toca disco — eso lo decide quien llama
    (ver `ensure_self_signed_cert`), lo que hace esto fácil de probar sin filesystem."""

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)

    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)  # autofirmado: issuer == subject
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=valid_days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
        .sign(private_key, hashes.SHA256())
    )

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return cert_pem, key_pem


def ensure_self_signed_cert(
    cert_path: str,
    key_path: str,
    common_name: str = DEFAULT_COMMON_NAME,
) -> tuple[str, str]:
    """Idempotente: si ambos archivos ya existen, no genera uno nuevo — regenerar el
    certificado en cada arranque obligaría a los supervisores a volver a confiarlo en su
    navegador cada vez."""

    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    cert_pem, key_pem = generate_self_signed_cert(common_name=common_name)

    with open(cert_path, "wb") as f:
        f.write(cert_pem)

    with open(key_path, "wb") as f:
        f.write(key_pem)

    return cert_path, key_path
