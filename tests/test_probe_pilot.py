from __future__ import annotations

import copy
import json
import runpy
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def pilot():
    return runpy.run_path(str(Path(__file__).parents[1] / "scripts/probe_pilot.py"))


@pytest.fixture
def policy(pilot):
    return pilot["load_policy"](Path(__file__).parents[1] / "monitoring/external-pilot.json")


def test_window_has_336_slots_with_exclusive_end_and_no_manual_traffic(pilot, policy):
    start = pilot["timestamp"](policy["start"])
    end = pilot["timestamp"](policy["end"])
    assert pilot["slot_for"](policy, start - timedelta(seconds=1)) is None
    assert pilot["slot_for"](policy, start) == 0
    assert pilot["slot_for"](policy, end - timedelta(seconds=1)) == 335
    assert pilot["slot_for"](policy, end) is None
    gate = pilot["gate"]
    assert gate(policy, now=start, event="schedule", attempt=1)["active"]
    assert not gate(policy, now=start, event="workflow_dispatch", attempt=1)["active"]
    assert not gate(policy, now=start, event="schedule", attempt=2)["active"]
    assert not gate(policy, now=end, event="schedule", attempt=1)["active"]
    assert not gate(policy, now=end, event="schedule", attempt=1)["expired"]
    assert gate(policy, now=end + timedelta(hours=1), event="schedule", attempt=1)["expired"]


def test_first_created_run_owns_slot_and_delays_do_not_catch_up(pilot, policy):
    start = pilot["timestamp"](policy["start"])
    runs = [
        {"id": 10, "event": "schedule", "run_attempt": 1, "created_at": start.isoformat()},
        {
            "id": 11,
            "event": "schedule",
            "run_attempt": 1,
            "created_at": (start + timedelta(minutes=20)).isoformat(),
        },
    ]
    reserve = pilot["reserve_slot"]
    assert reserve(policy, runs, runs[0], start + timedelta(minutes=30)) == 0
    assert reserve(policy, runs, runs[1], start + timedelta(minutes=30)) is None
    assert reserve(policy, runs, runs[0], start + timedelta(hours=1)) is None
    retry = {**runs[0], "run_attempt": 2}
    assert reserve(policy, runs, retry, start) is None
    assert reserve(policy, [], runs[0], start) is None


def test_yesterday_slot_cannot_spend_today_request_budget(pilot, policy):
    start = pilot["timestamp"](policy["start"])
    # Último slot que começa no dia UTC do início; a sua hora termina já no dia seguinte.
    slot = 23 - start.hour
    created = start + timedelta(hours=slot)
    current = {"id": 10, "event": "schedule", "run_attempt": 1, "created_at": created.isoformat()}
    late = created.replace(hour=0, minute=1) + timedelta(days=1)
    assert created.date() != late.date()
    assert pilot["slot_for"](policy, late) == slot
    assert not pilot["slot_open"](policy, slot, late)
    assert pilot["reserve_slot"](policy, [current], current, late) is None
    assert pilot["slot_open"](policy, slot, created)


@pytest.mark.parametrize("failed,calls", [(0, 1), (1, 3)])
def test_diagnostics_never_change_primary_result(
    pilot, policy, tmp_path, monkeypatch, failed, calls
):
    from hotelml import probe

    start = pilot["timestamp"](policy["start"])

    class Clock(datetime):
        @staticmethod
        def now(_):
            return start

    monkeypatch.setitem(pilot["collect"].__globals__, "datetime", Clock)
    monkeypatch.setattr("time.sleep", lambda _: None)
    seen = []

    def fake_probe(url, output, **kwargs):
        seen.append((output.name, kwargs["count"]))
        # Diagnósticos podem recuperar: a falha principal precisa permanecer.
        failure = failed if len(seen) == 1 else 0
        return {"failed_attempts": failure, "completed_attempts": 1, "success_rate": 1 - failure}

    monkeypatch.setattr(probe, "run_probe", fake_probe)
    result = pilot["collect"](policy, tmp_path / "collect", 0)
    assert len(seen) == calls and all(count == 1 for _, count in seen)
    assert result["primary_status"] == ("failure" if failed else "success")
    assert result["primary_success_rate"] == 1 - failed
    assert result["diagnostic_attempts"] == calls - 1
    if failed:
        assert result["diagnostic_success_rate"] == 1


