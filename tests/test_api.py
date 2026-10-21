from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from hotelml.api import Booking, LoadedModel, create_app, load_serving_model
from hotelml.bundle import export_champion
from hotelml.config import INPUT_COLUMNS
from hotelml.features import build_pipeline, clean_training_data
from hotelml.train import train_and_register


@pytest.fixture
def payload(raw_df):
    # JSON representa valores ausentes com null.
    return {"bookings": json.loads(raw_df[INPUT_COLUMNS].head(3).to_json(orient="records"))}


@pytest.fixture
def loaded(raw_df):
    data = clean_training_data(raw_df)
    model = build_pipeline("logreg").fit(data[INPUT_COLUMNS], data["is_canceled"])
    return LoadedModel(model, "test-model", "7")


def test_contract_matches_training_columns():
    assert set(Booking.model_fields) == set(INPUT_COLUMNS)


def test_api_matches_pipeline_and_loads_once(loaded, payload):
    calls = []

    def loader():
        calls.append(True)
        return loaded

    with TestClient(create_app(loader)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").json()["model_version"] == "7"
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        result = response.json()
        assert result["model_version"] == "7"
        import pandas as pd

        expected = loaded.model.predict_proba(pd.DataFrame(payload["bookings"]))[:, 1]
        np.testing.assert_allclose(
            [p["cancellation_probability"] for p in result["predictions"]], expected
        )
        assert client.post("/predict", json=payload).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lead_time", -1),
        ("lead_time", "10"),
        ("arrival_date_month", "Smarch"),
        ("adr", 1000),
        ("reservation_status", "Canceled"),
        ("children", -1),
    ],
)
def test_api_rejects_invalid_input(loaded, payload, field, value):
    payload["bookings"][0][field] = value
    with TestClient(create_app(lambda: loaded)) as client:
        assert client.post("/predict", json=payload).status_code == 422


def test_api_rejects_empty_or_large_batch_and_zero_guests(loaded, payload):
    with TestClient(create_app(lambda: loaded)) as client:
        assert client.post("/predict", json={"bookings": []}).status_code == 422
        assert (
            client.post("/predict", json={"bookings": payload["bookings"] * 34}).status_code == 422
        )
        row = payload["bookings"][0]
        row.update(adults=0, children=0, babies=0)
        assert client.post("/predict", json=payload).status_code == 422


def test_unavailable_model_returns_503(payload):
    app = create_app()
    # Sem lifespan, simula a indisponibilidade antes do modelo estar carregado.
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    assert client.post("/predict", json=payload).status_code == 503


def test_failed_model_load_prevents_startup():
    def fail():
        raise RuntimeError("no champion")

    with pytest.raises(RuntimeError, match="no champion"), TestClient(create_app(fail)):
        pass


def test_invalid_prediction_is_not_exposed(loaded, payload):
    class BrokenModel:
        def predict_proba(self, frame):
            return np.full((len(frame), 2), np.nan)

    broken = LoadedModel(BrokenModel(), "test-model", "8")
    with TestClient(create_app(lambda: broken)) as client:
        response = client.post("/predict", json=payload)
        assert response.status_code == 500
        assert response.json() == {"detail": "falha na inferência"}


def test_export_bundle_survives_registry_removal(raw_df, settings, tmp_path, monkeypatch, payload):
    result = train_and_register(raw_df, settings, model_type="logreg")
    output = tmp_path / "bundle"
    manifest = export_champion(settings, output)
    assert manifest["model_version"] == result.model_version
    with pytest.raises(FileExistsError):
        export_champion(settings, output)
    monkeypatch.setenv("MODEL_BUNDLE", str(output))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:1")
    with TestClient(create_app()) as client:
        response = client.post("/predict", json=payload)
        assert response.status_code == 200
        assert response.json()["model_version"] == result.model_version


def test_registry_loader_pins_version(raw_df, settings, monkeypatch):
    result = train_and_register(raw_df, settings, model_type="logreg")
    monkeypatch.delenv("MODEL_BUNDLE", raising=False)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", settings.tracking_uri)
    monkeypatch.setenv("MODEL_NAME", settings.model_name)
    loaded = load_serving_model()
    assert loaded.version == result.model_version
