"""Fatores de uma previsão: valores de Shapley por amostragem de permutações.

Mede quanto cada campo da reserva desloca a probabilidade do modelo em relação a reservas
típicas do treino. Explica o modelo, não a causa do cancelamento. É a única fonte de fatos da
explicação em linguagem natural: o texto não pode citar o que não estiver aqui.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hotelml.config import INPUT_COLUMNS


def shapley_values(
    predict: Callable[[pd.DataFrame], np.ndarray],
    booking: dict[str, Any],
    background: pd.DataFrame,
    *,
    permutations: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    """Contribuição de cada campo, com erro padrão; a soma fecha em p(reserva) - p(base)."""
    columns = list(background.columns)
    if set(booking) != set(columns):
        raise ValueError("a reserva e a referência precisam ter exatamente os mesmos campos")
    if background.empty or not 2 <= permutations <= 5000:
        raise ValueError("referência vazia ou número de permutações fora de 2-5000")
    rng = np.random.default_rng(seed)
    size = len(columns)
    # Cada permutação parte de uma reserva de referência e troca um campo de cada vez pelo
    # valor da reserva explicada; a variação a cada troca é a contribuição marginal do campo.
    rows = rng.integers(0, len(background), permutations)
    orders = np.argsort(rng.random((permutations, size)), axis=1)
    ranks = np.argsort(orders, axis=1)
    steps = np.arange(size + 1)[None, :, None]
    replaced = (ranks[:, None, :] < steps).reshape(-1, size)

    base = background.iloc[np.repeat(rows, size + 1)].reset_index(drop=True)
    frame = {}
    for index, name in enumerate(columns):
        column = base[name].astype(object)
        column[replaced[:, index]] = booking[name]
        # Campos numéricos voltam ao tipo numérico (ausente vira NaN); texto fica como está.
        numeric = pd.api.types.is_numeric_dtype(background[name])
        frame[name] = pd.to_numeric(column) if numeric else column
    scores = np.asarray(predict(pd.DataFrame(frame)), dtype=float)
    if scores.shape != (permutations * (size + 1),) or not np.isfinite(scores).all():
        raise ValueError("probabilidades inválidas na atribuição")
    scores = scores.reshape(permutations, size + 1)

    deltas = np.empty((permutations, size))
    np.put_along_axis(deltas, orders, np.diff(scores, axis=1), axis=1)
    mean = deltas.mean(axis=0)
    error = deltas.std(axis=0, ddof=1) / np.sqrt(permutations)
    probability = float(scores[:, -1].mean())
    baseline = float(scores[:, 0].mean())
    return {
        "probability": probability,
        "baseline_probability": baseline,
        "contributions": {
            name: {"value": float(mean[i]), "std_error": float(error[i])}
            for i, name in enumerate(columns)
        },
        # Telescópica por construção; um desvio aqui indicaria um erro de implementação.
        "additivity_gap": float(abs(mean.sum() - (probability - baseline))),
    }


def explain_booking(
    model: Any,
    booking: dict[str, Any],
    reference: pd.DataFrame,
    identity: dict[str, str],
    *,
    reference_sha256: str,
    threshold: float = 0.5,
    permutations: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    """Relatório de fatores de uma reserva já validada pelo contrato `Booking`."""
    result = shapley_values(
        lambda frame: model.predict_proba(frame)[:, 1],
        {name: booking[name] for name in INPUT_COLUMNS},
        reference[INPUT_COLUMNS],
        permutations=permutations,
        seed=seed,
    )
    factors = sorted(
        (
            {
                "field": name,
                "value": booking[name],
                "contribution": item["value"],
                "std_error": item["std_error"],
            }
            for name, item in result["contributions"].items()
        ),
        key=lambda factor: -abs(factor["contribution"]),
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "model": identity,
        "method": "permutation_shapley",
        "permutations": permutations,
        "seed": seed,
        "reference_rows": len(reference),
        "reference_sha256": reference_sha256,
        "threshold": threshold,
        "probability": result["probability"],
        "is_canceled": result["probability"] >= threshold,
        "baseline_probability": result["baseline_probability"],
        "additivity_gap": result["additivity_gap"],
        "factors": factors,
        "interpretation": (
            "Contribuições em probabilidade, relativas a reservas de referência do treino. "
            "Descrevem o comportamento do modelo; não são causa nem certeza."
        ),
    }


def explain_report(
    bundle: Path,
    reference: Path,
    booking: Path,
    output: Path,
    *,
    permutations: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    from hotelml.api import Booking
    from hotelml.bundle import load_bundle
    from hotelml.reference import load_reference

    if output.exists():
        raise FileExistsError(output)
    payload = Booking.model_validate(json.loads(booking.read_text(encoding="utf-8")))
    frame, metadata = load_reference(bundle, reference)
    loaded = load_bundle(bundle)
    result = explain_booking(
        loaded.model,
        payload.model_dump(),
        frame,
        {key: metadata[key] for key in ("model_name", "model_version", "run_id")},
        reference_sha256=metadata["reference_sha256"],
        permutations=permutations,
        seed=seed,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result
