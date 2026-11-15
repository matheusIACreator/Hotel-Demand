from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from hotelml.cli import main
from hotelml.config import TARGET
from hotelml.outcomes import FINAL_STATUSES, export_outcomes, to_outcomes
from hotelml.quality import quality_report

AVAILABLE = "2026-02-01T08:00:00+00:00"


@pytest.fixture
def source():
    return pd.DataFrame(
        {
            "booking_id": ["b-1", "b-2", "b-3", "b-4"],
            "reservation_status": ["Canceled", "Check-Out", "No-Show", "Check-Out"],
            "reservation_status_date": ["2026-01-05", "2026-01-20", "2026-01-21", "2026-01-31"],
            "unrelated": [1, 2, 3, 4],
        }
    )


def test_final_statuses_follow_the_training_target(raw_df):
    # O gerador sintético e o dataset real marcam o alvo a partir do estado final.
    mapped = raw_df.reservation_status.map(FINAL_STATUSES)
    assert mapped.notna().all()
    assert (mapped == raw_df[TARGET]).all()
    assert FINAL_STATUSES["No-Show"] == 1


def test_maps_statuses_and_uses_availability_instant(source):
    outcomes, summary = to_outcomes(source, available_at=AVAILABLE)
    assert list(outcomes.columns) == ["booking_id", "is_canceled", "resolved_at"]
    assert outcomes.is_canceled.tolist() == [1, 0, 1, 0]
    # A data do evento não vira `resolved_at`: o desfecho só existe para avaliação na exportação.
    assert (outcomes.resolved_at == pd.Timestamp(AVAILABLE)).all()
    assert summary["final_outcomes"] == 4 and summary["pending_excluded"] == 0
    assert summary["canceled"] == 2 and summary["not_canceled"] == 2
    assert summary["status_counts"] == {"Canceled": 1, "Check-Out": 2, "No-Show": 1}
    assert summary["latest_status_date"] == "2026-01-31"
    assert "b-1" not in json.dumps(summary)


def test_declared_pending_reservations_never_become_outcomes(source):
    source.loc[3, "reservation_status"] = "Confirmed"
    source.loc[3, "reservation_status_date"] = None
    with pytest.raises(ValueError, match="não reconhecidos"):
        to_outcomes(source, available_at=AVAILABLE)
    outcomes, summary = to_outcomes(source, available_at=AVAILABLE, pending_statuses=["Confirmed"])
    assert outcomes.booking_id.tolist() == ["b-1", "b-2", "b-3"]
    assert summary["pending_excluded"] == 1 and summary["final_outcomes"] == 3


@pytest.mark.parametrize(
    "column,value,message",
    [
        ("reservation_status", None, "não reconhecidos"),
        ("reservation_status", "canceled", "não reconhecidos"),
        ("reservation_status_date", None, "ausente ou inválida"),
        ("reservation_status_date", "ontem", "ausente ou inválida"),
        ("reservation_status_date", "2026-02-02", "posterior"),
        ("booking_id", "b-1", "IDs"),
        ("booking_id", " ", "IDs"),
    ],
)
def test_inconsistent_source_is_rejected(source, column, value, message):
    source[column] = source[column].astype(object)
    source.loc[1, column] = value
    with pytest.raises(ValueError, match=message):
        to_outcomes(source, available_at=AVAILABLE)


def test_contract_requires_columns_timezone_and_real_pending_states(source):
    with pytest.raises(ValueError, match="colunas obrigatórias"):
        to_outcomes(source.drop(columns="reservation_status"), available_at=AVAILABLE)
    with pytest.raises(ValueError, match="fuso"):
        to_outcomes(source, available_at="2026-02-01T08:00:00")
    with pytest.raises(ValueError, match="pendente"):
        to_outcomes(source, available_at=AVAILABLE, pending_statuses=["Check-Out"])


@pytest.mark.parametrize("suffix", [".parquet", ".csv"])
def test_export_writes_contract_manifest_and_never_overwrites(source, tmp_path, suffix):
    path = tmp_path / f"source{suffix}"
    if suffix == ".csv":
        source.to_csv(path, index=False)
    else:
        source.to_parquet(path, index=False)
    output = tmp_path / "out" / "outcomes.parquet"
    summary = export_outcomes(path, output, available_at=AVAILABLE)
    written = pd.read_parquet(output)
    assert written.is_canceled.tolist() == [1, 0, 1, 0]
    assert str(written.resolved_at.dt.tz) == "UTC"
    manifest = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest == summary
    assert manifest["provenance"]["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        export_outcomes(path, output, available_at=AVAILABLE)


def test_invalid_source_leaves_no_partial_output(source, tmp_path):
    source.loc[0, "reservation_status"] = "Desconhecido"
    path = tmp_path / "source.parquet"
    source.to_parquet(path, index=False)
    output = tmp_path / "outcomes.parquet"
    with pytest.raises(ValueError):
        export_outcomes(path, output, available_at=AVAILABLE)
    assert not output.exists() and not output.with_suffix(".manifest.json").exists()


def test_exported_outcomes_feed_quality_with_matching_hash(source, tmp_path, capsys):
    path = tmp_path / "source.parquet"
    source.to_parquet(path, index=False)
    output = tmp_path / "outcomes.parquet"
    assert (
        main(
            ["outcomes", "--source", str(path), "--output", str(output)]
            + ["--available-at", AVAILABLE]
        )
        == 0
    )
    printed = json.loads(capsys.readouterr().out)

    probabilities = [0.9, 0.2, 0.4, 0.7]
    scores = pd.DataFrame(
        {
            "booking_id": source.booking_id,
            "batch_id": "batch",
            "model_name": "hotel",
            "model_version": "1",
            "threshold": 0.5,
            "scored_at": pd.Timestamp("2026-01-01"),
            "cancellation_probability": probabilities,
            "is_canceled": np.array(probabilities) >= 0.5,
        }
    )
    batch = tmp_path / "batch"
    (batch / "scores").mkdir(parents=True)
    scores.to_parquet(batch / "scores" / "part-0.parquet", index=False)
    run = {
        "schema_version": 1,
        "scores": "scores",
        "batch_id": "batch",
        "rows": 4,
        "threshold": 0.5,
        "model": {"model_name": "hotel", "model_version": "1", "run_id": "run"},
    }
    (batch / "run.json").write_text(json.dumps(run))
    (batch / "_SUCCESS").touch()
    report = quality_report(
        batch,
        output,
        tmp_path / "quality.json",
        as_of="2026-02-02T00:00:00Z",
        data_kind="synthetic",
        minimum=2,
    )
    assert report["matched_final_outcomes"] == 4 and report["outcome_coverage"] == 1
    # b-1 cancelou (0,9 certo), b-2 ficou (0,2 certo), b-3 no-show (0,4 erro), b-4 ficou (0,7 erro).
    assert report["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert report["provenance"]["outcomes_sha256"] == printed["provenance"]["outcomes_sha256"]

    # Antes da disponibilização declarada, os mesmos desfechos ainda não contam.
    early = quality_report(
        batch,
        output,
        tmp_path / "early.json",
        as_of="2026-02-01T07:59:59Z",
        data_kind="synthetic",
        minimum=2,
    )
    assert early["matched_final_outcomes"] == 0 and early["pending_outcomes"] == 4
