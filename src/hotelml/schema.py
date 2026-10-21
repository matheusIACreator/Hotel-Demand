"""Validação de contrato dos dados brutos (falha cedo, com mensagem clara)."""

from __future__ import annotations

import pandas as pd

from hotelml.config import INPUT_COLUMNS, MONTH_TO_NUM, TARGET

NON_NEGATIVE = (
    "lead_time",
    "stays_in_weekend_nights",
    "stays_in_week_nights",
    "adults",
    "babies",
    "previous_cancellations",
    "previous_bookings_not_canceled",
    "booking_changes",
    "days_in_waiting_list",
    "required_car_parking_spaces",
    "total_of_special_requests",
)


class DataValidationError(ValueError):
    """Os dados não respeitam o contrato esperado."""


def validate_raw(df: pd.DataFrame) -> None:
    """Valida o dataset bruto. Lança `DataValidationError` listando todos os problemas."""
    if df.empty:
        raise DataValidationError("dataset vazio")

    required = [*INPUT_COLUMNS, TARGET, "arrival_date_year"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError(f"colunas em falta: {missing}")

    errors: list[str] = []
    if not df[TARGET].isin([0, 1]).all():
        errors.append(f"{TARGET} deve conter apenas 0 ou 1")

    for col in NON_NEGATIVE:
        if (df[col] < 0).any():
            errors.append(f"{col} tem valores negativos")

    unknown_months = set(df["arrival_date_month"].dropna().unique()) - set(MONTH_TO_NUM)
    if unknown_months:
        errors.append(f"meses inválidos: {sorted(unknown_months)}")

    if errors:
        raise DataValidationError("; ".join(errors))
