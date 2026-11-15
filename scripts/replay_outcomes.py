"""Replay histórico: desfechos exportados pela origem contra previsões do bundle, em pandas.

Verifica a cadeia adaptador de desfechos -> avaliação de qualidade no período de teste temporal.
As métricas obtidas pelos desfechos exportados têm de coincidir com as calculadas diretamente
pelo alvo do dataset. Não é um lote Spark monitorado nem tráfego de produção.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from hotelml.bundle import load_bundle
from hotelml.config import INPUT_COLUMNS, TARGET
from hotelml.data import load_raw
from hotelml.features import clean_training_data, time_split
from hotelml.metrics import evaluate
from hotelml.outcomes import SOURCE_COLUMNS, export_outcomes
from hotelml.quality import evaluate_outcomes

SHARED_METRICS = ("roc_auc", "pr_auc", "f1", "accuracy", "brier", "log_loss")


def replay(
    source: str,
    bundle: Path,
    output: Path,
    *,
    data_kind: str,
    test_fraction: float = 0.2,
    threshold: float = 0.5,
) -> dict:
    if output.exists():
        raise FileExistsError(output)
    raw = load_raw(source)
    _, test, cutoff = time_split(clean_training_data(raw), test_fraction)
    loaded = load_bundle(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))

    scored_at = datetime.now(UTC)
    probabilities = np.asarray(loaded.model.predict_proba(test[INPUT_COLUMNS]))[:, 1]
    # O dataset público não tem ID de negócio; estes IDs existem só dentro do replay.
    ids = [f"replay-{position}" for position in range(len(test))]
    batch_id = f"replay-{scored_at:%Y%m%dT%H%M%SZ}"
    scores = pd.DataFrame(
        {
            "booking_id": ids,
            "batch_id": batch_id,
            "model_name": loaded.name,
            "model_version": loaded.version,
            "threshold": threshold,
            "scored_at": scored_at,
            "cancellation_probability": probabilities,
            "is_canceled": probabilities >= threshold,
        }
    )
    run = {
        "schema_version": 1,
        "scores": "scores",
        "batch_id": batch_id,
        "rows": len(scores),
        "threshold": threshold,
        "model": manifest,
    }
    # A origem só disponibiliza os estados finais depois do scoring.
    available_at = (scored_at + timedelta(seconds=1)).isoformat()
    with tempfile.TemporaryDirectory(prefix="hotelml-replay-") as directory:
        export = Path(directory) / "source.parquet"
        test.assign(booking_id=ids)[list(SOURCE_COLUMNS)].to_parquet(export, index=False)
        outcomes_path = Path(directory) / "outcomes.parquet"
        summary = export_outcomes(export, outcomes_path, available_at=available_at)
        outcomes = pd.read_parquet(outcomes_path)
    quality = evaluate_outcomes(scores, outcomes, run, as_of=available_at, data_kind=data_kind)
    # Caminho independente: o alvo do dataset, sem passar pelo adaptador nem pelo join.
    direct = evaluate(loaded.model, test[INPUT_COLUMNS], test[TARGET], threshold)
    differences = {
        name: abs(quality["metrics"][name] - direct[name])
        for name in SHARED_METRICS
        if quality["metrics"][name] is not None
    }
    result = {
        "schema_version": 1,
        "scope": "historical_replay_pandas_scoring",
        "generated_at": datetime.now(UTC).isoformat(),
        "data_kind": data_kind,
        "source": source,
        "model": manifest,
        "test_cutoff": cutoff.date().isoformat(),
        "test_rows": len(test),
        "outcomes": {k: v for k, v in summary.items() if k != "provenance"},
        "quality_status": quality["status"],
        "outcome_coverage": quality["outcome_coverage"],
        "confusion_matrix": quality.get("confusion_matrix"),
        "metrics_from_exported_outcomes": quality["metrics"],
        "metrics_from_dataset_target": direct,
        "max_abs_difference": max(differences.values()) if differences else None,
        "consistent": (
            quality["status"] == "ready"
            and len(differences) == len(SHARED_METRICS)
            and max(differences.values()) < 1e-9
        ),
        "scores_sha256": hashlib.sha256(
            pd.util.hash_pandas_object(scores[["booking_id", "cancellation_probability"]])
            .to_numpy()
            .tobytes()
        ).hexdigest(),
        "limitation": (
            "Replay do período de teste do treino com scoring em pandas: confirma a cadeia de "
            "desfechos e qualidade, não mede o modelo em reservas novas nem valida o lote Spark."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="hf | synthetic | caminho .parquet/.csv")
    parser.add_argument("--bundle", type=Path, default=Path("model-bundle"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-kind", required=True, choices=["synthetic", "observed"])
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    result = replay(
        args.source,
        args.bundle,
        args.output,
        data_kind=args.data_kind,
        test_fraction=args.test_fraction,
    )
    print(json.dumps({k: result[k] for k in ("test_rows", "consistent", "max_abs_difference")}))
    return 0 if result["consistent"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