def test_expiration_blocks_probe_before_output_or_network(pilot, policy, tmp_path, monkeypatch):
    end = pilot["timestamp"](policy["end"])

    class Clock(datetime):
        @staticmethod
        def now(_):
            return end

    monkeypatch.setitem(pilot["collect"].__globals__, "datetime", Clock)
    with pytest.raises(RuntimeError, match="expirou"):
        pilot["collect"](policy, tmp_path / "collect", 0)
    assert not (tmp_path / "collect").exists()


def test_audit_distinguishes_service_failure_and_collection_gaps(pilot, policy):
    prefix = "probe-" + policy["pilot_id"]
    artifacts = [
        {"name": f"{prefix}-0-success", "expired": False},
        {"name": f"{prefix}-1-failure", "expired": False},
        {"name": f"{prefix}-2-incomplete", "expired": False},
        {"name": f"{prefix}-4-success", "expired": True},
        {"name": "audit-unrelated", "expired": False},
    ]
    now = pilot["timestamp"](policy["start"]) + timedelta(hours=5)
    result = pilot["audit"](policy, artifacts, now)
    assert result["expected_slots_so_far"] == 6
    assert result["counts"] == {
        "success": 1,
        "failure": 1,
        "incomplete": 1,
        "missing": 1,
        "pending": 2,
        "duplicate": 0,
    }
    assert result["primary_success_rate_observed"] == 0.5
    assert result["collection_coverage"] == pytest.approx(2 / 6)
    artifacts.append({"name": f"{prefix}-0-failure", "expired": False})
    result = pilot["audit"](policy, artifacts, now)
    assert result["counts"]["duplicate"] == 1
    assert result["counts"]["success"] == 0


