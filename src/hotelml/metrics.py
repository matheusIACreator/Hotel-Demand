"""Métricas de avaliação de classificação binária."""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline


def evaluate(
    model: Pipeline, x: pd.DataFrame, y: pd.Series, threshold: float = 0.5
) -> dict[str, float]:
    """Calcula as métricas do modelo num conjunto (x, y)."""
    proba = model.predict_proba(x)[:, 1]
    pred = (proba >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y, proba)),
        "pr_auc": float(average_precision_score(y, proba)),
        "f1": float(f1_score(y, pred)),
        "accuracy": float(accuracy_score(y, pred)),
        "brier": float(brier_score_loss(y, proba)),
        "log_loss": float(log_loss(y, proba)),
    }
