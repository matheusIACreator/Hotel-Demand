"""Gera os casos do eval da explicação: fatos reais do modelo sobre reservas sintéticas.

Cada caso é o JSON de fatos que `hotelml narrate` envia ao modelo de linguagem. As reservas vêm
de `make_synthetic` (nenhum dado do dataset real entra no repositório) e são pontuadas e
atribuídas pelo bundle e pela referência indicados. Casos-limite são edições declaradas de
fatos reais. Não chama nenhuma API.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from hotelml.api import Booking
from hotelml.bundle import load_bundle
from hotelml.config import INPUT_COLUMNS
from hotelml.explain import explain_booking
from hotelml.narrative import build_facts
from hotelml.reference import load_reference
from hotelml.synthetic import make_synthetic

BANDS = [
    (0.0, 0.2, "baixa"),
    (0.2, 0.5, "media-baixa"),
    (0.5, 0.8, "media-alta"),
    (0.8, 1.01, "alta"),
]


def _edited(case: dict, case_id: str, tag: str, note: str, **changes) -> dict:
    facts = copy.deepcopy(case["facts"]) | changes
    facts["other_fields"] = len(INPUT_COLUMNS) - len(facts["factors"])
    return {"id": case_id, "tags": [tag, "editado"], "note": note, "facts": facts}


def build(bundle: Path, reference: Path, per_band: int, seed: int) -> tuple[list[dict], dict]:
    loaded = load_bundle(bundle)
    frame, metadata = load_reference(bundle, reference)
    identity = {key: metadata[key] for key in ("model_name", "model_version", "run_id")}
    pool = make_synthetic(600, seed=seed)[INPUT_COLUMNS]
    records = json.loads(pool.to_json(orient="records"))
    bookings = [Booking.model_validate(record).model_dump() for record in records]
    scores = np.asarray(loaded.model.predict_proba(pd.DataFrame(bookings, columns=INPUT_COLUMNS)))
    probabilities = scores[:, 1]

    cases = []
    for low, high, band in BANDS:
        # Espalha a seleção dentro da faixa em vez de pegar as primeiras reservas.
        inside = [i for i in np.argsort(probabilities) if low <= probabilities[i] < high]
        picks = [inside[int(k)] for k in np.linspace(0, len(inside) - 1, per_band)]
        for order, index in enumerate(picks, 1):
            report = explain_booking(
                loaded.model,
                bookings[index],
                frame,
                identity,
                reference_sha256=metadata["reference_sha256"],
            )
            facts = build_facts(report)
            leader = "com-lider" if facts["leading_factor"] else "sem-lider"
            cases.append({"id": f"{band}-{order:02d}", "tags": [band, leader], "facts": facts})

    by_id = {case["id"]: case for case in cases}
    high, low = by_id["alta-03"], by_id["baixa-03"]
    first = high["facts"]["factors"][0]
    null_factor = {
        "field": "company",
        "label": "Empresa",
        "value": None,
        "direction": "reduz",
        "effect_pp": 2.4,
    }
    cases += [
        _edited(
            high,
            "limite-sem-fatores",
            "limite",
            "Nenhum fator com efeito claro.",
            factors=[],
            leading_factor=None,
        ),
        _edited(
            high,
            "limite-um-fator",
            "limite",
            "Um único fator, que é o líder.",
            factors=[first],
            leading_factor=first["field"],
        ),
        _edited(
            high,
            "limite-no-limiar",
            "limite",
            "Probabilidade exatamente no limiar.",
            probability_pct=50.0,
            decision="cancelamento provável",
        ),
        _edited(
            low,
            "limite-abaixo-do-limiar",
            "limite",
            "Logo abaixo do limiar.",
            probability_pct=49.9,
            decision="manutenção provável",
        ),
        _edited(
            low,
            "limite-valor-ausente",
            "limite",
            "Fator cujo valor na reserva é nulo.",
            factors=[*low["facts"]["factors"][:2], null_factor],
        ),
        _edited(
            low,
            "limite-igual-a-base",
            "limite",
            "Estimativa igual à das reservas típicas.",
            probability_pct=low["facts"]["baseline_pct"],
        ),
    ]
    provenance = {
        "generator": "scripts/build_explain_cases.py",
        "bookings": f"make_synthetic(600, seed={seed})",
        "model": identity,
        "reference_sha256": metadata["reference_sha256"],
        "attribution": {"method": "permutation_shapley", "permutations": 1000, "seed": 0},
    }
    return cases, provenance


def review(cases: list[dict], provenance: dict) -> str:
    lines = [
        "# Casos do eval da explicação de previsões",
        "",
        f"{len(cases)} casos. Cada um é o JSON de fatos enviado ao modelo de linguagem.",
        f"Reservas: `{provenance['bookings']}`; modelo `{provenance['model']['model_name']}` "
        f"versão {provenance['model']['model_version']}. Casos `editado` são alterações "
        "declaradas de fatos reais.",
        "",
        "| Caso | Faixa | Prob. | Base | Decisão | Fatores | Líder | Nota |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        facts = case["facts"]
        lines.append(
            f"| `{case['id']}` | {case['tags'][0]} | {facts['probability_pct']}% | "
            f"{facts['baseline_pct']}% | {facts['decision']} | {len(facts['factors'])} | "
            f"{facts['leading_factor'] or '—'} | {case.get('note', '')} |"
        )
    for case in cases:
        lines += [
            "",
            f"## {case['id']}",
            "",
            "| Campo | Valor | Sentido | Efeito (p.p.) |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| {f['label']} (`{f['field']}`) | {f['value']} | {f['direction']} "
            f"| {f['effect_pp']} |"
            for f in case["facts"]["factors"]
        ] or ["| (nenhum fator) | | | |"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("model-bundle"))
    parser.add_argument("--reference", type=Path, default=Path("data/reference-v1"))
    parser.add_argument("--output", type=Path, default=Path("evals/explain_booking"))
    parser.add_argument("--per-band", type=int, default=6)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    cases, provenance = build(args.bundle, args.reference, args.per_band, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "cases.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for case in cases:
            stream.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    (args.output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    (args.output / "CASES.md").write_text(review(cases, provenance), encoding="utf-8", newline="\n")
    print(f"{len(cases)} casos em {args.output}")


if __name__ == "__main__":
    main()
