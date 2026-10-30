from __future__ import annotations

import json

import pandas as pd
import pytest

from hotelml.reference import export_reference, load_reference


def test_package_downloads_explicit_run_and_detects_tampering(tmp_path, monkeypatch, raw_df):
    bundle, package = tmp_path / "bundle", tmp_path / "reference"
    bundle.mkdir()
    identity = {"model_name": "hotel", "model_version": "7", "run_id": "exact-run"}
    (bundle / "manifest.json").write_text(json.dumps(identity))
    artifact = tmp_path / "source.parquet"
    raw_df.head(200).to_parquet(artifact)
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        return str(artifact)

    monkeypatch.setattr("mlflow.artifacts.download_artifacts", download)
    metadata = export_reference(bundle, package, "sqlite:///isolated.db")
    assert calls[0]["run_id"] == "exact-run"
    assert calls[0]["artifact_path"] == "reference/reference.parquet"
    assert calls[0]["tracking_uri"] == "sqlite:///isolated.db"
    loaded, actual = load_reference(bundle, package)
    assert actual == metadata
    pd.testing.assert_frame_equal(loaded, raw_df.head(200))
    with pytest.raises(FileExistsError):
        export_reference(bundle, package, "unused")
    (package / "reference.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        load_reference(bundle, package)
    (bundle / "manifest.json").write_text(json.dumps({**identity, "run_id": "other"}))
    with pytest.raises(ValueError, match="não corresponde"):
        load_reference(bundle, package)


def test_reference_export_rejects_incomplete_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="incompleto"):
        export_reference(tmp_path, tmp_path / "output", "unused")
