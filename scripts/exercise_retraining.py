"""Exercício de retreino temporal em registry temporário, somente com dados sintéticos."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from mlflow import MlflowClient

from hotelml import registry
from hotelml.api import create_app
from hotelml.bundle import export_champion, load_bundle
from hotelml.config import INPUT_COLUMNS, TARGET, Settings
from hotelml.features import clean_training_data, time_split
from hotelml.metrics import evaluate
from hotelml.synthetic import make_synthetic
from hotelml.train import train_and_register


def _close_database(uri: str) -> None:
    from mlflow.store.model_registry.sqlalchemy_store import SqlAlchemyStore as RegistryStore
    from mlflow.store.tracking.sqlalchemy_store import SqlAlchemyStore as TrackingStore

    for store in (RegistryStore, TrackingStore):
        engine = store._engine_map.get(uri)
        if engine is not None:
            engine.dispose()


def _require(condition: bool) -> None:
    if not condition:
        raise RuntimeError("verificação de retreino falhou")


def exercise(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    if mlflow.active_run() is not None:
        raise RuntimeError("encerre o run MLflow ativo antes do exercício")
    previous_tracking, previous_registry = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    try:
        with (
            tempfile.TemporaryDirectory(prefix="hotelml-retraining-") as directory,
            ExitStack() as cleanup,
        ):
            root = Path(directory)
            settings = Settings(
                tracking_uri=f"sqlite:///{root / 'mlflow.db'}",
                artifact_root=root / "artifacts",
                experiment_name="retraining-exercise",
                model_name="retraining-exercise",
                data_dir=root / "data",
            )
            cleanup.callback(_close_database, settings.tracking_uri)
            raw = make_synthetic(800, seed=42)
            # Datas únicas tornam explícita a separação entre treino e teste do ensaio.
            dates = pd.date_range("2015-01-01", periods=len(raw))
            raw["arrival_date_year"] = dates.year
            raw["arrival_date_month"] = dates.month_name()
            raw["arrival_date_day_of_month"] = dates.day
            raw["arrival_date_week_number"] = dates.isocalendar().week.to_numpy(dtype=int)
            raw["reservation_status_date"] = dates.strftime("%Y-%m-%d")
            source = io.BytesIO()
            raw.to_parquet(source, index=False)
            historical = raw.iloc[:300]
            baseline = train_and_register(
                historical,
                settings,
                model_type="logreg",
                params={"C": 0.0001},
                data_source="synthetic_retraining_exercise",
            )
            export_champion(settings, root / "baseline")
            candidate = train_and_register(
                raw,
                settings,
                model_type="logreg",
                data_source="synthetic_retraining_exercise",
                promote=False,
            )
            client = MlflowClient(
                tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri
            )
            _require(candidate.decision is None)
            _require(
                registry.get_version(client, settings.model_name, registry.CHAMPION)
                == baseline.model_version
            )
            train, test, cutoff = time_split(clean_training_data(raw))
            _require(train.arrival_date.max() < test.arrival_date.min())
            _require(clean_training_data(historical).arrival_date.max() < cutoff)
            x_test, y_test = test[INPUT_COLUMNS], test[TARGET]
            old_bundle = load_bundle(root / "baseline")
            baseline_metrics = evaluate(old_bundle.model, x_test, y_test)
            # Um ganho superior a 1 em ROC AUC é impossível: ensaia o bloqueio da promoção.
            rejected = registry.promote_if_better(
                client,
                settings.model_name,
                candidate.model_version,
                candidate.metrics["roc_auc"],
                x_test,
                y_test,
                min_delta=1.0,
            )
            _require(not rejected.promoted)
            _require(
                registry.get_version(client, settings.model_name, registry.CHAMPION)
                == baseline.model_version
            )
            # A segunda decisão usa a política normal, sem forçar melhoria.
            decision = registry.promote_if_better(
                client,
                settings.model_name,
                candidate.model_version,
                candidate.metrics["roc_auc"],
                x_test,
                y_test,
            )
            _require(decision.champion_score == baseline_metrics["roc_auc"])
            _require(
                decision.promoted == (candidate.metrics["roc_auc"] > baseline_metrics["roc_auc"])
            )
            expected = candidate.model_version if decision.promoted else baseline.model_version
            manifest = export_champion(settings, root / "selected")
            _require(manifest["model_version"] == expected)
            if decision.promoted:
                _require(
                    registry.get_version(client, settings.model_name, registry.PREVIOUS)
                    == baseline.model_version
                )
            # O snapshot anterior permanece igual após a decisão no registry.
            np.testing.assert_array_equal(
                old_bundle.model.predict_proba(x_test),
                load_bundle(root / "baseline").model.predict_proba(x_test),
            )
            payload = {"bookings": json.loads(x_test.head(3).to_json(orient="records"))}
            with TestClient(create_app(lambda: load_bundle(root / "selected"))) as api:
                _require(api.get("/health/ready").json()["model_version"] == expected)
                response = api.post("/predict", json=payload)
                _require(response.status_code == 200)
                _require(response.json()["model_version"] == expected)
            result = {
                "schema_version": 1,
                "generated_at": datetime.now(UTC).isoformat(),
                "scope": "synthetic_local_temporary_registry",
                "trigger": "manual_exercise",
                "dataset_sha256": hashlib.sha256(source.getvalue()).hexdigest(),
                "historical_rows": len(historical),
                "retraining_rows": len(raw),
                "train_rows": len(train),
                "test_rows": len(test),
                "train_end": train.arrival_date.max().isoformat(),
                "test_start": cutoff.isoformat(),
                "test_end": test.arrival_date.max().isoformat(),
                "baseline": {
                    "version": baseline.model_version,
                    "run_id": baseline.run_id,
                    "metrics_on_retraining_test": baseline_metrics,
                },
                "candidate": {
                    "version": candidate.model_version,
                    "run_id": candidate.run_id,
                    "metrics_on_retraining_test": candidate.metrics,
                },
                "blocked_decision": asdict(rejected),
                "decision": asdict(decision),
                "selected_version": expected,
                "previous_snapshot_preserved": True,
                "readiness_passed": True,
                "prediction_passed": True,
                "limitation": (
                    "Ensaio sintético manual; não comprova melhoria em produção. "
                    "Registry, dados e bundles temporários são removidos ao terminar."
                ),
            }
    finally:
        mlflow.set_tracking_uri(previous_tracking)
        mlflow.set_registry_uri(previous_registry)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.output), ensure_ascii=True))


if __name__ == "__main__":
    main()
