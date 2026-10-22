"""Snapshot de uma versão do registry para serving independente do backend de treino."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient

from hotelml.config import Settings
from hotelml.registry import CHAMPION


@dataclass(frozen=True)
class LoadedModel:
    model: Any
    name: str
    version: str


def load_bundle(root: Path) -> LoadedModel:
    """Carrega o snapshot local sem consultar o registry, para API e executores Spark."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    model = mlflow.sklearn.load_model(str(root / "model"))
    return LoadedModel(model, manifest["model_name"], manifest["model_version"])


def export_champion(settings: Settings, output: Path) -> dict[str, str]:
    """Resolve o alias uma vez e copia a versão exata; nunca sobrescreve um bundle."""
    if output.exists():
        raise FileExistsError(f"destino já existe: {output}")
    mlflow.set_tracking_uri(settings.tracking_uri)
    mlflow.set_registry_uri(settings.tracking_uri)
    client = MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)
    version = client.get_model_version_by_alias(settings.model_name, CHAMPION)
    manifest = {
        "model_name": settings.model_name,
        "model_version": str(version.version),
        "run_id": str(version.run_id),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        # Versão explícita impede que uma promoção concorrente troque o modelo exportado.
        local = mlflow.artifacts.download_artifacts(
            artifact_uri=f"models:/{settings.model_name}/{version.version}",
            dst_path=str(Path(tmp) / "download"),
        )
        shutil.copytree(local, stage / "model")
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        stage.rename(output)
    return manifest
