"""Telemetria operacional sem conteúdo de reservas, URLs ou mensagens de exceção."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("hotelml.telemetry")


def event(name: str, **fields: object) -> None:
    log.info(
        json.dumps(
            {
                "schema_version": 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "event": name,
                **fields,
            },
            ensure_ascii=True,
            allow_nan=False,
        )
    )


class RequestTelemetry:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        status = 500
        sent = False
        error_type = None

        async def observed_send(message: Message) -> None:
            nonlocal status, sent
            if message["type"] == "http.response.start":
                status = message["status"]
                sent = True
                message = {
                    **message,
                    "headers": [
                        (k, v)
                        for k, v in message.get("headers", [])
                        if k.lower() != b"x-request-id"
                    ]
                    + [(b"x-request-id", request_id.encode("ascii"))],
                }
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        except Exception as exc:
            error_type = type(exc).__name__
            if sent:
                # Uma resposta parcial não pode ser substituída. Não propaga dados da exceção.
                raise RuntimeError("falha após início da resposta") from None
            await JSONResponse({"detail": "erro interno"}, status_code=500)(
                scope, receive, observed_send
            )
        finally:
            path = scope.get("path", "")
            # Probes bem-sucedidas são frequentes e não representam tráfego de negócio.
            if path not in {"/health/live", "/health/ready"} or status >= 400:
                route = path if path in {"/predict", "/health/live", "/health/ready"} else "other"
                method = scope.get("method", "")
                loaded = getattr(scope["app"].state, "loaded", None)
                event(
                    "http_request",
                    request_id=request_id,
                    route=route,
                    method=method
                    if method in {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"}
                    else "OTHER",
                    status_code=status,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                    model_name=loaded.name if loaded else None,
                    model_version=loaded.version if loaded else None,
                    error_type=error_type or scope["state"].get("error_type"),
                    booking_count=scope["state"].get("booking_count"),
                )
