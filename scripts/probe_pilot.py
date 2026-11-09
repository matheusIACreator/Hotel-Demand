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
        or policy["timeout_seconds"] != 30
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["gate", "collect", "audit"])
    parser.add_argument("--policy", type=Path, default=Path("monitoring/external-pilot.json"))
    parser.add_argument("--output", type=Path, default=Path("data/probe-pilot"))
    args = parser.parse_args()
    policy, now = load_policy(args.policy), datetime.now(UTC)
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
