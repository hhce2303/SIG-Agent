"""Adaptador de auth para servir video de escenarios — ver ADR-0009 (TODO-19).

Implementa `VideoTokenPort` (ver `core/ports.py`). Un `<video>` HTML no puede adjuntar el header
`Authorization` (bearer, ADR-0008) a su request, así que la ruta que sirve el archivo no puede
protegerse igual que el resto de las rutas REST. Este token es un mecanismo separado, de vida
deliberadamente corta (minutos, no horas): mismo HMAC-SHA256 + base64 de stdlib que
`HmacSessionTokenIssuer` (ADR-0008), sin dependencia nueva. Se obtiene primero con un request REST
normal (con bearer, `GET /scenarios/{id}/video`), y se usa una sola vez como query param contra la
ruta de streaming — mismo patrón que el WebSocket ya usa (`?token=`, ver `server/app.py`).
"""

import base64
import hashlib
import hmac
import json
import time

from core.ports import InvalidVideoTokenError, VideoTokenClaims, VideoTokenPort

DEFAULT_TTL_SECONDS = 5 * 60  # de vida corta a propósito — ver ADR-0009


class HmacVideoTokenIssuer(VideoTokenPort):

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

    def issue(self, scenario_id: str, supervisor_id: str) -> str:
        payload = {
            "scenario_id": scenario_id,
            "supervisor_id": supervisor_id,
            "issued_at": self._clock(),
        }
        encoded_payload = self._encode(payload)
        signature = self._sign(encoded_payload)

        return f"{encoded_payload.decode()}.{signature}"

    def verify(self, token: str, scenario_id: str) -> VideoTokenClaims:
        try:
            encoded_payload, signature = token.split(".")
        except ValueError:
            raise InvalidVideoTokenError("malformed token") from None

        if not hmac.compare_digest(signature, self._sign(encoded_payload.encode())):
            raise InvalidVideoTokenError("signature mismatch")

        payload = self._decode(encoded_payload)

        if self._clock() - payload["issued_at"] > self._ttl_seconds:
            raise InvalidVideoTokenError("token expired")

        if payload["scenario_id"] != scenario_id:
            # No es un scope real por-conexión como NFR-04 (no hay una conexión persistente que
            # aislar acá) — pero un token emitido para un escenario no debe servir para leer el
            # video de otro, mismo espíritu que la verificación de session_id del WebSocket.
            raise InvalidVideoTokenError("token does not match scenario_id")

        return VideoTokenClaims(
            scenario_id=payload["scenario_id"],
            supervisor_id=payload["supervisor_id"],
            issued_at=payload["issued_at"],
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
            raise InvalidVideoTokenError("malformed payload") from error
