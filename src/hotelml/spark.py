"""Preparação distribuída de reservas, preservando o contrato e as features do modelo."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from pyspark import SparkFiles
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from hotelml.api import Booking
from hotelml.bundle import load_bundle
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


def _prediction_batches(
    archive_name: str,
    model_name: str,
    model_version: str,
    threshold: float,
    batch_id: str,
    scored_at: str,
) -> Callable[[Iterator[pd.DataFrame]], Iterator[pd.DataFrame]]:
    def predict(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        loaded = load_bundle(Path(SparkFiles.get(archive_name)))
        if (loaded.name, loaded.version) != (model_name, model_version):
            raise ValueError("identidade do snapshot divergente no executor")
        for batch in batches:
            raw = validate_bookings(batch)
            probabilities = np.asarray(loaded.model.predict_proba(raw))
            if probabilities.shape != (len(raw), 2):
                raise ValueError("dimensões das probabilidades inválidas")
            proba = probabilities[:, 1]
            if not (np.isfinite(proba) & (proba >= 0) & (proba <= 1)).all():
                raise ValueError("probabilidades inválidas")
            yield pd.DataFrame(
                {
                    ID_COLUMN: batch[ID_COLUMN].to_numpy(),
                    "cancellation_probability": proba,
                    "is_canceled": proba >= threshold,
                    "model_name": model_name,
                    "model_version": model_version,
                    "threshold": threshold,
                    "batch_id": batch_id,
                    "scored_at": pd.Timestamp(scored_at),
                }
            )

    return predict


def score_batch(frame: DataFrame, bundle: Path, threshold: float = 0.5) -> DataFrame:
    """Distribui um snapshot imutável; carrega o modelo uma vez por partição, nunca por linha."""
    import shutil

    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold deve estar entre 0 e 1")
    validate_identifiers(frame)
    loaded = load_bundle(bundle)
    batch_id = uuid4().hex
    # Ações/retries são lazy: o ZIP deve sobreviver até ao fim do SparkContext.
    # A área gerida pelo Spark é removida quando a sessão termina.
    archive_dir = Path(SparkFiles.getRootDirectory()) / "hotelml-snapshots"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = shutil.make_archive(str(archive_dir / f"hotelml-{batch_id}"), "zip", bundle)
    frame.sparkSession.sparkContext.addArchive(archive)
    archive_name = Path(archive).name
    schema = StructType(
        [
            StructField(ID_COLUMN, StringType(), False),
            StructField("cancellation_probability", DoubleType(), False),
            StructField("is_canceled", BooleanType(), False),
            StructField("model_name", StringType(), False),
            StructField("model_version", StringType(), False),
            StructField("threshold", DoubleType(), False),
            StructField("batch_id", StringType(), False),
            StructField("scored_at", TimestampType(), False),
        ]
    )
    predictor = _prediction_batches(
        archive_name,
        loaded.name,
        loaded.version,
        threshold,
        batch_id,
        datetime.now(UTC).isoformat(),
    )
    return frame.select(ID_COLUMN, *INPUT_COLUMNS).mapInPandas(predictor, schema=schema)


def run_batch(
    spark: SparkSession,
    source: str,
    output: str,
    bundle: Path,
    threshold: float = 0.5,
) -> dict[str, str | int]:
    predictions = score_batch(spark.read.parquet(source), bundle, threshold).persist()
    try:
        rows = predictions.count()
        predictions.write.mode("errorifexists").parquet(output)
    finally:
        predictions.unpersist()
    return {"source": source, "output": output, "rows": rows}
