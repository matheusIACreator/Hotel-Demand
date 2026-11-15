from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hotelml.cli import main
from hotelml.retraining import load_policy, retraining_signals

POLICY_PATH = Path(__file__).parents[1] / "monitoring/retraining-policy.json"
NOW = "2026-06-01T00:00:00Z"
TRAINED = "2026-03-01T00:00:00Z"


@pytest.fixture
def policy():
    return {**load_policy(POLICY_PATH), "status": "approved"}


def drift(day: int, detected: bool, column: str = "lead_time") -> dict:
    return {
        "generated_at": f"2026-05-{day:02d}T00:00:00+00:00",
        "drift_detected": detected,
        "columns": [
            {"column": column, "drift_detected": detected},
            {"column": "adr", "drift_detected": False},
        ],
    }


def quality(roc_auc: float | None, kind: str = "observed", status: str = "ready") -> dict:
    return {
        "data_kind": kind,
        "status": status,
        "outcome_coverage": 0.9,
        "metrics": {"roc_auc": roc_auc},
    }


def signals(policy, **kwargs):
    options = {"now": NOW, "trained_at": TRAINED, "drift_reports": []} | kwargs
    return retraining_signals(policy, **options)


def test_versioned_policy_is_only_a_proposal():
    # Limiares escolhidos sem dados de operação: o responsável aprova antes de valerem.
    assert load_policy(POLICY_PATH)["status"] == "proposed"


def test_no_signal_without_persistent_evidence(policy):
    result = signals(policy, drift_reports=[drift(1, True)])
    assert result["retrain_recommended"] is False and result["signals"] == []
    assert result["notes"][0].startswith("drift: 1 de 2")
    assert result["model_age_days"] == 92


def test_drift_must_persist_in_the_most_recent_reports(policy):
    # A ordem de entrada não importa: vale a data de cada relatório.
    persistent = signals(policy, drift_reports=[drift(9, True, "adr"), drift(2, True)])
    assert persistent["retrain_recommended"] is True
    assert persistent["signals"] == [
        {"kind": "drift", "reports": 2, "columns": ["adr", "lead_time"]}
    ]
    recovered = signals(policy, drift_reports=[drift(2, True), drift(5, True), drift(9, False)])
    assert recovered["retrain_recommended"] is False


def test_only_observed_ready_quality_below_the_floor_triggers(policy):
    low = signals(policy, quality=quality(0.74))
    assert low["signals"] == [
        {"kind": "quality", "roc_auc": 0.74, "minimum": 0.8, "outcome_coverage": 0.9}
    ]
    for report in (
        quality(0.86),
        quality(0.74, kind="synthetic"),
        quality(None, status="insufficient_data"),
        quality(None),
    ):
        result = signals(policy, quality=report)
        assert not result["retrain_recommended"], report


def test_model_age_is_a_scheduled_trigger(policy):
    assert not signals(policy, now="2026-08-28T00:00:00Z")["retrain_recommended"]
    old = signals(policy, now="2026-08-29T00:00:00Z")
    assert old["signals"] == [{"kind": "age", "days": 181, "maximum": 180}]
    with pytest.raises(ValueError, match="posterior"):
        signals(policy, now="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="fuso"):
        signals(policy, trained_at="2026-03-01")


def test_proposed_policy_shows_signals_without_recommending(policy):
    proposed = {**policy, "status": "proposed"}
    result = signals(proposed, quality=quality(0.5))
    assert result["status"] == "policy_not_approved"
    assert result["signals"] and result["retrain_recommended"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "active"),
        ("consecutive_drift_reports", 0),
        ("min_observed_roc_auc", 0.5),
        ("min_observed_roc_auc", 1),
        ("max_model_age_days", 0),
    ],
)
def test_invalid_policy_is_rejected(policy, tmp_path, field, value):
    invalid = copy.deepcopy(policy)
    invalid[field] = value
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        load_policy(path)


def test_cli_records_inputs_and_returns_2_only_when_recommended(policy, tmp_path, capsys):
    approved = tmp_path / "policy.json"
    approved.write_text(json.dumps(policy))
    reports = []
    for day in (3, 8):
        path = tmp_path / f"drift-{day}.json"
        path.write_text(json.dumps(drift(day, True)))
        reports += ["--drift", str(path)]
    quality_path = tmp_path / "quality.json"
    quality_path.write_text(json.dumps(quality(0.9)))
    common = ["retrain-check", "--trained-at", TRAINED, "--as-of", NOW, *reports]
    common += ["--quality", str(quality_path)]

    output = tmp_path / "decision.json"
    assert main([*common, "--policy", str(approved), "--output", str(output)]) == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["retrain_recommended"] is True and printed["signals"] == ["drift"]
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert len(saved["inputs_sha256"]) == 4
    with pytest.raises(FileExistsError):
        main([*common, "--policy", str(approved), "--output", str(output)])

    # A política versionada ainda é uma proposta: mesmos sinais, sem recomendação.
    assert main([*common, "--policy", str(POLICY_PATH), "--output", str(tmp_path / "p.json")]) == 0
    assert json.loads(capsys.readouterr().out)["retrain_recommended"] is None
