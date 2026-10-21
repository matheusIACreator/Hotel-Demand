from __future__ import annotations

import pandas as pd
import pytest

from hotelml.schema import DataValidationError, validate_raw


def test_valid_data_passes(raw_df: pd.DataFrame) -> None:
    validate_raw(raw_df)


def test_empty_dataset_fails() -> None:
    with pytest.raises(DataValidationError, match="vazio"):
        validate_raw(pd.DataFrame())


def test_missing_column_fails(raw_df: pd.DataFrame) -> None:
    with pytest.raises(DataValidationError, match="colunas em falta"):
        validate_raw(raw_df.drop(columns=["lead_time"]))


def test_invalid_target_fails(raw_df: pd.DataFrame) -> None:
    bad = raw_df.copy()
    bad.loc[0, "is_canceled"] = 2
    with pytest.raises(DataValidationError, match="is_canceled"):
        validate_raw(bad)


def test_negative_values_reported_together(raw_df: pd.DataFrame) -> None:
    bad = raw_df.copy()
    bad.loc[0, "lead_time"] = -5
    bad.loc[1, "adults"] = -1
    with pytest.raises(DataValidationError) as exc:
        validate_raw(bad)
    assert "lead_time" in str(exc.value) and "adults" in str(exc.value)


def test_invalid_month_fails(raw_df: pd.DataFrame) -> None:
    bad = raw_df.copy()
    bad.loc[0, "arrival_date_month"] = "Smarch"
    with pytest.raises(DataValidationError, match="meses"):
        validate_raw(bad)
