"""Exercício sintético local de aliases e snapshots; nunca altera o ambiente publicado."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

import mlflow
import numpy as np
from fastapi.testclient import TestClient
from mlflow import MlflowClient

from hotelml import registry
from hotelml.api import create_app
from hotelml.bundle import export_champion, load_bundle
from hotelml.config import INPUT_COLUMNS, Settings
from hotelml.synthetic import make_synthetic
from hotelml.train import train_and_register


def close_database(uri: str) -> None:
    # MLflow mantém pools em cache; liberar somente o banco temporário deste exercício.
    from mlflow.store.model_registry.sqlalchemy_store import SqlAlchemyStore as RegistryStore
    from mlflow.store.tracking.sqlalchemy_store import SqlAlchemyStore as TrackingStore

    for store in (RegistryStore, TrackingStore):
        engine = store._engine_map.get(uri)
        if engine is not None:
            engine.dispose()


def require(condition: bool) -> None:
    if not condition:
        raise RuntimeError("verificação de rollback falhou")


def digest(root: Path) -> str:
    checksum = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        checksum.update(path.relative_to(root).as_posix().encode() + b"\0")
        checksum.update(hashlib.sha256(path.read_bytes()).digest())
    return checksum.hexdigest()


def exercise(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    start = time.perf_counter()
    previous_tracking, previous_registry = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    try:
        with (
            tempfile.TemporaryDirectory(prefix="hotelml-rollback-") as directory,
            ExitStack() as cleanup,
        ):
            root = Path(directory)
            settings = Settings(
                tracking_uri=f"sqlite:///{root / 'mlflow.db'}",
                artifact_root=root / "artifacts",
                experiment_name="rollback-exercise",
                model_name="rollback-exercise",
                data_dir=root / "data",
            )
            cleanup.callback(close_database, settings.tracking_uri)
            data = make_synthetic(600, seed=42)
            baseline = train_and_register(
                data, settings, model_type="logreg", data_source="synthetic"
            )
            export_champion(settings, root / "baseline")
            candidate = train_and_register(
                data,
                settings,
                model_type="logreg",
                params={"C": 0.1},
                data_source="synthetic",
                promote=False,
            )
            client = MlflowClient(
                tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri
            )
            payload = {
                "bookings": json.loads(
                    make_synthetic(3, seed=7)[INPUT_COLUMNS].to_json(orient="records")
                )
            }

            def predict(api):
                response = api.post("/predict", json=payload)
                if response.status_code != 200:
                    raise RuntimeError("previsão falhou no exercício")
                return response.json()

            with TestClient(create_app(lambda: load_bundle(root / "baseline"))) as api:
                original = predict(api)
                registry.promote_to_champion(client, settings.model_name, candidate.model_version)
                # A API com snapshot continua na versão anterior, apesar da troca do alias.
                require(predict(api)["model_version"] == baseline.model_version)
            export_champion(settings, root / "candidate")
            with TestClient(create_app(lambda: load_bundle(root / "candidate"))) as api:
                require(predict(api)["model_version"] == candidate.model_version)
                restored_version = registry.rollback(client, settings.model_name)
                require(predict(api)["model_version"] == candidate.model_version)
            export_champion(settings, root / "restored")
            with TestClient(create_app(lambda: load_bundle(root / "restored"))) as api:
                restored = predict(api)
                require(api.get("/health/ready").json()["model_version"] == baseline.model_version)
            require(restored_version == baseline.model_version)
            require(restored["model_version"] == original["model_version"])
            np.testing.assert_allclose(
                [p["cancellation_probability"] for p in original["predictions"]],
                [p["cancellation_probability"] for p in restored["predictions"]],
                rtol=0,
                atol=0,
            )
            hashes = {name: digest(root / name) for name in ("baseline", "candidate", "restored")}
            require(hashes["baseline"] == hashes["restored"])
            result = {
                "schema_version": 1,
                "generated_at": datetime.now(UTC).isoformat(),
                "scope": "synthetic_local_temporary_registry",
                "scenario": "Retorno preventivo por decisão manual; não simula degradação medida.",
                "baseline_version": baseline.model_version,
                "candidate_version": candidate.model_version,
                "restored_version": restored_version,
                "bundle_sha256": hashes,
                "alias_change_kept_running_snapshot": True,
                "predictions_restored_exactly": True,
                "readiness_passed": True,
                "elapsed_seconds": round(time.perf_counter() - start, 3),
                "limitation": "TestClient local; não mede RTO de redeploy na Azure.",
            }
    finally:
        mlflow.set_tracking_uri(previous_tracking)
        mlflow.set_registry_uri(previous_registry)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.output), ensure_ascii=True))


if __name__ == "__main__":
    main()
