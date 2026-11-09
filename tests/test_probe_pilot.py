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
    ],
)
def test_policy_cannot_expand_approved_traffic_or_duration(pilot, policy, tmp_path, field, value):
    invalid = copy.deepcopy(policy)
    invalid[field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        pilot["load_policy"](path)
