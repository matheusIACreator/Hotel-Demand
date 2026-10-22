from __future__ import annotations

import pandas as pd
import pytest

from hotelml.config import INPUT_COLUMNS, LEAKAGE_COLUMNS
from hotelml.features import add_features

spark_module = pytest.importorskip("hotelml.spark", exc_type=ImportError)


@pytest.fixture(scope="module")
def spark():
    session = spark_module.create_spark("local[2]")
    session.conf.set("spark.sql.execution.arrow.maxRecordsPerBatch", "7")
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def reservations(raw_df):
    frame = raw_df[INPUT_COLUMNS].head(30).copy()
    frame.insert(0, "booking_id", [f"booking-{i}" for i in range(len(frame))])
    frame.loc[0, ["children", "country", "agent", "company"]] = [None, None, None, None]
    return frame


def test_spark_features_match_shared_pipeline(spark, reservations):
    source = (
        spark.createDataFrame(reservations)
        .withColumn("reservation_status", spark_module.F.lit("Canceled"))
        .withColumn("is_canceled", spark_module.F.lit(1))
        .repartition(2)
    )
    prepared = spark_module.prepare_features(source).toPandas().sort_values("booking_id")
    expected = add_features(reservations).sort_values("booking_id")
    pd.testing.assert_frame_equal(
        prepared.reset_index(drop=True),
        expected[prepared.columns].reset_index(drop=True),
        check_dtype=False,
    )
    assert not set(LEAKAGE_COLUMNS) & set(prepared.columns)
    assert "is_canceled" not in prepared.columns


def test_spark_rejects_numeric_identifier(spark, reservations):
    reservations["booking_id"] = range(len(reservations))
    with pytest.raises(ValueError, match="booking_id deve ser string"):
        spark_module.prepare_features(spark.createDataFrame(reservations))


@pytest.mark.parametrize("bad_id", [None, "", "   ", "booking-1"])
def test_spark_rejects_invalid_identifiers(spark, reservations, bad_id):
    reservations.loc[0, "booking_id"] = bad_id
    with pytest.raises(ValueError, match="booking_id"):
        spark_module.prepare_features(spark.createDataFrame(reservations))


def test_spark_rejects_missing_columns_and_empty_input(spark, reservations):
    source = spark.createDataFrame(reservations)
    with pytest.raises(ValueError, match="colunas em falta"):
        spark_module.prepare_features(source.drop("lead_time"))
    with pytest.raises(ValueError, match="lote vazio"):
        spark_module.prepare_features(source.limit(0))


def test_spark_rejects_invalid_bookings(spark, reservations):
    reservations.loc[0, "lead_time"] = -1
    prepared = spark_module.prepare_features(spark.createDataFrame(reservations))
    with pytest.raises(Exception, match="reserva inválida"):
        prepared.collect()


def test_feature_job_writes_parquet_without_overwriting(spark, reservations, tmp_path):
    source, output = str(tmp_path / "raw"), str(tmp_path / "features")
    spark.createDataFrame(reservations).write.parquet(source)
    result = spark_module.run_features(spark, source, output)
    assert result["rows"] == len(reservations)
    assert spark.read.parquet(output).count() == len(reservations)
    with pytest.raises(Exception, match="PATH_ALREADY_EXISTS"):
        spark_module.run_features(spark, source, output)
