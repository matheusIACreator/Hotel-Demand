from __future__ import annotations

import json
import runpy
from pathlib import Path

import mlflow
import pytest


def test_isolated_rollback_restores_bundle_and_predictions(tmp_path):
    exercise = runpy.run_path(str(Path(__file__).parents[1] / "scripts/exercise_rollback.py"))[
        "exercise"
    ]
    before = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    output = tmp_path / "exercise.json"
    result = exercise(output)
    assert result["baseline_version"] != result["candidate_version"]
    assert result["restored_version"] == result["baseline_version"]
    assert result["predictions_restored_exactly"]
    assert result["alias_change_kept_running_snapshot"]
    assert result["bundle_sha256"]["baseline"] == result["bundle_sha256"]["restored"]
    assert json.loads(output.read_text(encoding="utf-8")) == result
    assert (mlflow.get_tracking_uri(), mlflow.get_registry_uri()) == before
    with pytest.raises(FileExistsError):
        exercise(output)
