"""Retreino candidato: treina sem promover, compara com o bundle aprovado e empacota.

O candidato é registrado como `challenger`. O bundle aprovado é reavaliado no teste temporal
dos dados novos, e só um candidato melhor é exportado, com o SHA-256 que o CD exige. Não troca
o champion, não altera a API publicada e não substitui a aprovação humana da release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from hotelml.bundle import export_version, load_bundle
from hotelml.config import INPUT_COLUMNS, TARGET, Settings
from hotelml.data import load_raw
from hotelml.features import clean_training_data, time_split
from hotelml.metrics import evaluate
from hotelml.train import train_and_register

TRIGGERS = ("manual", "drift", "quality", "age")


def retrain_candidate(
    source: str,
    baseline_bundle: Path,
    output: Path,
    settings: Settings,
    *,
    trigger: str,
    evidence: list[Path] | None = None,
    min_delta: float = 0.0,
    model_type: str = "hgb",
    test_fraction: float = 0.2,
) -> dict:
    if trigger not in TRIGGERS:
        raise ValueError(f"gatilho inválido: use {', '.join(TRIGGERS)}")
    if output.exists():
        raise FileExistsError(output)
    # Lê tudo o que pode falhar antes de registrar uma versão nova.
    proofs = {path.as_posix(): path.read_bytes() for path in evidence or []}
    baseline = load_bundle(baseline_bundle)
    baseline_manifest = json.loads((baseline_bundle / "manifest.json").read_text(encoding="utf-8"))
    raw = load_raw(source, settings)

    trained = train_and_register(
        raw,
        settings,
        model_type=model_type,
        test_fraction=test_fraction,
        data_source=source,
        promote=False,
    )
    # Mesma limpeza e mesmo corte do treino: os dois modelos são medidos nas mesmas reservas.
    train, test, cutoff = time_split(clean_training_data(raw), test_fraction)
    baseline_metrics = evaluate(baseline.model, test[INPUT_COLUMNS], test[TARGET])
    delta = trained.metrics["roc_auc"] - baseline_metrics["roc_auc"]
    better = delta > min_delta

    output.mkdir(parents=True)
    release = None
    if better:
        manifest = export_version(settings, trained.model_version, output / "candidate-bundle")
        archive = output / "model-bundle.tar.gz"
        # Mesmo conteúdo de `model_release.py pack`: só manifesto e modelo.
        with tarfile.open(archive, "x:gz") as stream:
            for name in ("manifest.json", "model"):
                stream.add(output / "candidate-bundle" / name, arcname=name)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        release = {
            "archive": archive.name,
            "model_sha256": digest,
            "model_version": manifest["model_version"],
        }
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "trigger": trigger,
        "evidence_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in proofs.items()},
        "data_source": source,
        "train_rows": len(train),
        "test_rows": len(test),
        "test_cutoff": cutoff.date().isoformat(),
        "baseline": {**baseline_manifest, "metrics_on_new_test": baseline_metrics},
        "candidate": {
            "model_name": settings.model_name,
            "model_version": trained.model_version,
            "run_id": trained.run_id,
            "alias": "challenger",
            "metrics_on_new_test": trained.metrics,
        },
        "roc_auc_delta": delta,
        "min_delta": min_delta,
        "candidate_better": better,
        "release": release,
        "approval": "pending_human_review" if better else "not_applicable",
        "limitation": (
            "Um único teste temporal; ganho no teste não é aprovação de release. Se o bundle "
            "aprovado tiver sido treinado com reservas posteriores ao corte, a comparação o "
            "favorece. O champion e a API publicada não são alterados."
        ),
    }
    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="hf | synthetic | caminho .parquet/.csv")
    parser.add_argument("--baseline-bundle", type=Path, default=Path("model-bundle"))
    parser.add_argument("--output", type=Path, required=True, help="diretório novo")
    parser.add_argument("--trigger", required=True, choices=TRIGGERS)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--min-delta", type=float, default=0.0, help="ganho mínimo de ROC AUC")
    parser.add_argument("--model", default="hgb", choices=["hgb", "logreg"])
    args = parser.parse_args()
    report = retrain_candidate(
        args.source,
        args.baseline_bundle,
        args.output,
        Settings(),
        trigger=args.trigger,
        evidence=args.evidence,
        min_delta=args.min_delta,
        model_type=args.model,
    )
    keys = ("candidate_better", "roc_auc_delta", "release", "approval")
    print(json.dumps({key: report[key] for key in keys}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
