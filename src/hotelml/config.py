"""Configuração central: constantes do dataset e settings lidos do ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Dataset público no Hugging Face (reservas de hotel, ~119 mil linhas).
HF_REPO_ID = "gemuchu/hotel_bookings"
HF_FILENAME = "data/train-00000-of-00001.parquet"

TARGET = "is_canceled"

# Colunas que só existem depois do desfecho da reserva: usá-las seria vazamento (leakage).
LEAKAGE_COLUMNS = ("reservation_status", "reservation_status_date", "assigned_room_type")

MONTH_TO_NUM = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

# Contrato de entrada do modelo: é exatamente o que uma requisição de inferência precisa enviar.
INPUT_COLUMNS = [
    "hotel",
    "lead_time",
    "arrival_date_month",
    "arrival_date_week_number",
    "arrival_date_day_of_month",
    "stays_in_weekend_nights",
    "stays_in_week_nights",
    "adults",
    "children",
    "babies",
    "meal",
    "country",
    "market_segment",
    "distribution_channel",
    "is_repeated_guest",
    "previous_cancellations",
    "previous_bookings_not_canceled",
    "reserved_room_type",
    "booking_changes",
    "deposit_type",
    "agent",
    "company",
    "days_in_waiting_list",
    "customer_type",
    "adr",
    "required_car_parking_spaces",
    "total_of_special_requests",
]

# Features que o modelo realmente consome, depois do passo `add_features`.
NUMERIC_MODEL = [
    "lead_time",
    "arrival_date_week_number",
    "arrival_date_day_of_month",
    "stays_in_weekend_nights",
    "stays_in_week_nights",
    "adults",
    "children",
    "babies",
    "is_repeated_guest",
    "previous_cancellations",
    "previous_bookings_not_canceled",
    "booking_changes",
    "days_in_waiting_list",
    "adr",
    "required_car_parking_spaces",
    "total_of_special_requests",
    "total_nights",
    "total_guests",
    "has_agent",
    "has_company",
    "arrival_month_num",
]
CATEGORICAL_MODEL = [
    "hotel",
    "meal",
    "country",
    "market_segment",
    "distribution_channel",
    "reserved_room_type",
    "deposit_type",
    "customer_type",
]

ADR_MAX = 1000.0  # remove outliers absurdos de diária (o dataset original tem um de 5400)

# O MLflow serializa modelos sklearn com skops, que recusa tipos desconhecidos ao carregar.
# Esta é uma allowlist explícita e revisada (modelo gerado por nós, em registry nosso).
# NUNCA trocar por "confiar em tudo": um arquivo de modelo adulterado poderia derrubar o serving.
SKOPS_TRUSTED_TYPES = [
    "hotelml.features.add_features",  # nosso código
    "numpy.dtype",
    "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor",
]


@dataclass(frozen=True)
class Settings:
    """Parâmetros de execução. Em produção vêm de variáveis de ambiente."""

    tracking_uri: str = field(
        default_factory=lambda: os.environ.get(
            "MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT / 'mlflow.db'}"
        )
    )
    artifact_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("MLFLOW_ARTIFACT_ROOT", str(PROJECT_ROOT / "mlartifacts"))
        )
    )
    experiment_name: str = field(
        default_factory=lambda: os.environ.get("MLFLOW_EXPERIMENT", "hotel-cancellation")
    )
    model_name: str = field(
        default_factory=lambda: os.environ.get("MODEL_NAME", "hotel-cancellation")
    )
    data_dir: Path = PROJECT_ROOT / "data" / "raw"
