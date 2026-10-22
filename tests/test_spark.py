from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from hotelml.bundle import LoadedModel
from hotelml.config import INPUT_COLUMNS, LEAKAGE_COLUMNS, SKOPS_TRUSTED_TYPES
from hotelml.features import add_features, build_pipeline, clean_training_data

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


@pytest.fixture(scope="module")
def snapshot(raw_df, tmp_path_factory):
    import mlflow.sklearn

    data = clean_training_data(raw_df)
    model = build_pipeline("logreg").fit(data[INPUT_COLUMNS], data["is_canceled"])
    root = tmp_path_factory.mktemp("snapshot")
    mlflow.sklearn.save_model(
        model,
        str(root / "model"),
        serialization_format="skops",
        skops_trusted_types=SKOPS_TRUSTED_TYPES,
        pip_requirements=[],
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "model_name": "test-model",
                "model_version": "17",
                "run_id": "batch-test",
            }
        ),
        encoding="utf-8",
    )
    return root, model


def test_distributed_predictions_match_pipeline(spark, reservations, snapshot):
    root, model = snapshot
    source = spark.createDataFrame(reservations).repartition(2)
    predicted = spark_module.score_batch(source, root, threshold=0.65).toPandas()
    predicted = predicted.sort_values("booking_id")
    raw = reservations.sort_values("booking_id")[INPUT_COLUMNS]
    expected = model.predict_proba(raw)[:, 1]
    np.testing.assert_allclose(predicted.cancellation_probability, expected)
    np.testing.assert_array_equal(predicted.is_canceled, expected >= 0.65)
    assert set(predicted.model_name) == {"test-model"}
    assert set(predicted.model_version) == {"17"}
    assert set(predicted.threshold) == {0.65}
    assert predicted.batch_id.nunique() == 1
    assert predicted.scored_at.nunique() == 1
    assert predicted.booking_id.is_unique


def test_scoring_recomputes_features_from_raw_columns(spark, reservations, snapshot):
    root, model = snapshot
    features = spark_module.prepare_features(spark.createDataFrame(reservations))
    features = features.withColumn("total_guests", spark_module.F.lit(100000))
    predicted = spark_module.score_batch(features, root).toPandas().sort_values("booking_id")
    expected = model.predict_proba(reservations.sort_values("booking_id")[INPUT_COLUMNS])[:, 1]
    np.testing.assert_allclose(predicted.cancellation_probability, expected)


@pytest.mark.parametrize("threshold", [-0.1, 1.1, np.nan, np.inf])
def test_scoring_rejects_invalid_threshold(spark, reservations, snapshot, threshold):
    with pytest.raises(ValueError, match="threshold"):
        spark_module.score_batch(spark.createDataFrame(reservations), snapshot[0], threshold)


def test_batch_job_writes_auditable_predictions(spark, reservations, snapshot, tmp_path):
    source, output = str(tmp_path / "raw"), str(tmp_path / "scores")
    spark.createDataFrame(reservations).write.parquet(source)
    result = spark_module.run_batch(spark, source, output, snapshot[0])
    assert result["rows"] == len(reservations)
    scores = spark.read.parquet(output).toPandas()
    assert len(scores) == len(reservations)
    assert scores.model_version.unique().tolist() == ["17"]
    assert (tmp_path / "scores" / "_SUCCESS").exists()
    with pytest.raises(Exception, match="PATH_ALREADY_EXISTS"):
        spark_module.run_batch(spark, source, output, snapshot[0])


def test_partition_loads_model_once_for_multiple_arrow_batches(monkeypatch, reservations):
    calls = []

    class Model:
        def predict_proba(self, frame):
            return np.tile([0.3, 0.7], (len(frame), 1))

    def loader(path):
        calls.append(path)
        return LoadedModel(Model(), "test-model", "17")

    monkeypatch.setattr(spark_module, "load_bundle", loader)
    monkeypatch.setattr(spark_module.SparkFiles, "get", lambda name: ".")
    predict = spark_module._prediction_batches(
        "bundle.zip",
        "test-model",
        "17",
        0.5,
        "batch-1",
        "2026-10-22T00:00:00Z",
    )
    batches = list(predict(iter([reservations.iloc[:3], reservations.iloc[3:]])))
    assert len(batches) == 2
    assert len(calls) == 1
    assert sum(len(frame) for frame in batches) == len(reservations)


@pytest.mark.parametrize("probability", [np.nan, -0.1, 1.1])
def test_partition_rejects_invalid_probabilities(monkeypatch, reservations, probability):
    class Model:
        def predict_proba(self, frame):
            return np.tile([0.5, probability], (len(frame), 1))

    monkeypatch.setattr(
        spark_module,
        "load_bundle",
        lambda path: LoadedModel(Model(), "test-model", "17"),
    )
    monkeypatch.setattr(spark_module.SparkFiles, "get", lambda name: ".")
    predict = spark_module._prediction_batches(
        "bundle.zip",
        "test-model",
        "17",
        0.5,
        "batch-1",
        "2026-10-22T00:00:00Z",
    )
    with pytest.raises(ValueError, match="probabilidades inválidas"):
        list(predict(iter([reservations])))
