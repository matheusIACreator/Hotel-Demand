"""SLIs de pedidos observados no processo da API, sem inferir disponibilidade externa."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp deve ser uma data com fuso horário")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp inválido") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("timestamp deve incluir fuso horário")
    return stamp.astimezone(UTC)


def evaluate_slo(
    events: list[dict],
    *,
    start: str,
    end: str,
    availability_target: float,
    latency_target: float,
    latency_ms: float,
    data_kind: str,
    complete_window: bool = False,
    minimum: int = 100,
) -> dict:
    """Avalia [start, end); completude é declaração do operador, não inferência dos logs."""
    window_start, window_end = _timestamp(start), _timestamp(end)
    if (
        window_start >= window_end
        or data_kind not in {"synthetic", "observed"}
        or isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or minimum < 1
        or not isinstance(complete_window, bool)
    ):
        raise ValueError("janela ou parâmetros inválidos")
    for target in (availability_target, latency_target):
        if isinstance(target, bool) or not math.isfinite(target) or not 0 < target < 1:
            raise ValueError("metas devem estar entre 0 e 1, exclusivamente")
    if isinstance(latency_ms, bool) or not math.isfinite(latency_ms) or latency_ms <= 0:
        raise ValueError("limite de latência deve ser positivo e finito")
    seen: set[str] = set()
    successful_durations = []
    eligible = successful = fast = excluded = 0
    for item in events:
        if not isinstance(item, dict):
            raise ValueError("evento deve ser um objeto JSON")
        if (
            item.get("event") != "http_request"
            or item.get("route") != "/predict"
            or item.get("method") != "POST"
        ):
            continue
        stamp = _timestamp(item.get("timestamp"))
        if not window_start <= stamp < window_end:
            continue
        if type(item.get("schema_version")) is not int or item["schema_version"] != 1:
            raise ValueError("versão de telemetria não suportada")
        request_id = item.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip() or request_id in seen:
            raise ValueError("request_id ausente ou duplicado na janela")
        seen.add(request_id)
        status, duration = item.get("status_code"), item.get("duration_ms")
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            raise ValueError("status HTTP inválido")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise ValueError("duração inválida")
        # Erros do cliente não participam do denominador; permanecem visíveis no relatório.
        if 400 <= status <= 499:
            excluded += 1
            continue
        eligible += 1
        if 200 <= status <= 299:
            successful += 1
            successful_durations.append(duration)
            fast += duration <= latency_ms
    reasons = []
    if not complete_window:
        reasons.append("collection_not_confirmed_complete")
    if eligible < minimum:
        reasons.append("insufficient_requests")
    ready = not reasons

    def objective(good: int, target: float) -> dict:
        bad = eligible - good
        allowed = eligible * (1 - target)
        sli = good / eligible if eligible else None
        return {
            "target": target,
            "good_requests": good,
            "bad_requests": bad,
            "sli": sli,
            "met": (sli >= target) if ready and sli is not None else None,
            "allowed_bad_requests": allowed if ready else None,
            "remaining_bad_requests": allowed - bad if ready else None,
            "budget_consumed_ratio": bad / allowed if ready else None,
            "burn_rate": (bad / eligible) / (1 - target) if ready else None,
        }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "api_process_observed_requests",
        "data_kind": data_kind,
        "window": {"start": window_start.isoformat(), "end_exclusive": window_end.isoformat()},
        "collection_declared_complete": complete_window,
        "minimum_requests": minimum,
        "status": "ready" if ready else "inconclusive",
        "inconclusive_reasons": reasons,
        "observed_requests": eligible + excluded,
        "excluded_client_errors": excluded,
        "eligible_requests": eligible,
        "availability": objective(successful, availability_target),
        "latency": {"threshold_ms": latency_ms, **objective(fast, latency_target)},
        "successful_latency_ms": {
            name: float(np.percentile(successful_durations, percentile))
            if successful_durations
            else None
            for name, percentile in (("p50", 50), ("p95", 95), ("p99", 99))
        },
        "limitation": (
            "Pedidos observados dentro da API; exclui rede, ingress, espera por réplica "
            "e Vercel. Completude declarada não comprova ausência de perda na coleta."
        ),
    }


def slo_report(source: Path, output: Path, *, input_format: str = "jsonl", **kwargs: Any) -> dict:
    if output.exists():
        raise FileExistsError(output)
    data = source.read_bytes()
    content = data.decode("utf-8-sig")
    if input_format == "jsonl":
        events = [json.loads(line) for line in content.splitlines() if line.strip()]
    elif input_format == "azure":
        response = json.loads(content)
        if not isinstance(response, dict) or response.get("error"):
            raise ValueError("resposta Azure inválida ou parcial")
        tables = response.get("tables")
        if not isinstance(tables, list) or len(tables) != 1:
            raise ValueError("esperada uma tabela Azure com event_json")
        table = tables[0]
        if not isinstance(table, dict) or table.get("columns") != [
            {"name": "event_json", "type": "string"}
        ]:
            raise ValueError("projeção Azure deve conter somente event_json string")
        rows = table.get("rows")
        if not isinstance(rows, list) or any(
            not isinstance(r, list) or len(r) != 1 or not isinstance(r[0], str) for r in rows
        ):
            raise ValueError("linhas Azure inválidas")
        events = [json.loads(row[0]) for row in rows]
    else:
        raise ValueError("formato de entrada não suportado")
    result = evaluate_slo(events, **kwargs)
    result["provenance"] = {
        "events_sha256": hashlib.sha256(data).hexdigest(),
        "input_format": input_format,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result
