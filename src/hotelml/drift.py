"""Comparação offline de distribuições; não estima qualidade nem decide retreino."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hotelml.api import Booking
from hotelml.config import CATEGORICAL_MODEL, INPUT_COLUMNS

CATEGORICAL = {*CATEGORICAL_MODEL, "arrival_date_month"}


def _validate(frame: pd.DataFrame, minimum: int) -> pd.DataFrame:
    if not frame.columns.is_unique or set(INPUT_COLUMNS) - set(frame.columns):
        raise ValueError("colunas obrigatórias ausentes ou duplicadas")
    if len(frame) < minimum:
        raise ValueError(f"amostra insuficiente: mínimo de {minimum} reservas")
    selected = frame[INPUT_COLUMNS].astype(object).where(frame[INPUT_COLUMNS].notna(), None)
    for index, row in enumerate(selected.to_dict(orient="records")):
        try:
            Booking.model_validate(row)
        except ValueError:
            # Não incluir valores da reserva no diagnóstico.
            raise ValueError(f"reserva inválida na posição {index}") from None
    return selected


def compare(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    minimum: int = 200,
    psi_threshold: float = 0.2,
    tv_threshold: float = 0.1,
) -> dict[str, Any]:
    """PSI por bins da referência e distância de variação total para categorias."""
    if minimum < 2 or not np.isfinite([psi_threshold, tv_threshold]).all():
        raise ValueError("parâmetros inválidos")
    if psi_threshold <= 0 or not 0 < tv_threshold <= 1:
        raise ValueError("limiares inválidos")
    reference, current = _validate(reference, minimum), _validate(current, minimum)
    columns = []
    for name in INPUT_COLUMNS:
        ref, cur = reference[name], current[name]
        if name in CATEGORICAL:
            # Nulos são uma categoria separada, sem sentinela que colida com texto válido.
            p, q = ref.dropna().value_counts(), cur.dropna().value_counts()
            categories = p.index.union(q.index)
            rp = np.append(p.reindex(categories, fill_value=0), ref.isna().sum()) / len(ref)
            cp = np.append(q.reindex(categories, fill_value=0), cur.isna().sum()) / len(cur)
            score = float(np.abs(rp - cp).sum() / 2)
            method, threshold = "total_variation", tv_threshold
        else:
            r = ref.dropna().to_numpy(dtype=float)
            c = cur.dropna().to_numpy(dtype=float)
            cuts = np.unique(np.quantile(r, np.linspace(0, 1, 11))) if len(r) else np.empty(0)
            if len(cuts) == 1:
                cuts = np.array([cuts[0], np.nextafter(cuts[0], np.inf)])
            edges = np.concatenate(([-np.inf], cuts, [np.inf]))
            rp = np.append(np.histogram(r, edges)[0], ref.isna().sum()).astype(float)
            cp = np.append(np.histogram(c, edges)[0], cur.isna().sum()).astype(float)
            # Suavização explícita evita infinitos em bins antes vazios.
            rp, cp = rp / len(ref) + 1e-6, cp / len(cur) + 1e-6
            rp, cp = rp / rp.sum(), cp / cp.sum()
            score = float(np.sum((cp - rp) * np.log(cp / rp)))
            method, threshold = "psi", psi_threshold
        columns.append(
            {
                "column": name,
                "method": method,
                "score": score,
                "threshold": threshold,
                "drift_detected": score >= threshold,
                "reference_missing_rate": float(ref.isna().mean()),
                "current_missing_rate": float(cur.isna().mean()),
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "reference_rows": len(reference),
        "current_rows": len(current),
        "minimum_rows": minimum,
        "numeric_bins": "quantis da referência, caudas e nulos",
        "psi_smoothing": 1e-6,
        "drift_detected": any(c["drift_detected"] for c in columns),
        "columns": columns,
        "interpretation": "Sinal de mudança nas entradas; não mede perda de qualidade.",
    }


def report(reference: Path, current: Path, output: Path, **options: Any) -> dict[str, Any]:
    """Lê Parquet e grava relatório novo, identificado pelos hashes das duas fontes."""
    if output.exists():
        raise FileExistsError(output)
    reference_bytes, current_bytes = reference.read_bytes(), current.read_bytes()
    result = compare(
        pd.read_parquet(io.BytesIO(reference_bytes)),
        pd.read_parquet(io.BytesIO(current_bytes)),
        **options,
    )
    # O hash identifica exatamente os bytes comparados, mesmo se a origem mudar depois.
    result["reference_sha256"] = hashlib.sha256(reference_bytes).hexdigest()
    result["current_sha256"] = hashlib.sha256(current_bytes).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return result
