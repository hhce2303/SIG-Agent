"""Adaptador de auth por sesión — token propio firmado (ADR-0008, accepted 2026-08-19).

Implementa `SessionTokenPort` (ver `core/ports.py`). Sin dependencias nuevas: HMAC-SHA256 +
base64 de la librería estándar, sin librería externa de JWT. El scope por conexión que exige
NFR-04 (una conexión no puede apuntar a la sesión de otra) lo impone quien *valida* el token
contra el `session_id` de la conexión WebSocket entrante — este adaptador solo garantiza
autenticidad (firma válida) y vigencia (no expirado), no decide autorización por sí solo.
"""

import base64
import hashlib
import hmac
import json
import time

from core.ports import InvalidSessionTokenError, SessionTokenClaims, SessionTokenPort

DEFAULT_TTL_SECONDS = 8 * 60 * 60  # un turno de trabajo — ver TODO-04 (retención) para el resto


class HmacSessionTokenIssuer(SessionTokenPort):

    def __init__(
        self,
        secret_key: bytes,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock=time.time,
    ):
        if not secret_key:
            raise ValueError("secret_key must not be empty")

        self._secret_key = secret_key
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def issue(self, supervisor_id: str, session_id: str, role: str = "supervisor") -> str:
        payload = {
            "supervisor_id": supervisor_id,
            "session_id": session_id,
            "issued_at": self._clock(),
            "role": role,
        }
        encoded_payload = self._encode(payload)
        signature = self._sign(encoded_payload)

        return f"{encoded_payload.decode()}.{signature}"

    def verify(self, token: str) -> SessionTokenClaims:
        try:
            encoded_payload, signature = token.split(".")
        except ValueError:
            raise InvalidSessionTokenError("malformed token") from None

        if not hmac.compare_digest(signature, self._sign(encoded_payload.encode())):
            raise InvalidSessionTokenError("signature mismatch")

        payload = self._decode(encoded_payload)

        if self._clock() - payload["issued_at"] > self._ttl_seconds:
            raise InvalidSessionTokenError("token expired")

        return SessionTokenClaims(
            supervisor_id=payload["supervisor_id"],
            session_id=payload["session_id"],
            issued_at=payload["issued_at"],
            # ADR-0011: tokens emitidos antes de este campo (o por cualquier issuer viejo en
            # memoria) no tienen "role" en su payload — default "supervisor" preserva su
            # comportamiento exacto de antes, nadie se vuelve manager por un token viejo.
            role=payload.get("role", "supervisor"),
        )

    def _sign(self, encoded_payload: bytes) -> str:
        return hmac.new(self._secret_key, encoded_payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _encode(payload: dict) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(payload).encode())

    @staticmethod
    def _decode(encoded_payload: str) -> dict:
        try:
            return json.loads(base64.urlsafe_b64decode(encoded_payload))
        except (ValueError, UnicodeDecodeError) as error:
            raise InvalidSessionTokenError("malformed payload") from error
