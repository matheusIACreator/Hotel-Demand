from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from hotelml.bundle import export_champion
from hotelml.train import train_and_register


@pytest.fixture
def replay():
    return runpy.run_path(str(Path(__file__).parents[1] / "scripts/replay_outcomes.py"))["replay"]


@pytest.fixture
def bundle(raw_df, settings, tmp_path):
    train_and_register(raw_df, settings, data_source="synthetic")
    path = tmp_path / "bundle"
    export_champion(settings, path)
    return path


def test_exported_outcomes_reproduce_metrics_from_the_target(replay, bundle, raw_df, tmp_path):
    source = tmp_path / "bookings.parquet"
    raw_df.to_parquet(source, index=False)
    output = tmp_path / "replay.json"
    result = replay(str(source), bundle, output, data_kind="synthetic")
    assert result["consistent"] and result["max_abs_difference"] < 1e-9
    assert result["scope"] == "historical_replay_pandas_scoring"
    assert result["outcome_coverage"] == 1
    assert result["outcomes"]["final_outcomes"] == result["test_rows"] > 30
    assert result["metrics_from_exported_outcomes"]["roc_auc"] == pytest.approx(
        result["metrics_from_dataset_target"]["roc_auc"]
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["model"]["model_version"] == "1" and "replay-0" not in json.dumps(saved)
    with pytest.raises(FileExistsError):
        replay(str(source), bundle, output, data_kind="synthetic")


def test_replay_flags_a_source_that_disagrees_with_the_target(replay, bundle, raw_df, tmp_path):
    # Uma origem que troca estados finais deixa de reproduzir as métricas do alvo.
    wrong = raw_df.copy()
    wrong["reservation_status"] = wrong.reservation_status.map(
        {"Canceled": "Check-Out", "Check-Out": "Canceled"}
    )
    source = tmp_path / "wrong.parquet"
    wrong.to_parquet(source, index=False)
    result = replay(str(source), bundle, tmp_path / "wrong.json", data_kind="synthetic")
    assert not result["consistent"]
    assert result["max_abs_difference"] > 0.1