def test_empty_audit_before_pilot_and_complete_final_window(pilot, policy):
    start, end = pilot["timestamp"](policy["start"]), pilot["timestamp"](policy["end"])
    before = pilot["audit"](policy, [], start - timedelta(seconds=1))
    assert before["expected_slots_so_far"] == 0
    assert before["primary_success_rate_observed"] is None
    final = pilot["audit"](policy, [], end + timedelta(hours=1))
    assert final["counts"]["missing"] == 336
    assert final["counts"]["pending"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("period_seconds", 60),
        ("diagnostic_attempts", 10),
        ("retention_days", 7),
        ("end", "2027-01-01T00:00:00Z"),
        ("timeout_seconds", 29),
        ("timeout_seconds", 61),
    ],
)
def test_policy_cannot_expand_approved_traffic_or_duration(pilot, policy, tmp_path, field, value):
    invalid = copy.deepcopy(policy)
    invalid[field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        pilot["load_policy"](path)


def test_timeout_covers_the_measured_cold_start(policy):
    # Arranques a frio de ~31 s foram medidos em 2026-11-15; um timeout menor censura a duração.
    assert policy["timeout_seconds"] == 60


def _artifact(root, name, primary, diagnostics=(), success_marker=True):
    base = root / name
    for folder, attempts in [("primary", [primary])] + [
        (f"diagnostic-{i}", [d]) for i, d in enumerate(diagnostics, 1)
    ]:
        (base / folder).mkdir(parents=True)
        (base / folder / "attempts.jsonl").write_text(
            "".join(json.dumps(a) + chr(10) for a in attempts), encoding="utf-8"
        )
        if success_marker:
            (base / folder / "_SUCCESS").touch()


def _attempt(started, seconds, outcome="success", status=200):
    start = datetime.fromisoformat(started)
    return {
        "sequence": 1,
        "started_at": start.isoformat(),
        "http_status": status,
        "outcome": outcome,
        "duration_ms": seconds * 1000,
        "finished_at": (start + timedelta(seconds=seconds)).isoformat(),
    }


def test_review_summarizes_durations_recovery_and_coverage(pilot, policy, tmp_path):
    prefix = "probe-" + policy["pilot_id"]
    start = pilot["timestamp"](policy["start"])
    first = start.isoformat()
    # Mesma forma do slot 21 do primeiro piloto: 504 aos ~21 s e recuperação no diagnóstico.
    _artifact(
        tmp_path,
        f"{prefix}-0-failure",
        _attempt(first, 20.9, "http_error", 504),
        [
            _attempt((start + timedelta(seconds=26)).isoformat(), 19.0),
            _attempt((start + timedelta(seconds=50)).isoformat(), 0.5),
        ],
    )
    _artifact(tmp_path, f"{prefix}-1-success", _attempt(first, 31.0))
    _artifact(tmp_path, f"{prefix}-3-success", _attempt(first, 0.4))
    # Sem marcador de conclusão e de outro piloto: não entram nas estatísticas.
    _artifact(tmp_path, f"{prefix}-4-success", _attempt(first, 1.0), success_marker=False)
    _artifact(tmp_path, "probe-outro-piloto-5-success", _attempt(first, 1.0))
    (tmp_path / "audit.json").write_text("{}")

    result = pilot["review"](policy, tmp_path, start + timedelta(hours=4, minutes=30))
    assert result["expected_slots_so_far"] == 5
    assert result["slots_with_primary"] == 3
    assert result["collection_coverage"] == pytest.approx(3 / 5)
    assert result["skipped_artifacts"] == [f"{prefix}-4-success"]
    assert result["primary_successes"] == 2 and result["primary_failures"] == 1
    assert result["primary_success_rate_observed"] == pytest.approx(2 / 3)
    assert result["primary_outcomes"] == {"http_error": 1, "success": 2}
    assert result["primary_http_statuses"] == {"200": 2, "504": 1}
    assert result["primary_success_duration_ms"]["max"] == 31000
    assert result["primary_failure_duration_ms"]["count"] == 1
    # Da primeira chamada ao fim do primeiro diagnóstico bem-sucedido: 26 s + 19 s.
    assert result["recovery_seconds"]["max"] == pytest.approx(45)
    assert result["slots"]["0"]["diagnostic_outcomes"] == ["success", "success"]
    assert result["slots"]["1"]["recovery_seconds"] is None
    assert result["slo_status"] == "not_evaluated"


def test_review_before_start_and_without_artifacts_has_no_rates(pilot, policy, tmp_path):
    start, end = pilot["timestamp"](policy["start"]), pilot["timestamp"](policy["end"])
    before = pilot["review"](policy, tmp_path, start - timedelta(seconds=1))
    assert before["expected_slots_so_far"] == 0
    assert before["collection_coverage"] is None
    assert before["primary_success_rate_observed"] is None
    assert before["primary_success_duration_ms"]["p95"] is None
    after = pilot["review"](policy, tmp_path, end + timedelta(days=1))
    assert after["expected_slots_so_far"] == 336
    assert after["collection_coverage"] == 0


def test_review_cli_never_overwrites_a_report(pilot, tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    output = tmp_path / "review.json"
    argv = ["probe_pilot.py", "review", "--artifacts", str(artifacts), "--output", str(output)]
    argv += ["--policy", str(Path(__file__).parents[1] / "monitoring/external-pilot.json")]
    monkeypatch.setattr("sys.argv", argv)
    assert pilot["main"]() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["slots_with_primary"] == 0
    with pytest.raises(FileExistsError):
        pilot["main"]()


@pytest.fixture
def slo(pilot):
    return pilot["load_slo"](Path(__file__).parents[1] / "monitoring/slo-policy.json")


def _review(pilot, policy, tmp_path, durations, failures=0):
    prefix = "probe-" + policy["pilot_id"]
    start = pilot["timestamp"](policy["start"])
    for slot, seconds in enumerate(durations):
        _artifact(tmp_path, f"{prefix}-{slot}-success", _attempt(start.isoformat(), seconds))
    for slot in range(len(durations), len(durations) + failures):
        _artifact(
            tmp_path, f"{prefix}-{slot}-failure", _attempt(start.isoformat(), 60, "timeout", None)
        )
    return pilot["review"](policy, tmp_path, start + timedelta(days=13))


def test_versioned_targets_belong_to_this_pilot_and_await_approval(policy, slo):
    assert slo["external"]["pilot_id"] == policy["pilot_id"]
    assert slo["external"]["duration_ms"] < policy["timeout_seconds"] * 1000
    # Metas propostas não podem gerar um veredito antes de o responsável as aprovar.
    assert slo["status"] == "proposed"


def test_proposed_policy_reports_rates_without_a_verdict(pilot, policy, slo, tmp_path):
    result = pilot["evaluate"](_review(pilot, policy, tmp_path, [31] * 40), slo)
    assert result["status"] == "policy_not_approved"
    assert result["success"]["observed"] == 1 and result["success"]["met"] is None
    assert result["duration"]["met"] is None


def test_approved_policy_needs_volume_and_counts_failures_as_slow(pilot, policy, slo, tmp_path):
    approved = {**slo, "status": "approved"}
    few = pilot["evaluate"](_review(pilot, policy, tmp_path / "few", [31] * 29), approved)
    assert few["status"] == "insufficient_data" and few["success"]["met"] is None

    # 36 rápidas, 2 lentas e 2 falhas em 40: sucesso 95%, mas só 90% dentro de 45 s.
    mixed = _review(pilot, policy, tmp_path / "mixed", [31] * 36 + [50] * 2, failures=2)
    result = pilot["evaluate"](mixed, approved)
    assert result["status"] == "ready"
    assert result["success"]["observed"] == pytest.approx(0.95) and result["success"]["met"]
    assert result["duration"]["observed"] == pytest.approx(0.9) and result["duration"]["met"]

    worse = _review(pilot, policy, tmp_path / "worse", [31] * 35 + [50] * 2, failures=3)
    result = pilot["evaluate"](worse, approved)
    assert not result["success"]["met"] and not result["duration"]["met"]


def test_targets_of_another_pilot_are_not_applied(pilot, policy, slo, tmp_path):
    other = {**slo, "status": "approved", "external": {**slo["external"], "pilot_id": "outro"}}
    result = pilot["evaluate"](_review(pilot, policy, tmp_path, [31] * 40), other)
    assert result["status"] == "wrong_pilot" and result["success"]["met"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"status": "validated"},
        {"external": {"minimum_primaries": 0}},
        {"external": {"success_target": 1}},
        {"external": {"duration_ms": 61000}},
    ],
)
def test_invalid_slo_policy_is_rejected(pilot, slo, tmp_path, change):
    invalid = copy.deepcopy(slo)
    for key, value in change.items():
        if isinstance(value, dict):
            invalid[key].update(value)
        else:
            invalid[key] = value
    path = tmp_path / "slo.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        pilot["load_slo"](path)


def test_review_cli_returns_2_only_for_a_violated_approved_target(
    pilot, policy, slo, tmp_path, monkeypatch
):
    artifacts = tmp_path / "artifacts"
    _review(pilot, policy, artifacts, [31] * 20, failures=20)
    approved = tmp_path / "slo.json"
    approved.write_text(json.dumps({**slo, "status": "approved"}))
    root = Path(__file__).parents[1]

    class Clock(datetime):
        @staticmethod
        def now(_):
            return pilot["timestamp"](policy["start"]) + timedelta(days=13)

    monkeypatch.setitem(pilot["main"].__globals__, "datetime", Clock)
    for name, path, code in (("a", approved, 2), ("b", root / "monitoring/slo-policy.json", 0)):
        argv = ["probe_pilot.py", "review", "--artifacts", str(artifacts)]
        argv += ["--output", str(tmp_path / f"{name}.json"), "--slo", str(path)]
        argv += ["--policy", str(root / "monitoring/external-pilot.json")]
        monkeypatch.setattr("sys.argv", argv)
        assert pilot["main"]() == code
    report = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert report["slo_status"] == "ready" and report["evaluation"]["success"]["met"] is False
