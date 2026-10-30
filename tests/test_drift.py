from __future__ import annotations

import json

import numpy as np
import pytest

from hotelml.cli import main
from hotelml.config import INPUT_COLUMNS
from hotelml.drift import compare, report
from hotelml.synthetic import make_synthetic


@pytest.fixture
def sample():
    return make_synthetic(600)[INPUT_COLUMNS]


def test_same_data_and_row_order_do_not_drift(sample):
    result = compare(sample, sample.sample(frac=1, random_state=3))
    assert not result["drift_detected"]
    assert all(c["score"] == 0 for c in result["columns"])


def test_numeric_categorical_and_missing_shifts(sample):
    current = sample.copy()
    current["lead_time"] += 1000
    current["hotel"] = "CATEGORIA_NOVA_PRIVADA"
    current["company"] = 999.0
    result = compare(sample, current)
    found = {c["column"]: c for c in result["columns"]}
    assert all(found[c]["drift_detected"] for c in ("lead_time", "hotel", "company"))
    assert "CATEGORIA_NOVA_PRIVADA" not in json.dumps(result)
    assert all(np.isfinite(c["score"]) for c in result["columns"])


@pytest.mark.parametrize("value", [0, 10, 20])
def test_constant_numeric_reference_detects_both_tails(sample, value):
    sample["lead_time"] = 10
    current = sample.copy()
    current["lead_time"] = value
    column = next(c for c in compare(sample, current)["columns"] if c["column"] == "lead_time")
    assert column["drift_detected"] == (value != 10)


def test_all_missing_reference_and_current(sample):
    sample["company"] = None
    assert not compare(sample, sample)["drift_detected"]
    current = sample.copy()
    current["company"] = 1.0
    assert compare(sample, current)["drift_detected"]


def test_invalid_and_insufficient_inputs_are_rejected(sample):
    with pytest.raises(ValueError, match="insuficiente"):
        compare(sample.head(3), sample)
    with pytest.raises(ValueError, match="colunas"):
        compare(sample.drop(columns="hotel"), sample)
    sample.loc[0, "hotel"] = "DADO_PRIVADO"
    sample.loc[0, "adr"] = -1
    with pytest.raises(ValueError, match="posição 0") as error:
        compare(sample, sample)
    assert "DADO_PRIVADO" not in str(error.value)


@pytest.mark.parametrize(
    "options",
    [{"minimum": 0}, {"psi_threshold": float("nan")}, {"tv_threshold": 2}, {"psi_threshold": 0}],
)
def test_invalid_parameters(sample, options):
    with pytest.raises(ValueError):
        compare(sample, sample, **options)


def test_report_provenance_no_overwrite_and_cli_exit_code(sample, tmp_path, capsys):
    ref, cur, out = (tmp_path / name for name in ("ref.parquet", "cur.parquet", "out.json"))
    sample.to_parquet(ref)
    current = sample.copy()
    current["lead_time"] += 1000
    current.to_parquet(cur)
    args = ["drift", "--reference", str(ref), "--current", str(cur), "--output", str(out)]
    assert main(args) == 2
    result = json.loads(out.read_text(encoding="utf-8"))
    assert len(result["reference_sha256"]) == 64
    assert result["reference_sha256"] != result["current_sha256"]
    with pytest.raises(FileExistsError):
        report(ref, cur, out)
    assert "drift_detected" in capsys.readouterr().out
