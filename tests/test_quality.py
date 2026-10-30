from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from hotelml.cli import main
from hotelml.quality import evaluate_outcomes, quality_report


@pytest.fixture
def cohort():
    probabilities = [0.1, 0.8, 0.6, 0.2]
    scores = pd.DataFrame(
        {
            "booking_id": [f"synthetic-{i}" for i in range(4)],
            "batch_id": "batch",
            "model_name": "hotel",
            "model_version": "1",
            "threshold": 0.5,
            "scored_at": pd.Timestamp("2026-01-01"),
            "cancellation_probability": probabilities,
            "is_canceled": np.array(probabilities) >= 0.5,
        }
    )
    outcomes = pd.DataFrame(
        {
            "booking_id": scores.booking_id,
            "is_canceled": [0, 1, 0, 1],
            "resolved_at": "2026-01-02T00:00:00Z",
        }
    )
    run = {
        "schema_version": 1,
        "scores": "scores",
        "batch_id": "batch",
        "rows": 4,
        "threshold": 0.5,
        "model": {"model_name": "hotel", "model_version": "1", "run_id": "run"},
    }
    return scores, outcomes, run


def evaluate(cohort, **kwargs):
    return evaluate_outcomes(
        *cohort, as_of="2026-01-03T00:00:00Z", data_kind="synthetic", minimum=2, **kwargs
    )


def test_known_metrics_and_no_individual_data(cohort):
    result = evaluate(cohort)
    assert result["outcome_coverage"] == 1
    assert result["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert result["metrics"]["accuracy"] == 0.5
    assert result["metrics"]["precision"] == 0.5
    assert result["metrics"]["brier"] == pytest.approx(0.2625)
    assert result["metrics"]["roc_auc"] == 0.75
    assert "synthetic-0" not in json.dumps(result)


def test_cutoff_partial_and_insufficient_coverage(cohort):
    scores, outcomes, run = cohort
    outcomes.loc[2:, "resolved_at"] = "2026-01-05T00:00:00Z"
    result = evaluate(cohort)
    assert result["matched_final_outcomes"] == 2
    assert result["pending_outcomes"] == 2
    assert result["outcome_coverage"] == 0.5
    result = evaluate_outcomes(
        scores, outcomes, run, as_of="2026-01-03T00:00:00Z", data_kind="synthetic", minimum=3
    )
    assert result["status"] == "insufficient_data"
    assert all(v is None for v in result["metrics"].values())
    empty = outcomes.iloc[:0]
    result = evaluate((scores, empty, run))
    assert result["matched_final_outcomes"] == 0
    before = evaluate_outcomes(
        scores, empty, run, as_of="2025-01-01T00:00:00Z", data_kind="synthetic", minimum=2
    )
    assert before["eligible_predictions"] == 0 and before["outcome_coverage"] is None


def test_one_class_keeps_undefined_metrics_null(cohort):
    scores, outcomes, _ = cohort
    outcomes["is_canceled"] = 0
    scores["cancellation_probability"] = 0.2
    scores["is_canceled"] = False
    result = evaluate(cohort)
    assert result["metrics"]["roc_auc"] is None
    assert result["metrics"]["pr_auc"] is None
    assert result["metrics"]["recall"] is None
    assert result["metrics"]["precision"] is None
    assert result["metrics"]["brier"] == pytest.approx(0.04)


@pytest.mark.parametrize(
    "column,value",
    [
        ("booking_id", "synthetic-1"),
        ("model_version", "other"),
        ("batch_id", "other"),
        ("threshold", 0.4),
        ("cancellation_probability", np.nan),
        ("cancellation_probability", 1.1),
        ("is_canceled", True),
        ("scored_at", "invalid"),
    ],
)
def test_corrupt_scores_rejected(cohort, column, value):
    if column == "scored_at":
        cohort[0][column] = cohort[0][column].astype(object)
    cohort[0].loc[0, column] = value
    with pytest.raises(ValueError):
        evaluate(cohort)


@pytest.mark.parametrize(
    "column,value",
    [
        ("booking_id", "synthetic-1"),
        ("is_canceled", 2),
        ("resolved_at", "2025-12-31T00:00:00Z"),
        ("resolved_at", "2026-01-02"),
    ],
)
def test_corrupt_outcomes_rejected(cohort, column, value):
    cohort[1].loc[0, column] = value
    with pytest.raises(ValueError):
        evaluate(cohort)


def test_unmatched_labels_do_not_change_metrics(cohort):
    scores, outcomes, run = cohort
    other = pd.DataFrame(
        {"booking_id": ["outside"], "is_canceled": [1], "resolved_at": ["2026-01-02T00:00:00Z"]}
    )
    result = evaluate((scores, pd.concat([outcomes, other], ignore_index=True), run))
    assert result["unmatched_outcome_ids"] == 1
    assert result["metrics"]["accuracy"] == 0.5


def test_file_report_requires_completed_batch_and_tracks_hashes(cohort, tmp_path, capsys):
    scores, outcomes, run = cohort
    batch = tmp_path / "batch"
    (batch / "scores").mkdir(parents=True)
    scores.to_parquet(batch / "scores/part.parquet", index=False)
    labels, output = tmp_path / "outcomes.parquet", tmp_path / "quality.json"
    outcomes.to_parquet(labels, index=False)
    (batch / "run.json").write_text(json.dumps(run))
    with pytest.raises(ValueError, match="incompleto"):
        quality_report(batch, labels, output, as_of="2026-01-03T00:00:00Z", data_kind="synthetic")
    (batch / "_SUCCESS").touch()
    assert (
        main(
            [
                "quality",
                "--batch",
                str(batch),
                "--outcomes",
                str(labels),
                "--output",
                str(output),
                "--as-of",
                "2026-01-03T00:00:00Z",
                "--data-kind",
                "synthetic",
                "--minimum-rows",
                "2",
            ]
        )
        == 0
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "ready"
    assert all(len(v) == 64 for v in result["provenance"].values())
    with pytest.raises(FileExistsError):
        quality_report(batch, labels, output, as_of="2026-01-03T00:00:00Z", data_kind="synthetic")
    assert "ready" in capsys.readouterr().out
