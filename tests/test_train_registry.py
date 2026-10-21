from __future__ import annotations

import mlflow.sklearn
import pandas as pd
import pytest
from mlflow import MlflowClient

from hotelml import registry
from hotelml.config import INPUT_COLUMNS, Settings
from hotelml.train import train_and_register


def _client(settings: Settings) -> MlflowClient:
    return MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)


def test_first_model_becomes_champion(raw_df: pd.DataFrame, settings: Settings) -> None:
    result = train_and_register(raw_df, settings, data_source="synthetic")

    assert result.metrics["roc_auc"] > 0.65  # o sinal sintético é aprendível
    assert result.decision is not None and result.decision.promoted
    client = _client(settings)
    assert (
        registry.get_version(client, settings.model_name, registry.CHAMPION) == result.model_version
    )
    assert (
        registry.get_version(client, settings.model_name, registry.CHALLENGER)
        == result.model_version
    )


def test_registered_model_serves_raw_payload(raw_df: pd.DataFrame, settings: Settings) -> None:
    train_and_register(raw_df, settings)
    model = mlflow.sklearn.load_model(f"models:/{settings.model_name}@{registry.CHAMPION}")
    proba = model.predict_proba(raw_df[INPUT_COLUMNS].head(10))
    assert proba.shape == (10, 2)


def test_training_logs_reference_artifact_and_metrics(
    raw_df: pd.DataFrame, settings: Settings
) -> None:
    result = train_and_register(raw_df, settings)
    client = _client(settings)
    run = client.get_run(result.run_id)
    assert "test_roc_auc" in run.data.metrics
    assert run.data.params["model_type"] == "hgb"
    artifacts = [a.path for a in client.list_artifacts(result.run_id, "reference")]
    assert "reference/reference.parquet" in artifacts


def test_worse_challenger_is_not_promoted(raw_df: pd.DataFrame, settings: Settings) -> None:
    first = train_and_register(raw_df, settings, model_type="hgb")
    # min_delta=1.0 torna a promoção impossível: roc_auc nunca melhora mais que 1.
    second = train_and_register(raw_df, settings, model_type="logreg", min_delta=1.0)

    assert second.decision is not None and not second.decision.promoted
    client = _client(settings)
    assert (
        registry.get_version(client, settings.model_name, registry.CHAMPION) == first.model_version
    )
    assert (
        registry.get_version(client, settings.model_name, registry.CHALLENGER)
        == second.model_version
    )


def test_better_challenger_is_promoted_and_rollback_restores(
    raw_df: pd.DataFrame, settings: Settings
) -> None:
    first = train_and_register(raw_df, settings, model_type="logreg")
    second = train_and_register(raw_df, settings, model_type="hgb", min_delta=-1.0)
    client = _client(settings)

    assert second.decision is not None and second.decision.promoted
    assert (
        registry.get_version(client, settings.model_name, registry.CHAMPION) == second.model_version
    )
    assert (
        registry.get_version(client, settings.model_name, registry.PREVIOUS) == first.model_version
    )

    restored = registry.rollback(client, settings.model_name)
    assert restored == first.model_version
    assert (
        registry.get_version(client, settings.model_name, registry.CHAMPION) == first.model_version
    )


def test_rollback_without_history_fails(raw_df: pd.DataFrame, settings: Settings) -> None:
    train_and_register(raw_df, settings)
    with pytest.raises(registry.RollbackError):
        registry.rollback(_client(settings), settings.model_name)


def test_invalid_data_is_rejected_before_training(raw_df: pd.DataFrame, settings: Settings) -> None:
    from hotelml.schema import DataValidationError

    with pytest.raises(DataValidationError):
        train_and_register(raw_df.drop(columns=["adr"]), settings)
