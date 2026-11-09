"""Sondagem externa finita com reservas sintéticas e registro de cada tentativa."""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from hotelml.api import Booking
from hotelml.config import INPUT_COLUMNS
from hotelml.synthetic import make_synthetic

MAX_RESPONSE_BYTES = 65536


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str, payload: bytes, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "hotelml-synthetic-probe/1"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # Não copiar mensagens ou corpo de erros para o relatório.
        with exc:
            return exc.code, b""


def _prediction(body: bytes, target: str) -> tuple[str, str]:
    try:
        data = json.loads(body)
        if target == "azure":
            name, version = data["model_name"], data["model_version"]
            predictions = data["predictions"]
            if not isinstance(predictions, list) or len(predictions) != 1:
                raise ValueError
            probability = predictions[0]["cancellation_probability"]
            decision = predictions[0]["is_canceled"]
        else:
            if data["ok"] is not True or data["threshold"] != 0.5:
                raise ValueError
            name, version = data["modelName"], data["modelVersion"]
            probability, decision = data["probability"], data["isCanceled"]
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name) > 200
            or not isinstance(version, str)
            or not version.strip()
            or len(version) > 200
            or isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
            or not isinstance(decision, bool)
            or decision != (probability >= 0.5)
        ):
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError):
        raise ValueError("resposta de previsão fora do contrato") from None
    return name, version


def run_probe(
    url: str,
    output: Path,
    *,
    target: str,
    count: int = 3,
    interval: float = 5,
    timeout: float = 30,
    expected_version: str | None = None,
    fetch: Callable[[str, bytes, float], tuple[int, bytes]] = _fetch,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Uma chamada por tentativa, sem aquecimento ou retry; saída nova e marcadores de conclusão."""
    base = urlsplit(url)
    if (
        target not in {"azure", "web"}
        or base.scheme not in {"http", "https"}
        or not base.hostname
        or base.username is not None
        or base.password is not None
        or base.query
        or base.fragment
        or base.path not in {"", "/"}
        or (base.scheme == "http" and base.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise ValueError("use uma origem HTTPS sem caminho, credenciais ou parâmetros")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20:
        raise ValueError("quantidade deve estar entre 1 e 20 tentativas")
    for value, minimum in ((interval, 0), (timeout, 0.001)):
        if isinstance(value, bool) or not math.isfinite(value) or not minimum <= value <= 60:
            raise ValueError("intervalo deve estar em 0–60 s e timeout em 0,001–60 s")
    if expected_version is not None and (
        not isinstance(expected_version, str) or not expected_version.strip()
    ):
        raise ValueError("versão esperada inválida")
    endpoint = url.rstrip("/") + ("/predict" if target == "azure" else "/api/predict")
    # A validação reaproveita o contrato da API; nenhum dado observado é enviado.
    booking = Booking.model_validate(
        json.loads(make_synthetic(1, seed=7)[INPUT_COLUMNS].to_json(orient="records"))[0]
    ).model_dump()
    payload = json.dumps({"bookings": [booking]} if target == "azure" else {"booking": booking})
    output.mkdir(parents=True, exist_ok=False)
    started_at = datetime.now(UTC).isoformat()
    with (output / "run.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "schema_version": 1,
                "scope": "external_synthetic_prediction",
                "target": target,
                "origin": url.rstrip("/"),
                "started_at": started_at,
                "planned_attempts": count,
                "interval_after_completion_seconds": interval,
                "socket_timeout_seconds": timeout,
                "expected_version": expected_version,
                "payload_kind": "synthetic",
                "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            },
            stream,
            indent=2,
            allow_nan=False,
        )
    attempts = []
    with (output / "attempts.jsonl").open("x", encoding="utf-8") as stream:
        for index in range(count):
            if index:
                sleep(interval)
            attempt: dict = {
                "sequence": index + 1,
                "started_at": datetime.now(UTC).isoformat(),
                "http_status": None,
                "outcome": "network_error",
            }
            start = time.perf_counter()
            try:
                status, body = fetch(endpoint, payload.encode("utf-8"), timeout)
                attempt["http_status"] = status
                if not 200 <= status <= 299:
                    attempt["outcome"] = "http_error"
                elif len(body) > MAX_RESPONSE_BYTES:
                    attempt["outcome"] = "response_too_large"
                else:
                    try:
                        name, version = _prediction(body, target)
                    except ValueError:
                        attempt["outcome"] = "invalid_response"
                    else:
                        attempt["outcome"] = (
                            "success"
                            if expected_version is None or version == expected_version
                            else "version_mismatch"
                        )
                        if attempt["outcome"] == "success":
                            attempt.update(model_name=name, model_version=version)
            except TimeoutError:
                attempt["outcome"] = "timeout"
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, TimeoutError):
                    attempt["outcome"] = "timeout"
            except (OSError, ValueError, http.client.HTTPException):
                # Inclui conexão interrompida e erros de protocolo, sem persistir a exceção.
                pass
            attempt["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
            attempt["finished_at"] = datetime.now(UTC).isoformat()
            stream.write(json.dumps(attempt, allow_nan=False, ensure_ascii=False) + "\n")
            stream.flush()
            attempts.append(attempt)
    successful = [a for a in attempts if a["outcome"] == "success"]
    latencies = [a["duration_ms"] for a in successful]
    result = {
        "schema_version": 1,
        "scope": "external_synthetic_prediction",
        "target": target,
        "origin": url.rstrip("/"),
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "planned_attempts": count,
        "completed_attempts": len(attempts),
        "interval_after_completion_seconds": interval,
        "socket_timeout_seconds": timeout,
        "expected_version": expected_version,
        "successful_attempts": len(successful),
        "failed_attempts": count - len(successful),
        "success_rate": len(successful) / count,
        "outcomes": {
            outcome: sum(a["outcome"] == outcome for a in attempts)
            for outcome in sorted({a["outcome"] for a in attempts})
        },
        "successful_latency_ms": {
            name: float(np.percentile(latencies, percentile)) if latencies else None
            for name, percentile in (("p50", 50), ("p95", 95), ("p99", 99))
        },
        "attempts_sha256": hashlib.sha256((output / "attempts.jsonl").read_bytes()).hexdigest(),
        "run_sha256": hashlib.sha256((output / "run.json").read_bytes()).hexdigest(),
        "slo_status": "not_evaluated",
        "limitation": (
            "Amostra de sondagem sintética deste cliente, sem SLO de produção. "
            "Primeira tentativa não comprova cold start. "
            "Timeout de socket não é prazo total de DNS/HTTP."
        ),
    }
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    (output / "_SUCCESS").touch(exist_ok=False)
    return result
