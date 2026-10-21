"""Treino com rastreamento no MLflow, registro de modelo e promoção champion/challenger."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature

from hotelml import registry
from hotelml.config import INPUT_COLUMNS, SKOPS_TRUSTED_TYPES, TARGET, Settings
from hotelml.features import build_pipeline, clean_training_data, time_split
from hotelml.metrics import evaluate
from hotelml.schema import validate_raw

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainResult:
    run_id: str
    model_version: str
    metrics: dict[str, float]
    decision: registry.PromotionDecision | None


def _get_or_create_experiment(client: MlflowClient, settings: Settings) -> str:
    experiment = client.get_experiment_by_name(settings.experiment_name)
    if experiment is not None:
        return str(experiment.experiment_id)
    settings.artifact_root.mkdir(parents=True, exist_ok=True)
    return str(
        client.create_experiment(
            settings.experiment_name, artifact_location=settings.artifact_root.resolve().as_uri()
        )
    )


def train_and_register(
    raw: pd.DataFrame,
    settings: Settings,
    model_type: str = "hgb",
    params: dict[str, Any] | None = None,
    test_fraction: float = 0.2,
    data_source: str = "unknown",
    promote: bool = True,
    min_delta: float = 0.0,
) -> TrainResult:
    """Valida, treina, avalia no futuro, registra o modelo e (opcionalmente) tenta promovê-lo."""
    validate_raw(raw)
    data = clean_training_data(raw)
    train_df, test_df, cutoff = time_split(data, test_fraction)

    x_train, y_train = train_df[INPUT_COLUMNS], train_df[TARGET]
    x_test, y_test = test_df[INPUT_COLUMNS], test_df[TARGET]

    mlflow.set_tracking_uri(settings.tracking_uri)
    mlflow.set_registry_uri(settings.tracking_uri)
    client = MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)
    experiment_id = _get_or_create_experiment(client, settings)

    pipeline = build_pipeline(model_type, params)

    with mlflow.start_run(experiment_id=experiment_id, run_name=f"{model_type}") as run:
        mlflow.log_params(
            {
                "model_type": model_type,
                "n_train": len(train_df),
                "n_test": len(test_df),
                "test_cutoff": cutoff.date().isoformat(),
                "data_source": data_source,
                **{f"hp_{k}": v for k, v in (params or {}).items()},
            }
        )

        pipeline.fit(x_train, y_train)
        metrics = evaluate(pipeline, x_test, y_test)
        mlflow.log_metrics({f"test_{k}": v for k, v in metrics.items()})

        # Amostra de referência: base para detecção de drift na fase de monitoramento.
        with tempfile.TemporaryDirectory() as tmp:
            reference = x_train.sample(min(5000, len(x_train)), random_state=0)
            ref_path = Path(tmp) / "reference.parquet"
            reference.to_parquet(ref_path)
            mlflow.log_artifact(str(ref_path), artifact_path="reference")

        sample = x_train.head(100)
        info = mlflow.sklearn.log_model(
            pipeline,
            name="model",
            signature=infer_signature(sample, pipeline.predict(sample)),
            input_example=x_train.head(5),
            registered_model_name=settings.model_name,
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
        )
        version = str(info.registered_model_version)
        run_id = run.info.run_id

    registry.set_challenger(client, settings.model_name, version)
    decision = None
    if promote:
        decision = registry.promote_if_better(
            client,
            settings.model_name,
            version,
            metrics["roc_auc"],
            x_test,
            y_test,
            min_delta=min_delta,
        )
        log.info("promoção: %s", decision.reason)

    return TrainResult(run_id=run_id, model_version=version, metrics=metrics, decision=decision)
