"""Pacote de referência separado do serving, vinculado ao run explícito do bundle."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path

import mlflow
import pandas as pd

IDENTITY = ("model_name", "model_version", "run_id")


def export_reference(bundle: Path, output: Path, tracking_uri: str) -> dict:
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if not all(isinstance(manifest.get(k), str) and manifest[k] for k in IDENTITY):
        raise ValueError("manifesto do bundle incompleto")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        root = Path(directory)
        downloaded = mlflow.artifacts.download_artifacts(
            run_id=manifest["run_id"],
            artifact_path="reference/reference.parquet",
            tracking_uri=tracking_uri,
            dst_path=str(root / "download"),
        )
        stage = root / "package"
        stage.mkdir()
        shutil.copyfile(downloaded, stage / "reference.parquet")
        metadata = {k: manifest[k] for k in IDENTITY}
        metadata["reference_sha256"] = hashlib.sha256(
            (stage / "reference.parquet").read_bytes()
        ).hexdigest()
        (stage / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        stage.rename(output)
    return metadata


def load_reference(bundle: Path, package: Path) -> tuple[pd.DataFrame, dict]:
    expected = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    if not all(expected.get(k) and metadata.get(k) == expected[k] for k in IDENTITY):
        raise ValueError("referência não corresponde ao modelo e run do bundle")
    data = (package / "reference.parquet").read_bytes()
    if hashlib.sha256(data).hexdigest() != metadata.get("reference_sha256"):
        raise ValueError("hash da referência divergente")
    return pd.read_parquet(io.BytesIO(data)), metadata
