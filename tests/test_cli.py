from __future__ import annotations

import json

import pytest

from hotelml.cli import main


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("MODEL_NAME", "cli-model")


def test_train_status_and_rollback_flow(capsys, tmp_path) -> None:
    assert main(["train", "--source", "synthetic", "--rows", "3000"]) == 0
    out = json.loads(capsys.readouterr().out.split("}\n", 1)[0] + "}")
    assert out["promoted"] is True

    assert main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["champion"] == out["version"]

    assert main(["export", "--output", str(tmp_path / "bundle")]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["model_version"] == out["version"]

    assert (
        main(
            [
                "reference",
                "--bundle",
                str(tmp_path / "bundle"),
                "--output",
                str(tmp_path / "reference"),
            ]
        )
        == 0
    )
    reference = json.loads(capsys.readouterr().out)
    assert reference["run_id"] == exported["run_id"]
    assert len(reference["reference_sha256"]) == 64

    assert main(["rollback"]) == 1  # só há uma versão: nada para reverter


def test_missing_data_source_raises() -> None:
    with pytest.raises(FileNotFoundError):
        main(["train", "--source", "/nao/existe.parquet"])
