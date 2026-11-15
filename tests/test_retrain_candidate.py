from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pandas as pd
import pytest
from mlflow import MlflowClient

from hotelml import registry
from hotelml.bundle import export_champion, load_bundle
from hotelml.config import INPUT_COLUMNS
from hotelml.train import train_and_register

SCRIPTS = Path(__file__).parents[1] / "scripts"


@pytest.fixture
def retrain():
    return runpy.run_path(str(SCRIPTS / "retrain_candidate.py"))["retrain_candidate"]


@pytest.fixture
def production(raw_df, settings, tmp_path):
    """Modelo aprovado: treinado só com a parte mais antiga do histórico."""
    history = raw_df.sort_values(["arrival_date_year", "reservation_status_date"]).head(1500)
    train_and_register(history, settings, model_type="logreg", data_source="synthetic")
    bundle = tmp_path / "approved"
    export_champion(settings, bundle)
    source = tmp_path / "bookings.parquet"
    raw_df.to_parquet(source, index=False)
    return bundle, source


def aliases(settings):
    client = MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)
    names = (registry.CHAMPION, registry.CHALLENGER, registry.PREVIOUS)
    return {alias: registry.get_version(client, settings.model_name, alias) for alias in names}


def test_better_candidate_is_packaged_without_touching_the_champion(
    retrain, production, settings, tmp_path
):
    bundle, source = production
    evidence = tmp_path / "decision.json"
    evidence.write_text("{}")
    output = tmp_path / "candidate"
    # Ganho mínimo negativo garante o caminho de empacotamento, qualquer que seja o resultado.
    report = retrain(
        str(source), bundle, output, settings, trigger="drift", evidence=[evidence], min_delta=-1
    )
    assert report["candidate_better"] and report["approval"] == "pending_human_review"
    assert report["roc_auc_delta"] == pytest.approx(
        report["candidate"]["metrics_on_new_test"]["roc_auc"]
        - report["baseline"]["metrics_on_new_test"]["roc_auc"]
    )
    assert report["baseline"]["model_version"] == "1"
    assert report["candidate"]["model_version"] == "2"
    assert report["evidence_sha256"] == {evidence.as_posix(): hashlib.sha256(b"{}").hexdigest()}
    # O champion continua a ser a versão aprovada; o candidato é apenas challenger.
    assert aliases(settings) == {"champion": "1", "challenger": "2", "previous_champion": None}

    archive = output / report["release"]["archive"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == report["release"]["model_sha256"]
    # O pacote passa pela mesma verificação que o CD aplica antes de construir a imagem.
    unpack = runpy.run_path(str(SCRIPTS / "model_release.py"))["unpack"]
    manifest = unpack(archive, tmp_path / "unpacked", report["release"]["model_sha256"], "2")
    assert manifest["run_id"] == report["candidate"]["run_id"]
    candidate = load_bundle(tmp_path / "unpacked")
    sample = pd.read_parquet(source)[INPUT_COLUMNS].head(5)
    assert candidate.version == "2" and len(candidate.model.predict_proba(sample)) == 5
    assert json.loads((output / "report.json").read_text(encoding="utf-8")) == report
    with pytest.raises(FileExistsError):
        retrain(str(source), bundle, output, settings, trigger="drift")


def test_candidate_without_enough_gain_produces_no_release(retrain, production, settings, tmp_path):
    bundle, source = production
    output = tmp_path / "blocked"
    report = retrain(str(source), bundle, output, settings, trigger="manual", min_delta=1)
    assert not report["candidate_better"]
    assert report["release"] is None and report["approval"] == "not_applicable"
    assert sorted(p.name for p in output.iterdir()) == ["report.json"]
    assert aliases(settings)["champion"] == "1"


def test_decision_follows_the_measured_scores(retrain, production, settings, tmp_path):
    bundle, source = production
    report = retrain(str(source), bundle, tmp_path / "measured", settings, trigger="age")
    gain = (
        report["candidate"]["metrics_on_new_test"]["roc_auc"]
        > report["baseline"]["metrics_on_new_test"]["roc_auc"]
    )
    assert report["candidate_better"] == gain
    assert report["test_rows"] > 0 and report["train_rows"] > report["test_rows"]


def test_invalid_inputs_fail_before_registering_a_version(retrain, production, settings, tmp_path):
    bundle, source = production
    with pytest.raises(ValueError, match="gatilho"):
        retrain(str(source), bundle, tmp_path / "a", settings, trigger="capricho")
    with pytest.raises(FileNotFoundError):
        retrain(
            str(source),
            bundle,
            tmp_path / "b",
            settings,
            trigger="manual",
            evidence=[tmp_path / "ausente.json"],
        )
    with pytest.raises(FileNotFoundError):
        retrain(str(tmp_path / "nada.parquet"), bundle, tmp_path / "c", settings, trigger="manual")
    assert aliases(settings)["challenger"] == "1"
    assert not any((tmp_path / name).exists() for name in "abc")
