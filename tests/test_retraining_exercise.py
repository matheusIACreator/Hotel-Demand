from __future__ import annotations

import json
import runpy
from pathlib import Path

import mlflow
import pytest


def test_retraining_compares_future_holdout_and_exports_selected_model(tmp_path):
    exercise = runpy.run_path(str(Path(__file__).parents[1] / "scripts/exercise_retraining.py"))[
        "exercise"
    ]
    before = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    output = tmp_path / "exercise.json"
    result = exercise(output)
    assert result["historical_rows"] < result["train_rows"]
    assert result["train_rows"] + result["test_rows"] == result["retraining_rows"]
    assert result["train_end"] < result["test_start"] <= result["test_end"]
    assert not result["blocked_decision"]["promoted"]
    baseline = result["baseline"]["metrics_on_retraining_test"]["roc_auc"]
    candidate = result["candidate"]["metrics_on_retraining_test"]["roc_auc"]
    assert result["decision"]["champion_score"] == baseline
    assert result["decision"]["challenger_score"] == candidate
    assert result["decision"]["promoted"] == (candidate > baseline)
    assert (
        result["selected_version"]
        == result["candidate" if candidate > baseline else "baseline"]["version"]
    )
    assert result["previous_snapshot_preserved"]
    assert result["readiness_passed"] and result["prediction_passed"]
    assert len(result["dataset_sha256"]) == 64
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert (mlflow.get_tracking_uri(), mlflow.get_registry_uri()) == before
    with pytest.raises(FileExistsError):
        exercise(output)


def test_training_failure_restores_mlflow_context_without_success_report(tmp_path, monkeypatch):
    exercise = runpy.run_path(str(Path(__file__).parents[1] / "scripts/exercise_retraining.py"))[
        "exercise"
    ]
    before = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    temporary_roots = []

    def fail_training(raw, settings, **kwargs):
        temporary_roots.append(settings.artifact_root.parent)
        mlflow.set_tracking_uri(settings.tracking_uri)
        mlflow.set_registry_uri(settings.tracking_uri)
        raise RuntimeError("falha simulada de treino")

    monkeypatch.setitem(exercise.__globals__, "train_and_register", fail_training)
    output = tmp_path / "failure.json"
    with pytest.raises(RuntimeError, match="falha simulada"):
        exercise(output)
    assert (mlflow.get_tracking_uri(), mlflow.get_registry_uri()) == before
    assert not output.exists()
    assert temporary_roots and not temporary_roots[0].exists()


def test_active_mlflow_run_prevents_exercise(tmp_path, monkeypatch):
    exercise = runpy.run_path(str(Path(__file__).parents[1] / "scripts/exercise_retraining.py"))[
        "exercise"
    ]
    monkeypatch.setattr(mlflow, "active_run", lambda: object())
    with pytest.raises(RuntimeError, match="run MLflow ativo"):
        exercise(tmp_path / "active.json")
