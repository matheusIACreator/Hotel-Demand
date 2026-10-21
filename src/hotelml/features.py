"""Limpeza, engenharia de features e pipeline sklearn.

Separação importante:
- `clean_training_data` filtra linhas e só roda no treino (não existe "linha inválida" em serving).
- `add_features` é stateless e vive DENTRO do pipeline, então o modelo registrado aceita
  diretamente o payload cru de uma requisição (`INPUT_COLUMNS`), sem divergência treino/serving.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from hotelml.config import (
    ADR_MAX,
    CATEGORICAL_MODEL,
    MONTH_TO_NUM,
    NUMERIC_MODEL,
)


def clean_training_data(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas inválidas e cria `arrival_date` (usada para o split temporal)."""
    out = df.copy()
    out["children"] = out["children"].fillna(0)
    guests = out["adults"] + out["children"] + out["babies"]
    out = out[(guests > 0) & (out["adr"] >= 0) & (out["adr"] < ADR_MAX)].copy()

    out["arrival_date"] = pd.to_datetime(
        {
            "year": out["arrival_date_year"],
            "month": out["arrival_date_month"].map(MONTH_TO_NUM),
            "day": out["arrival_date_day_of_month"],
        },
        errors="coerce",
    )
    out = out.dropna(subset=["arrival_date"])
    return out.reset_index(drop=True)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Features derivadas, sem estado. Seguro para treino e serving."""
    out = df.copy()
    out["children"] = out["children"].fillna(0)
    out["country"] = out["country"].fillna("UNK")
    out["total_nights"] = out["stays_in_weekend_nights"] + out["stays_in_week_nights"]
    out["total_guests"] = out["adults"] + out["children"] + out["babies"]
    out["has_agent"] = out["agent"].notna().astype(int)
    out["has_company"] = out["company"].notna().astype(int)
    out["arrival_month_num"] = out["arrival_date_month"].map(MONTH_TO_NUM)
    return out


def time_split(
    df: pd.DataFrame, test_fraction: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Split temporal: treina no passado, avalia no futuro (mais realista que split aleatório)."""
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction deve estar entre 0 e 1")
    ordered = df.sort_values("arrival_date", kind="stable").reset_index(drop=True)
    cut = int(len(ordered) * (1.0 - test_fraction))
    train, test = ordered.iloc[:cut], ordered.iloc[cut:]
    return train, test, pd.Timestamp(test["arrival_date"].iloc[0])


DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    "hgb": {"max_iter": 200, "learning_rate": 0.1, "random_state": 42},
    "logreg": {"max_iter": 1000, "C": 1.0},
}


def build_pipeline(model_type: str = "hgb", params: dict[str, Any] | None = None) -> Pipeline:
    """Monta o pipeline completo: features -> pré-processamento -> estimador."""
    if model_type not in DEFAULT_PARAMS:
        raise ValueError(f"model_type inválido: {model_type!r}. Use {sorted(DEFAULT_PARAMS)}")
    hyper = {**DEFAULT_PARAMS[model_type], **(params or {})}

    numeric_steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
    if model_type == "logreg":
        numeric_steps.append(("scale", StandardScaler()))

    preprocessor = ColumnTransformer(
        [
            ("num", Pipeline(numeric_steps), NUMERIC_MODEL),
            (
                "cat",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist", min_frequency=20, sparse_output=False
                ),
                CATEGORICAL_MODEL,
            ),
        ],
        remainder="drop",
    )
    estimator = (
        HistGradientBoostingClassifier(**hyper)
        if model_type == "hgb"
        else LogisticRegression(**hyper)
    )
    return Pipeline(
        [
            ("features", FunctionTransformer(add_features)),
            ("preprocess", preprocessor),
            ("model", estimator),
        ]
    )
