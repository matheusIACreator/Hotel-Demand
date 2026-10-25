from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from hotelml.api import LoadedModel, create_app
from hotelml.config import INPUT_COLUMNS


def records(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name == "hotelml.telemetry"]


def test_request_metadata_and_lifecycle_without_payload(raw_df, caplog):
    class Model:
        def predict_proba(self, frame):
            return [[0.8, 0.2] for _ in range(len(frame))]

    payload = {"bookings": json.loads(raw_df[INPUT_COLUMNS].head(1).to_json(orient="records"))}
    payload["bookings"][0]["country"] = "SEGREDO_RESERVA"
    caplog.set_level(logging.INFO, logger="hotelml.telemetry")
    with TestClient(create_app(lambda: LoadedModel(Model(), "hotel", "1"))) as client:
        response = client.post(
            "/predict?token=SEGREDO_QUERY",
            json=payload,
            headers={"X-Request-ID": "SEGREDO_HEADER", "Authorization": "Bearer SEGREDO_AUTH"},
        )
        assert response.status_code == 200
        request_id = response.headers["x-request-id"]
        assert re.fullmatch(r"[a-f0-9]{32}", request_id)
        client.get("/health/live")
        client.get("/health/ready")
        client.get("/SEGREDO_CAMINHO")
        assert client.get("/health/live").headers["x-request-id"] != request_id
    events = records(caplog)
    assert [r["event"] for r in events] == [
        "model_loading",
        "model_ready",
        "http_request",
        "http_request",
        "model_stopped",
    ]
    request = events[2]
    assert request["request_id"] == request_id
    assert request["route"] == "/predict"
    assert request["model_version"] == "1"
    assert request["booking_count"] == 1
    assert request["duration_ms"] >= 0
    assert events[3]["route"] == "other"
    assert "SEGREDO" not in json.dumps(events)


@pytest.mark.parametrize("status", [422, 503, 500])
def test_failed_predictions_record_status_without_exception_details(raw_df, caplog, status):
    class Model:
        def predict_proba(self, frame):
            raise ValueError("SEGREDO_EXCECAO")

    caplog.set_level(logging.INFO, logger="hotelml.telemetry")
    app = create_app(lambda: LoadedModel(Model(), "hotel", "1"))
    payload = {"bookings": json.loads(raw_df[INPUT_COLUMNS].head(1).to_json(orient="records"))}
    with TestClient(app) as client:
        if status == 422:
            payload["bookings"][0]["lead_time"] = -1
        if status == 503:
            app.state.loaded = None
        response = client.post("/predict", json=payload)
        assert response.status_code == status
        request = [r for r in records(caplog) if r["event"] == "http_request"][-1]
        assert request["status_code"] == status
        assert request["error_type"] == ("ValueError" if status == 500 else None)
    assert "SEGREDO_EXCECAO" not in caplog.text


def test_unhandled_exception_is_sanitized(caplog):
    caplog.set_level(logging.INFO, logger="hotelml.telemetry")
    app = create_app(lambda: LoadedModel(None, "hotel", "1"))

    @app.get("/broken")
    def broken():
        raise RuntimeError("SEGREDO_ERRO_INTERNO")

    with TestClient(app) as client:
        response = client.get("/broken")
    assert response.status_code == 500
    assert response.json() == {"detail": "erro interno"}
    assert "SEGREDO" not in caplog.text
    assert records(caplog)[2]["error_type"] == "RuntimeError"


def test_startup_failure_has_event_without_sensitive_message(caplog):
    caplog.set_level(logging.INFO, logger="hotelml.telemetry")

    def fail():
        raise ValueError("SEGREDO_REGISTRY")

    with pytest.raises(RuntimeError, match="modelo indisponível"), TestClient(create_app(fail)):
        pass
    events = records(caplog)
    assert events[-1]["event"] == "model_load_failed"
    assert events[-1]["error_type"] == "ValueError"
    assert "SEGREDO" not in caplog.text
