"""Converte estados finais de reserva exportados pela origem para o contrato de desfechos."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from hotelml.quality import _ids, _utc

# Estados finais do sistema de reservas e o alvo que o modelo prevê. No dataset de treino,
# `No-Show` também está marcado como cancelamento (`is_canceled = 1`).
FINAL_STATUSES = {"Canceled": 1, "No-Show": 1, "Check-Out": 0}
SOURCE_COLUMNS = ("booking_id", "reservation_status", "reservation_status_date")


def to_outcomes(
    source: pd.DataFrame, *, available_at: str, pending_statuses: Iterable[str] = ()
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Mapeia estados finais; reservas declaradas pendentes ficam de fora, sem virar desfecho."""
    available = _utc(available_at)
    if not set(SOURCE_COLUMNS) <= set(source.columns):
        raise ValueError(f"colunas obrigatórias ausentes: {', '.join(SOURCE_COLUMNS)}")
    _ids(source)
    pending = set(pending_statuses)
    if pending & set(FINAL_STATUSES):
        raise ValueError("um estado final não pode ser declarado pendente")
    status = source.reservation_status
    # Um estado desconhecido interrompe a exportação: descartá-lo esconderia um erro da origem.
    unknown = sorted({repr(v) for v in status[~status.isin(set(FINAL_STATUSES) | pending)]})
    if unknown:
        raise ValueError(f"estados não reconhecidos: {', '.join(unknown)}")
    final = source[status.isin(set(FINAL_STATUSES))]
    dates = pd.to_datetime(final.reservation_status_date, errors="coerce", utc=True)
    if dates.isna().any():
        raise ValueError("data do estado final ausente ou inválida")
    if (dates > available).any():
        raise ValueError("estado final com data posterior à disponibilização")
    outcomes = pd.DataFrame(
        {
            "booking_id": final.booking_id.to_numpy(),
            "is_canceled": final.reservation_status.map(FINAL_STATUSES).to_numpy(dtype="int64"),
            # Instante em que a origem disponibilizou o resultado, não a data do evento:
            # o contrato proíbe datas retroativas que ocultem o atraso de disponibilização.
            "resolved_at": available,
        }
    )
    summary = {
        "schema_version": 1,
        "available_at": available.isoformat(),
        "source_rows": len(source),
        "final_outcomes": len(outcomes),
        "pending_excluded": int(status.isin(pending).sum()),
        "status_counts": {str(k): int(v) for k, v in status.value_counts().sort_index().items()},
        "canceled": int(outcomes.is_canceled.sum()),
        "not_canceled": int((outcomes.is_canceled == 0).sum()),
        "earliest_status_date": dates.min().date().isoformat() if len(dates) else None,
        "latest_status_date": dates.max().date().isoformat() if len(dates) else None,
    }
    return outcomes, summary


def export_outcomes(
    source: Path, output: Path, *, available_at: str, pending_statuses: Iterable[str] = ()
) -> dict[str, Any]:
    """Grava o Parquet de desfechos e um manifesto ao lado; nunca sobrescreve."""
    manifest_path = output.with_suffix(".manifest.json")
    for path in (output, manifest_path):
        if path.exists():
            raise FileExistsError(path)
    source_bytes = source.read_bytes()
    frame = (
        pd.read_csv(io.BytesIO(source_bytes), dtype={"booking_id": "string"})
        if source.suffix == ".csv"
        else pd.read_parquet(io.BytesIO(source_bytes))
    )
    if "booking_id" in frame:
        # CSV e Arrow podem devolver tipos de string diferentes; o contrato exige `str`.
        frame["booking_id"] = frame.booking_id.astype(object)
    outcomes, summary = to_outcomes(
        frame, available_at=available_at, pending_statuses=pending_statuses
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    outcomes.to_parquet(buffer, index=False)
    with output.open("xb") as stream:
        stream.write(buffer.getvalue())
    summary["provenance"] = {
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        # Mesmo hash que `hotelml quality` grava em `provenance.outcomes_sha256`.
        "outcomes_sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
    }
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return summary
