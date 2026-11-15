from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from hotelml.bundle import export_champion
from hotelml.cli import main
from hotelml.config import INPUT_COLUMNS
from hotelml.explain import explain_booking, shapley_values
from hotelml.reference import export_reference
from hotelml.train import train_and_register


@pytest.fixture
def background():
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "a": rng.normal(10, 2, 400),
            "b": rng.integers(0, 5, 400).astype(float),
            "kind": rng.choice(["x", "y"], 400),
            "unused": rng.normal(0, 1, 400),
        }
    )


def additive(frame: pd.DataFrame) -> np.ndarray:
    # Modelo aditivo: o valor de Shapley exato é o efeito do campo menos a média da referência.
    return (0.02 * frame.a + 0.05 * frame.b + 0.1 * (frame.kind == "y")).to_numpy(dtype=float)


def test_additive_model_recovers_exact_contributions(background):
    booking = {"a": 14.0, "b": 4.0, "kind": "y", "unused": 9.0}
    result = shapley_values(additive, booking, background, permutations=400, seed=1)
    contributions = result["contributions"]
    sampled = background.iloc[np.random.default_rng(1).integers(0, 400, 400)]
    assert contributions["a"]["value"] == pytest.approx(0.02 * (14 - sampled.a.mean()))
    assert contributions["b"]["value"] == pytest.approx(0.05 * (4 - sampled.b.mean()))
    assert contributions["kind"]["value"] == pytest.approx(0.1 * (1 - (sampled.kind == "y").mean()))
    # Um campo que o modelo ignora não recebe contribuição, por maior que seja o valor.
    assert contributions["unused"] == {"value": 0.0, "std_error": 0.0}
    assert result["probability"] == pytest.approx(additive(pd.DataFrame([booking]))[0])


def test_contributions_sum_to_the_gap_from_the_baseline(background):
    def interacting(frame: pd.DataFrame) -> np.ndarray:
        return (0.001 * frame.a * frame.b + 0.2 * (frame.kind == "y") * (frame.a > 10)).to_numpy()

    booking = {"a": 13.0, "b": 3.0, "kind": "y", "unused": 0.0}
    result = shapley_values(interacting, booking, background, permutations=300, seed=5)
    total = sum(item["value"] for item in result["contributions"].values())
    assert total == pytest.approx(result["probability"] - result["baseline_probability"])
    assert result["additivity_gap"] < 1e-12
    # Com interação há variância entre permutações, e ela é reportada.
    assert result["contributions"]["a"]["std_error"] > 0


def test_same_seed_is_reproducible_and_missing_values_are_supported(background):
    booking = {"a": None, "b": 2.0, "kind": "x", "unused": 0.0}

    def tolerant(frame: pd.DataFrame) -> np.ndarray:
        assert pd.api.types.is_numeric_dtype(frame.a) and frame.kind.map(type).eq(str).all()
        return (0.02 * frame.a.fillna(0) + 0.05 * frame.b).to_numpy(dtype=float)

    first = shapley_values(tolerant, booking, background, permutations=50, seed=7)
    assert first == shapley_values(tolerant, booking, background, permutations=50, seed=7)
    assert first != shapley_values(tolerant, booking, background, permutations=50, seed=8)
    assert first["contributions"]["a"]["value"] < 0


def test_invalid_inputs_are_rejected(background):
    booking = {"a": 1.0, "b": 1.0, "kind": "x", "unused": 0.0}
    with pytest.raises(ValueError, match="mesmos campos"):
        shapley_values(additive, {**booking, "extra": 1}, background)
    with pytest.raises(ValueError, match="permutações"):
        shapley_values(additive, booking, background, permutations=1)
    with pytest.raises(ValueError, match="vazia"):
        shapley_values(additive, booking, background.head(0))
    with pytest.raises(ValueError, match="inválidas"):
        shapley_values(lambda frame: np.full(len(frame), np.nan), booking, background)


@pytest.fixture
def trained(raw_df, settings, tmp_path):
    train_and_register(raw_df, settings, data_source="synthetic")
    bundle, reference = tmp_path / "bundle", tmp_path / "reference"
    export_champion(settings, bundle)
    export_reference(bundle, reference, settings.tracking_uri)
    booking = json.loads(raw_df[INPUT_COLUMNS].head(1).to_json(orient="records"))[0]
    return bundle, reference, booking


def test_real_pipeline_matches_the_model_probability(trained, raw_df):
    from hotelml.bundle import load_bundle
    from hotelml.reference import load_reference

    bundle, reference, booking = trained
    loaded = load_bundle(bundle)
    frame, metadata = load_reference(bundle, reference)
    report = explain_booking(
        loaded.model,
        booking,
        frame,
        {"model_name": loaded.name, "model_version": loaded.version, "run_id": "run"},
        reference_sha256=metadata["reference_sha256"],
        permutations=60,
    )
    direct = loaded.model.predict_proba(pd.DataFrame([booking], columns=INPUT_COLUMNS))[0, 1]
    assert report["probability"] == pytest.approx(direct)
    assert report["is_canceled"] == (direct >= 0.5)
    assert [f["field"] for f in report["factors"]] != INPUT_COLUMNS
    assert sorted(f["field"] for f in report["factors"]) == sorted(INPUT_COLUMNS)
    magnitudes = [abs(f["contribution"]) for f in report["factors"]]
    assert magnitudes == sorted(magnitudes, reverse=True)
    total = sum(f["contribution"] for f in report["factors"])
    assert total == pytest.approx(report["probability"] - report["baseline_probability"])
    assert report["additivity_gap"] < 1e-9


def test_cli_validates_the_booking_and_never_overwrites(trained, tmp_path, capsys):
    bundle, reference, booking = trained
    path = tmp_path / "booking.json"
    path.write_text(json.dumps(booking))
    output = tmp_path / "factors.json"
    command = ["explain", "--bundle", str(bundle), "--reference", str(reference)]
    command += ["--booking", str(path), "--permutations", "20"]
    assert main([*command, "--output", str(output)]) == 0
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert printed["probability"] == saved["probability"]
    assert saved["method"] == "permutation_shapley" and saved["permutations"] == 20
    with pytest.raises(FileExistsError):
        main([*command, "--output", str(output)])
    path.write_text(json.dumps({**booking, "adr": -1}))
    with pytest.raises(ValueError):
        main([*command, "--output", str(tmp_path / "invalid.json")])
    assert not (tmp_path / "invalid.json").exists()
