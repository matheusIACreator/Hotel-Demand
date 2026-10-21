from __future__ import annotations

import pandas as pd
import pytest

from hotelml.config import INPUT_COLUMNS, LEAKAGE_COLUMNS, TARGET
from hotelml.features import add_features, build_pipeline, clean_training_data, time_split
from hotelml.synthetic import make_synthetic


def test_synthetic_is_deterministic() -> None:
    pd.testing.assert_frame_equal(make_synthetic(200, seed=7), make_synthetic(200, seed=7))


def test_no_leakage_column_in_model_input() -> None:
    assert not set(LEAKAGE_COLUMNS) & set(INPUT_COLUMNS)
    assert TARGET not in INPUT_COLUMNS


def test_clean_drops_invalid_rows(raw_df: pd.DataFrame) -> None:
    dirty = raw_df.copy()
    dirty.loc[0, ["adults", "children", "babies"]] = [0, 0, 0]
    dirty.loc[1, "adr"] = 5400.0
    dirty.loc[2, "adr"] = -6.38
    cleaned = clean_training_data(dirty)
    assert len(cleaned) == len(dirty) - 3
    assert "arrival_date" in cleaned.columns
    assert cleaned["arrival_date"].notna().all()


def test_add_features_is_pure_and_correct(raw_df: pd.DataFrame) -> None:
    sample = raw_df[INPUT_COLUMNS].head(50)
    before = sample.copy()
    out = add_features(sample)
    pd.testing.assert_frame_equal(sample, before)  # não altera a entrada
    assert (
        out["total_nights"] == sample["stays_in_weekend_nights"] + sample["stays_in_week_nights"]
    ).all()
    assert out["country"].notna().all()
    assert set(out["has_agent"].unique()) <= {0, 1}


def test_time_split_has_no_overlap(raw_df: pd.DataFrame) -> None:
    data = clean_training_data(raw_df)
    train, test, cutoff = time_split(data, 0.25)
    assert train["arrival_date"].max() <= test["arrival_date"].min()
    assert test["arrival_date"].min() == cutoff
    assert abs(len(test) / len(data) - 0.25) < 0.01


def test_time_split_rejects_bad_fraction(raw_df: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        time_split(clean_training_data(raw_df), 1.5)


@pytest.mark.parametrize("model_type", ["hgb", "logreg"])
def test_pipeline_accepts_raw_payload_and_returns_probabilities(
    raw_df: pd.DataFrame, model_type: str
) -> None:
    data = clean_training_data(raw_df)
    pipe = build_pipeline(model_type).fit(data[INPUT_COLUMNS], data[TARGET])
    proba = pipe.predict_proba(data[INPUT_COLUMNS].head(20))
    assert proba.shape == (20, 2)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_pipeline_handles_unseen_category(raw_df: pd.DataFrame) -> None:
    data = clean_training_data(raw_df)
    pipe = build_pipeline("hgb").fit(data[INPUT_COLUMNS], data[TARGET])
    row = data[INPUT_COLUMNS].head(1).copy()
    row["country"] = "ZZZ"
    assert pipe.predict_proba(row).shape == (1, 2)


def test_invalid_model_type_rejected() -> None:
    with pytest.raises(ValueError, match="model_type"):
        build_pipeline("xgboost")
