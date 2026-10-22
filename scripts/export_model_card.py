"""Exporta, para a página Modelo do frontend, as métricas históricas de uma versão registada.

Lê parâmetros e métricas do run no MLflow e, com o dataset local, reconstrói os períodos da
divisão temporal. Nada é estimado: se uma fonte faltar, o script falha.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from mlflow import MlflowClient

from hotelml.config import HF_REPO_ID, TARGET, Settings
from hotelml.features import clean_training_data, time_split

ROOT = Path(__file__).resolve().parents[1]
METRICS = ["roc_auc", "pr_auc", "f1", "accuracy", "brier", "log_loss"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1")
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument(
        "--data", type=Path, default=ROOT / "data" / "raw" / "data" / "train-00000-of-00001.parquet"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "web" / "lib" / "data" / "model-card.json"
    )
    args = parser.parse_args()

    settings = Settings()
    client = MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)
    version = client.get_model_version(settings.model_name, args.version)
    run = client.get_run(version.run_id)
    params = run.data.params

    raw = pd.read_parquet(args.data)
    data = clean_training_data(raw)
    train, test, cutoff = time_split(data, args.test_fraction)
    if str(len(train)) != params["n_train"] or str(len(test)) != params["n_test"]:
        raise SystemExit("o dataset local não reproduz a divisão registada no run")
    if cutoff.date().isoformat() != params["test_cutoff"]:
        raise SystemExit("data de corte diferente da registada no run")

    card = {
        "source": {
            "description": "Run MLflow da versão registada e dataset local usado no treino.",
            "model_name": settings.model_name,
            "model_version": str(version.version),
            "run_id": version.run_id,
            "trained_at": datetime.fromtimestamp(run.info.start_time / 1000, UTC).isoformat(),
            "exported_at": datetime.now(UTC).date().isoformat(),
        },
        "estimator": params["model_type"],
        "dataset": {
            "name": HF_REPO_ID,
            "url": f"https://huggingface.co/datasets/{HF_REPO_ID}",
            "data_source": params["data_source"],
            "raw_rows": len(raw),
            "removed_rows": len(raw) - len(data),
            "train_rows": len(train),
            "test_rows": len(test),
            "train_start": train["arrival_date"].min().date().isoformat(),
            "train_end": train["arrival_date"].max().date().isoformat(),
            "test_start": test["arrival_date"].min().date().isoformat(),
            "test_end": test["arrival_date"].max().date().isoformat(),
            "test_cutoff": params["test_cutoff"],
            "train_cancel_rate": round(float(train[TARGET].mean()), 4),
            "test_cancel_rate": round(float(test[TARGET].mean()), 4),
        },
        "metrics": {name: run.data.metrics[f"test_{name}"] for name in METRICS},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(card, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"métricas da versão {version.version} exportadas para {args.output}")


if __name__ == "__main__":
    main()
