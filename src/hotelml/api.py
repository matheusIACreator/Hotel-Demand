"""API de inferência: contrato explícito, modelo carregado uma vez e probes independentes."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hotelml.bundle import LoadedModel, load_bundle
from hotelml.config import ADR_MAX, INPUT_COLUMNS, MONTH_TO_NUM, Settings
from hotelml.observability import RequestTelemetry, event

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]


class Booking(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    hotel: str = Field(min_length=1, max_length=100)
    lead_time: NonNegativeInt
    arrival_date_month: str
    arrival_date_week_number: int = Field(ge=1, le=53, strict=True)
    arrival_date_day_of_month: int = Field(ge=1, le=31, strict=True)
    stays_in_weekend_nights: NonNegativeInt
    stays_in_week_nights: NonNegativeInt
    adults: NonNegativeInt
    children: float | None = Field(ge=0)
    babies: NonNegativeInt
    meal: str = Field(min_length=1, max_length=100)
    country: str | None = Field(max_length=100)
    market_segment: str = Field(min_length=1, max_length=100)
    distribution_channel: str = Field(min_length=1, max_length=100)
    is_repeated_guest: Literal[0, 1]
    previous_cancellations: NonNegativeInt
    previous_bookings_not_canceled: NonNegativeInt
    reserved_room_type: str = Field(min_length=1, max_length=100)
    booking_changes: NonNegativeInt
    deposit_type: str = Field(min_length=1, max_length=100)
    agent: float | None = Field(ge=0)
    company: float | None = Field(ge=0)
    days_in_waiting_list: NonNegativeInt
    customer_type: str = Field(min_length=1, max_length=100)
    adr: float = Field(ge=0, lt=ADR_MAX)
    required_car_parking_spaces: NonNegativeInt
    total_of_special_requests: NonNegativeInt

    @model_validator(mode="after")
    def valid_booking(self) -> Booking:
        if self.arrival_date_month not in MONTH_TO_NUM:
            raise ValueError("mês de chegada inválido")
        if self.adults + (self.children or 0) + self.babies <= 0:
            raise ValueError("a reserva deve ter pelo menos um hóspede")
        return self


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bookings: list[Booking] = Field(min_length=1, max_length=100)


class Prediction(BaseModel):
    cancellation_probability: float = Field(ge=0, le=1)
    is_canceled: bool


class PredictResponse(BaseModel):
    model_name: str
    model_version: str
    predictions: list[Prediction]


def load_serving_model() -> LoadedModel:
    load_dotenv(override=False)
    bundle = os.environ.get("MODEL_BUNDLE")
    if bundle:
        return load_bundle(Path(bundle))
    settings = Settings()
    mlflow.set_tracking_uri(settings.tracking_uri)
    mlflow.set_registry_uri(settings.tracking_uri)
    client = mlflow.MlflowClient()
    version = client.get_model_version_by_alias(settings.model_name, "champion")
    model = mlflow.sklearn.load_model(f"models:/{settings.model_name}/{version.version}")
    return LoadedModel(model, settings.model_name, str(version.version))


def create_app(loader: Callable[[], LoadedModel] = load_serving_model) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        # O access log do Uvicorn inclui query strings; a telemetria usa rotas controladas.
        logging.getLogger("uvicorn.access").disabled = True
        # Falha no arranque: uma revisão sem modelo nunca deve receber tráfego.
        start = time.perf_counter()
        event("model_loading")
        try:
            app.state.loaded = loader()
        except Exception as exc:
            event("model_load_failed", error_type=type(exc).__name__)
            raise RuntimeError("modelo indisponível na inicialização") from None
        loaded = app.state.loaded
        event(
            "model_ready",
            model_name=loaded.name,
            model_version=loaded.version,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        try:
            yield
        finally:
            event("model_stopped", model_name=loaded.name, model_version=loaded.version)
            app.state.loaded = None

    app = FastAPI(title="hotelml", version="0.2.0", lifespan=lifespan)
    app.add_middleware(RequestTelemetry)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        loaded = getattr(app.state, "loaded", None)
        if loaded is None:
            raise HTTPException(503, "modelo indisponível")
        return {"status": "ready", "model_name": loaded.name, "model_version": loaded.version}

    @app.post("/predict", response_model=PredictResponse)
    def predict(request: PredictRequest, http_request: Request) -> PredictResponse:
        http_request.state.booking_count = len(request.bookings)
        loaded = getattr(app.state, "loaded", None)
        if loaded is None:
            raise HTTPException(503, "modelo indisponível")
        frame = pd.DataFrame([b.model_dump() for b in request.bookings], columns=INPUT_COLUMNS)
        try:
            probabilities = np.asarray(loaded.model.predict_proba(frame))[:, 1]
            if len(probabilities) != len(frame) or not np.isfinite(probabilities).all():
                raise ValueError("probabilidades inválidas")
            predictions = [
                Prediction(cancellation_probability=float(p), is_canceled=bool(p >= 0.5))
                for p in probabilities
            ]
        except Exception as exc:
            http_request.state.error_type = type(exc).__name__
            raise HTTPException(500, "falha na inferência") from None
        return PredictResponse(
            model_name=loaded.name, model_version=loaded.version, predictions=predictions
        )

    return app


app = create_app()
