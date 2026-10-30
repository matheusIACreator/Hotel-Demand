"""Avaliação offline de um lote concluído contra desfechos finais conhecidos no corte."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)

METRICS = ("roc_auc", "pr_auc", "accuracy", "precision", "recall", "f1", "brier", "log_loss")


def _utc(value: Any) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError
        return stamp.tz_convert("UTC")
    except (ValueError, TypeError):
        raise ValueError("data de desfecho/corte deve ser válida e incluir fuso horário") from None


def _ids(frame: pd.DataFrame) -> None:
    if not frame.columns.is_unique:
        raise ValueError("colunas duplicadas")
    if (
        "booking_id" not in frame
        or not frame.booking_id.map(lambda v: isinstance(v, str) and bool(v.strip())).all()
        or frame.booking_id.duplicated().any()
    ):
        raise ValueError("IDs ausentes, inválidos ou duplicados")


def evaluate_outcomes(
    scores: pd.DataFrame,
    outcomes: pd.DataFrame,
    run: dict,
    *,
    as_of: str,
    data_kind: str,
    minimum: int = 30,
) -> dict[str, Any]:
    cutoff = _utc(as_of)
    if minimum < 2 or data_kind not in {"synthetic", "observed"}:
        raise ValueError("parâmetros de avaliação inválidos")
    model = run.get("model", {})
    if not all(
        isinstance(model.get(k), str) and model[k]
        for k in ("model_name", "model_version", "run_id")
    ):
        raise ValueError("identidade do modelo incompleta")
    required = {
        "booking_id",
        "batch_id",
        "model_name",
        "model_version",
        "threshold",
        "scored_at",
        "cancellation_probability",
        "is_canceled",
    }
    if not required <= set(scores) or not {"booking_id", "is_canceled", "resolved_at"} <= set(
        outcomes
    ):
        raise ValueError("colunas obrigatórias ausentes")
    _ids(scores)
    _ids(outcomes)
    if scores.empty or len(scores) != run.get("rows"):
        raise ValueError("lote vazio ou contagem divergente")
    for field, expected in (
        ("batch_id", run.get("batch_id")),
        ("model_name", model["model_name"]),
        ("model_version", model["model_version"]),
        ("threshold", run.get("threshold")),
    ):
        if expected is None or not scores[field].eq(expected).all():
            raise ValueError("identidade ou limiar divergente no lote")
    threshold = float(run["threshold"])
    proba = scores.cancellation_probability
    if (
        not np.isfinite(threshold)
        or not 0 <= threshold <= 1
        or not pd.api.types.is_numeric_dtype(proba)
        or not np.isfinite(proba).all()
        or not proba.between(0, 1).all()
    ):
        raise ValueError("probabilidades ou limiar inválidos")
    for frame in (scores, outcomes):
        if not frame.is_canceled.map(
            lambda v: isinstance(v, (bool, int, np.integer)) and v in (0, 1)
        ).all():
            raise ValueError("desfecho/decisão deve ser binário e não nulo")
    if not scores.is_canceled.eq(proba >= threshold).all():
        raise ValueError("decisão incompatível com probabilidade e limiar")
    scores = scores.copy()
    outcomes = outcomes.copy()
    # Spark escreve TimestampType sem fuso; o contrato do scoring define UTC.
    scores["scored_at"] = pd.to_datetime(scores.scored_at, utc=True, errors="coerce")
    if scores.scored_at.isna().any():
        raise ValueError("horário de scoring inválido")
    outcomes["resolved_at"] = pd.to_datetime(outcomes.resolved_at.map(_utc), utc=True)
    joined = scores.merge(
        outcomes, on="booking_id", how="inner", suffixes=("_pred", "_true"), validate="one_to_one"
    )
    if (joined.resolved_at < joined.scored_at).any():
        raise ValueError("desfecho anterior ao scoring; revise a relação temporal")
    eligible = scores.scored_at <= cutoff
    matched = joined[(joined.scored_at <= cutoff) & (joined.resolved_at <= cutoff)]
    count = len(matched)
    eligible_rows = int(eligible.sum())
    result: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_kind": data_kind,
        "as_of": cutoff.isoformat(),
        "batch_id": run["batch_id"],
        "model": model,
        "threshold": threshold,
        "batch_rows": len(scores),
        "eligible_predictions": eligible_rows,
        "matched_final_outcomes": count,
        "pending_outcomes": eligible_rows - count,
        "outcome_coverage": count / eligible_rows if eligible_rows else None,
        "unmatched_outcome_ids": int((~outcomes.booking_id.isin(scores.booking_id)).sum()),
        "minimum_rows": minimum,
        "status": "ready" if count >= minimum else "insufficient_data",
        "metrics": dict.fromkeys(METRICS),
        "interpretation": (
            "Métricas somente dos desfechos finais conhecidos no corte; "
            "cobertura parcial pode enviesar resultados."
        ),
    }
    if count < minimum:
        return result
    y = matched.is_canceled_true.to_numpy(dtype=int)
    prediction = matched.is_canceled_pred.to_numpy(dtype=int)
    probabilities = matched.cancellation_probability.to_numpy(dtype=float)
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(y, prediction, labels=[0, 1]).ravel())
    result["confusion_matrix"] = {"tn": tn, "fp": fp, "fn": fn, "tp": tp}
    result["class_counts"] = {"not_canceled": int((y == 0).sum()), "canceled": int(y.sum())}
    metrics = {
        "roc_auc": float(roc_auc_score(y, probabilities)) if len(np.unique(y)) == 2 else None,
        "pr_auc": float(average_precision_score(y, probabilities))
        if len(np.unique(y)) == 2
        else None,
        "accuracy": float(accuracy_score(y, prediction)),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "brier": float(brier_score_loss(y, probabilities)),
        "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
    }
    result["metrics"] = metrics
    return result


def quality_report(
    batch: Path,
    outcomes: Path,
    output: Path,
    *,
    as_of: str,
    data_kind: str,
    minimum: int = 30,
) -> dict:
    if output.exists():
        raise FileExistsError(output)
    if not (batch / "_SUCCESS").is_file():
        raise ValueError("lote monitorado incompleto")
    run_bytes = (batch / "run.json").read_bytes()
    run = json.loads(run_bytes)
    if run.get("schema_version") != 1 or run.get("scores") != "scores":
        raise ValueError("formato de lote não suportado")
    chunks = []
    digest = hashlib.sha256()
    for path in sorted((batch / "scores").rglob("*.parquet")):
        data = path.read_bytes()
        digest.update(path.relative_to(batch).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(data).digest())
        chunks.append(pd.read_parquet(io.BytesIO(data)))
    if not chunks:
        raise ValueError("previsões ausentes")
    outcome_bytes = outcomes.read_bytes()
    result = evaluate_outcomes(
        pd.concat(chunks, ignore_index=True),
        pd.read_parquet(io.BytesIO(outcome_bytes)),
        run,
        as_of=as_of,
        data_kind=data_kind,
        minimum=minimum,
    )
    result["provenance"] = {
        "run_sha256": hashlib.sha256(run_bytes).hexdigest(),
        "scores_sha256": digest.hexdigest(),
        "outcomes_sha256": hashlib.sha256(outcome_bytes).hexdigest(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result
