"""Controle temporal, coleta e auditoria do piloto externo aprovado."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("data deve incluir fuso")
    return result.astimezone(UTC)


def load_policy(path: Path) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    start, end = timestamp(policy["start"]), timestamp(policy["end"])
    if (
        policy["schema_version"] != 1
        or not re.fullmatch(r"[a-z0-9-]+", policy["pilot_id"])
        or end - start != timedelta(days=14)
        or policy["period_seconds"] != 3600
        or policy["diagnostic_attempts"] != 2
        or policy["retention_days"] != 30
        # Abaixo do arranque a frio medido (~31 s) o timeout censura a duração; 60 s é o teto
        # da própria sondagem (ADR 0013).
        or not 30 <= policy["timeout_seconds"] <= 60
        or policy["diagnostic_interval_seconds"] != 5
        or policy["collection_grace_seconds"] != 5400
        or start.minute != 17
        or start.second != 0
        or start.microsecond != 0
    ):
        raise ValueError("política fora dos limites aprovados")
    return policy


def slot_for(policy: dict, value: datetime) -> int | None:
    start, end = timestamp(policy["start"]), timestamp(policy["end"])
    if not start <= value < end:
        return None
    return int((value - start).total_seconds() // policy["period_seconds"])


def slot_open(policy: dict, slot: int, now: datetime) -> bool:
    scheduled = timestamp(policy["start"]) + timedelta(seconds=slot * policy["period_seconds"])
    # Não carregar tentativas do último slot de ontem para o orçamento UTC de hoje.
    return slot_for(policy, now) == slot and now.date() == scheduled.date()


def outputs(**values: object) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def gate(policy: dict, *, now: datetime, event: str, attempt: int) -> dict:
    active = slot_for(policy, now) is not None and event == "schedule" and attempt == 1
    result = {
        "active": active,
        "expired": now
        >= timestamp(policy["end"])
        + timedelta(seconds=policy["collection_grace_seconds"] - policy["period_seconds"]),
        "pilot_id": policy["pilot_id"],
    }
    outputs(**result)
    return result


def api(path: str) -> dict:
    token = os.environ["GH_TOKEN"]
    request = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pages(path: str, key: str) -> list[dict]:
    records = []
    for page in range(1, 101):
        response = api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        batch = response[key]
        records.extend(batch)
        if len(batch) < 100:
            return records
    raise RuntimeError("paginação incompleta; coleta suspensa")


def reserve_slot(policy: dict, runs: list[dict], current: dict, now: datetime) -> int | None:
    """Só o primeiro run agendado criado para um slot pode enviar tráfego."""
    if current["event"] != "schedule" or current["run_attempt"] != 1:
        return None
    created = timestamp(current["created_at"])
    slot = slot_for(policy, created)
    # Um job atrasado não pode executar o slot de uma hora anterior.
    if slot is None or not slot_open(policy, slot, now):
        return None
    owners = [
        run["id"]
        for run in runs
        if run["event"] == "schedule" and slot_for(policy, timestamp(run["created_at"])) == slot
    ]
    if not owners or current["id"] != min(owners):
        return None
    return slot


def collect(policy: dict, output: Path, slot: int) -> dict:
    from hotelml.probe import run_probe

    # A reserva remota antecede esta função; um diretório novo preserva interrupções locais.
    if not slot_open(policy, slot, datetime.now(UTC)):
        raise RuntimeError("slot expirou antes da chamada; não enviar tráfego")
    output.mkdir(parents=True, exist_ok=False)
    primary = run_probe(
        policy["origin"],
        output / "primary",
        target="web",
        count=1,
        timeout=policy["timeout_seconds"],
        expected_version=policy["expected_version"],
    )
    primary_status = "failure" if primary["failed_attempts"] else "success"
    # Publicar imediatamente: uma falha posterior no diagnóstico não apaga o resultado principal.
    outputs(primary_status=primary_status)
    diagnostics = []
    if primary_status == "failure":
        import time

        for index in range(policy["diagnostic_attempts"]):
            time.sleep(policy["diagnostic_interval_seconds"])
            if not slot_open(policy, slot, datetime.now(UTC)):
                break
            diagnostic = run_probe(
                policy["origin"],
                output / f"diagnostic-{index + 1}",
                target="web",
                count=1,
                timeout=policy["timeout_seconds"],
                expected_version=policy["expected_version"],
            )
            diagnostics.append(diagnostic)
    result = {
        "schema_version": 1,
        "pilot_id": policy["pilot_id"],
        "slot": slot,
        "primary_status": primary_status,
        "primary_attempts": primary["completed_attempts"],
        "diagnostic_attempts": sum(d["completed_attempts"] for d in diagnostics),
        "primary_success_rate": primary["success_rate"],
        "diagnostic_success_rate": (
            sum(d["success_rate"] for d in diagnostics) / len(diagnostics) if diagnostics else None
        ),
        "slo_status": "not_evaluated",
    }
    (output / "pilot.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def audit(policy: dict, artifacts: list[dict], now: datetime) -> dict:
    prefix = "probe-" + policy["pilot_id"] + "-"
    slots: dict[int, list[str]] = {}
    for artifact in artifacts:
        if artifact.get("expired") or not artifact["name"].startswith(prefix):
            continue
        match = re.fullmatch(
            re.escape(prefix) + r"(\d+)-(success|failure|incomplete)", artifact["name"]
        )
        if match:
            slots.setdefault(int(match[1]), []).append(match[2])
    start, end = timestamp(policy["start"]), timestamp(policy["end"])
    counts = dict.fromkeys(
        ("success", "failure", "missing", "pending", "incomplete", "duplicate"), 0
    )
    missing = []
    expected = 0
    for slot in range(int((end - start).total_seconds() // policy["period_seconds"])):
        scheduled = start + timedelta(seconds=slot * policy["period_seconds"])
        if scheduled > now:
            break
        expected += 1
        evidence = slots.get(slot, [])
        if len(evidence) > 1:
            status = "duplicate"
        elif evidence:
            status = evidence[0]
        elif now < scheduled + timedelta(seconds=policy["collection_grace_seconds"]):
            status = "pending"
        else:
            status = "missing"
            missing.append(scheduled.isoformat())
        counts[status] += 1
    completed = counts["success"] + counts["failure"]
    return {
        "schema_version": 1,
        "pilot_id": policy["pilot_id"],
        "audited_at": now.isoformat(),
        "start": policy["start"],
        "end_exclusive": policy["end"],
        "expected_slots_so_far": expected,
        "counts": counts,
        "missing_scheduled_times": missing,
        "primary_success_rate_observed": counts["success"] / completed if completed else None,
        "collection_coverage": completed / expected if expected else None,
        "slo_status": "not_evaluated",
        "limitation": "Ausência de artefato é lacuna de coleta, não indisponibilidade da API.",
    }


def _attempts(directory: Path) -> list[dict]:
    path = directory / "attempts.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _percentiles(values: list[float]) -> dict:
    import numpy as np

    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "max": max(values),
    }


def review(policy: dict, artifacts: Path, now: datetime) -> dict:
    """Resume os journals baixados; lê só tentativas concluídas, sem inferir slots ausentes."""
    prefix = "probe-" + policy["pilot_id"] + "-"
    slots: dict[int, dict] = {}
    skipped = []
    for directory in sorted(p for p in artifacts.iterdir() if p.is_dir()):
        match = re.fullmatch(
            re.escape(prefix) + r"(\d+)-(success|failure|incomplete)", directory.name
        )
        if not match:
            continue
        slot = int(match[1])
        root = directory
        primary = _attempts(root / "primary")
        if slot in slots or len(primary) != 1 or not (root / "primary" / "_SUCCESS").is_file():
            skipped.append(directory.name)
            slots.pop(slot, None)
            continue
        diagnostics = [
            attempt
            for index in range(1, policy["diagnostic_attempts"] + 1)
            for attempt in _attempts(root / f"diagnostic-{index}")
        ]
        recovered = next((d for d in diagnostics if d["outcome"] == "success"), None)
        slots[slot] = {
            "primary": primary[0],
            "diagnostics": diagnostics,
            # Da primeira chamada até o fim do primeiro diagnóstico bem-sucedido.
            "recovery_seconds": (
                (
                    timestamp(recovered["finished_at"]) - timestamp(primary[0]["started_at"])
                ).total_seconds()
                if recovered and primary[0]["outcome"] != "success"
                else None
            ),
        }
    primaries = [entry["primary"] for entry in slots.values()]
    successes = [a for a in primaries if a["outcome"] == "success"]
    failures = [a for a in primaries if a["outcome"] != "success"]
    start, end = timestamp(policy["start"]), timestamp(policy["end"])
    total = int((end - start).total_seconds() // policy["period_seconds"])
    # Mesmo critério da auditoria: conta os slots cujo horário planejado já chegou.
    expected = (
        0
        if now < start
        else min(total, int((now - start).total_seconds() // policy["period_seconds"]) + 1)
    )
    recoveries = [e["recovery_seconds"] for e in slots.values() if e["recovery_seconds"]]
    return {
        "schema_version": 1,
        "pilot_id": policy["pilot_id"],
        "reviewed_at": now.isoformat(),
        "timeout_seconds": policy["timeout_seconds"],
        "expected_slots_so_far": expected,
        "slots_with_primary": len(primaries),
        "collection_coverage": len(primaries) / expected if expected else None,
        "skipped_artifacts": skipped,
        "primary_successes": len(successes),
        "primary_failures": len(failures),
        "primary_success_rate_observed": len(successes) / len(primaries) if primaries else None,
        "primary_outcomes": {
            outcome: sum(a["outcome"] == outcome for a in primaries)
            for outcome in sorted({a["outcome"] for a in primaries})
        },
        "primary_http_statuses": {
            str(status): sum(a["http_status"] == status for a in primaries)
            for status in sorted({a["http_status"] for a in primaries}, key=str)
        },
        "primary_success_duration_ms": _percentiles([a["duration_ms"] for a in successes]),
        "primary_failure_duration_ms": _percentiles([a["duration_ms"] for a in failures]),
        "failed_slots_with_successful_diagnostic": len(recoveries),
        "recovery_seconds": _percentiles(recoveries),
        "slots": {
            str(slot): {
                "started_at": entry["primary"]["started_at"],
                "outcome": entry["primary"]["outcome"],
                "http_status": entry["primary"]["http_status"],
                "duration_ms": entry["primary"]["duration_ms"],
                "diagnostic_outcomes": [d["outcome"] for d in entry["diagnostics"]],
                "recovery_seconds": entry["recovery_seconds"],
            }
            for slot, entry in sorted(slots.items())
        },
        "slo_status": "not_evaluated",
        "limitation": (
            "Só descreve os slots com journal baixado; ausência é lacuna de coleta. "
            "Falha por timeout não revela a duração real da resposta."
        ),
    }


def load_slo(path: Path) -> dict:
    slo = json.loads(path.read_text(encoding="utf-8"))
    external = slo.get("external", {})
    if (
        slo.get("schema_version") != 1
        or slo.get("status") not in {"proposed", "approved"}
        or not isinstance(external.get("minimum_primaries"), int)
        or external["minimum_primaries"] < 1
        or not all(0 < external.get(key, 0) < 1 for key in ("success_target", "duration_target"))
        or not 0 < external.get("duration_ms", 0) <= 60000
    ):
        raise ValueError("política de SLO inválida")
    return slo


def evaluate(result: dict, slo: dict) -> dict:
    """Compara a revisão com metas fixadas antes; só conclui com política aprovada e volume."""
    external = slo["external"]
    count = result["slots_with_primary"]
    durations = [
        entry["duration_ms"] for entry in result["slots"].values() if entry["outcome"] == "success"
    ]
    fast = sum(duration <= external["duration_ms"] for duration in durations)
    if external["pilot_id"] != result["pilot_id"]:
        status = "wrong_pilot"
    elif slo["status"] != "approved":
        status = "policy_not_approved"
    elif count < external["minimum_primaries"]:
        status = "insufficient_data"
    else:
        status = "ready"
    ready = status == "ready"
    success_rate = result["primary_successes"] / count if count else None
    # Falhas também consomem a meta de duração: o denominador são todas as principais.
    fast_rate = fast / count if count else None
    return {
        "status": status,
        "policy_status": slo["status"],
        "primaries": count,
        "minimum_primaries": external["minimum_primaries"],
        "success": {
            "target": external["success_target"],
            "observed": success_rate,
            "met": success_rate >= external["success_target"] if ready else None,
        },
        "duration": {
            "threshold_ms": external["duration_ms"],
            "target": external["duration_target"],
            "observed": fast_rate,
            "met": fast_rate >= external["duration_target"] if ready else None,
        },
        "scope": "primeira chamada de cada slot coletado; não é disponibilidade mensal",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["gate", "collect", "audit", "review"])
    parser.add_argument("--policy", type=Path, default=Path("monitoring/external-pilot.json"))
    parser.add_argument("--output", type=Path, default=Path("data/probe-pilot"))
    parser.add_argument("--artifacts", type=Path, help="diretório com os artefatos baixados")
    parser.add_argument("--slo", type=Path, help="política de metas para avaliar a revisão")
    args = parser.parse_args()
    policy, now = load_policy(args.policy), datetime.now(UTC)
    if args.command == "review":
        if args.artifacts is None:
            parser.error("review requer --artifacts")
        if args.output.exists():
            raise FileExistsError(args.output)
        result = review(policy, args.artifacts, now)
        if args.slo is not None:
            result["evaluation"] = evaluate(result, load_slo(args.slo))
            result["slo_status"] = result["evaluation"]["status"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(json.dumps({k: v for k, v in result.items() if k != "slots"}))
        evaluation = result.get("evaluation", {})
        violated = evaluation.get("status") == "ready" and not (
            evaluation["success"]["met"] and evaluation["duration"]["met"]
        )
        return 2 if violated else 0
    if args.command == "gate":
        print(
            json.dumps(
                gate(
                    policy,
                    now=now,
                    event=os.environ.get("GITHUB_EVENT_NAME", "manual"),
                    attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
                )
            )
        )
        return 0
    repository = os.environ["GITHUB_REPOSITORY"]
    if args.command == "audit":
        artifacts = pages(f"/repos/{repository}/actions/artifacts", "artifacts")
        result = audit(policy, artifacts, now)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        return 0
    run_id = int(os.environ["GITHUB_RUN_ID"])
    current = api(f"/repos/{repository}/actions/runs/{run_id}")
    runs = pages(
        f"/repos/{repository}/actions/workflows/external-probe.yml/runs?event=schedule",
        "workflow_runs",
    )
    slot = reserve_slot(policy, runs, current, datetime.now(UTC))
    if slot is None:
        print("Run sem slot elegível; nenhum pedido enviado")
        return 0
    outputs(slot=slot)
    result = collect(policy, args.output, slot)
    print(json.dumps(result))
    return 2 if result["primary_status"] == "failure" else 0


if __name__ == "__main__":
    raise SystemExit(main())
