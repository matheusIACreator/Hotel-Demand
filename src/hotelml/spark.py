"""Preparação distribuída de reservas, preservando o contrato e as features do modelo."""

from __future__ import annotations

from collections.abc import Iterator

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType

from hotelml.api import Booking
from hotelml.config import CATEGORICAL_MODEL, INPUT_COLUMNS
from hotelml.features import add_features

ID_COLUMN = "booking_id"
DERIVED_COLUMNS = ["total_nights", "total_guests", "has_agent", "has_company", "arrival_month_num"]
NULLABLE_COLUMNS = {"children", "country", "agent", "company"}
STRING_COLUMNS = {*CATEGORICAL_MODEL, "arrival_date_month"}
DOUBLE_COLUMNS = {"children", "agent", "company", "adr", "total_guests"}


def feature_schema() -> StructType:
    fields = [StructField(ID_COLUMN, StringType(), nullable=False)]
    for name in [*INPUT_COLUMNS, *DERIVED_COLUMNS]:
        dtype = (
            StringType()
            if name in STRING_COLUMNS
            else DoubleType()
            if name in DOUBLE_COLUMNS
            else LongType()
        )
        fields.append(StructField(name, dtype, nullable=name in NULLABLE_COLUMNS))
    return StructType(fields)


def validate_bookings(frame: pd.DataFrame) -> pd.DataFrame:
    """Usa a mesma validação de inferência da API, incluindo os valores ausentes de Arrow."""
    raw = frame[INPUT_COLUMNS].astype(object).where(frame[INPUT_COLUMNS].notna(), None)
    rows = []
    for record in raw.to_dict(orient="records"):
        try:
            rows.append(Booking.model_validate(record).model_dump())
        except ValueError:
            # Não colocar payloads potencialmente pessoais nos logs do executor.
            raise ValueError("reserva inválida no lote; reveja o contrato Booking") from None
    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def _feature_batches(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    for batch in batches:
        features = add_features(validate_bookings(batch))
        features.insert(0, ID_COLUMN, batch[ID_COLUMN].to_numpy())
        yield features[[ID_COLUMN, *INPUT_COLUMNS, *DERIVED_COLUMNS]]


def validate_identifiers(frame: DataFrame) -> None:
    missing = [c for c in [ID_COLUMN, *INPUT_COLUMNS] if c not in frame.columns]
    if missing:
        raise ValueError(f"colunas em falta: {missing}")
    if not isinstance(frame.schema[ID_COLUMN].dataType, StringType):
        raise ValueError("booking_id deve ser string")
    if frame.limit(1).count() == 0:
        raise ValueError("lote vazio")
    invalid = frame.where(F.col(ID_COLUMN).isNull() | (F.trim(F.col(ID_COLUMN)) == ""))
    if invalid.limit(1).count():
        raise ValueError("booking_id nulo ou vazio")
    if frame.groupBy(ID_COLUMN).count().where(F.col("count") > 1).limit(1).count():
        raise ValueError("booking_id duplicado")


def prepare_features(frame: DataFrame) -> DataFrame:
    """Valida IDs globalmente e calcula features por lote Arrow, sem coletar o dataset."""
    validate_identifiers(frame)
    return frame.select(ID_COLUMN, *INPUT_COLUMNS).mapInPandas(
        _feature_batches, schema=feature_schema()
    )


def create_spark(master: str | None = None) -> SparkSession:
    builder = (
        SparkSession.builder.appName("hotelml")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.execution.arrow.maxRecordsPerBatch", "1000")
    )
    if master:
        builder = builder.master(master)
    return builder.getOrCreate()


def run_features(spark: SparkSession, source: str, output: str) -> dict[str, str | int]:
    prepared = prepare_features(spark.read.parquet(source)).persist()
    try:
        rows = prepared.count()  # Valida todos os lotes antes de iniciar a escrita.
        prepared.write.mode("errorifexists").parquet(output)
    finally:
        prepared.unpersist()
    return {"source": source, "output": output, "rows": rows}
