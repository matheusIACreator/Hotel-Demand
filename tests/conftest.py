from __future__ import annotations

import pandas as pd
import pytest

from hotelml.config import Settings
from hotelml.synthetic import make_synthetic


@pytest.fixture(scope="session")
def raw_df() -> pd.DataFrame:
    return make_synthetic(n=4000, seed=1)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        tracking_uri=f"sqlite:///{tmp_path / 'mlflow.db'}",
        artifact_root=tmp_path / "artifacts",
        experiment_name="test-exp",
        model_name="test-model",
        data_dir=tmp_path / "raw",
    )
