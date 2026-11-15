"""Gatilhos de retreino: transforma relatórios existentes numa recomendação auditável."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hotelml.quality import _utc


def load_policy(path: Path) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if (
        policy.get("schema_version") != 1
        or policy.get("status") not in {"proposed", "approved"}
        or not isinstance(policy.get("consecutive_drift_reports"), int)
        or policy["consecutive_drift_reports"] < 1
        or not 0.5 < policy.get("min_observed_roc_auc", 0) < 1
        or not isinstance(policy.get("max_model_age_days"), int)
        or policy["max_model_age_days"] < 1
    ):
        raise ValueError("política de retreino inválida")
    return policy


def retraining_signals(
    policy: dict[str, Any],
    *,
    now: str,
    trained_at: str,
    drift_reports: list[dict[str, Any]],
    quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Avalia drift persistente, qualidade observada e idade do modelo; nunca treina."""
    current, trained = _utc(now), _utc(trained_at)
    if trained > current:
        raise ValueError("data de treino posterior à avaliação")
    signals, notes = [], []

    # Um lote isolado com drift não basta: o sinal tem de persistir nos relatórios mais recentes.
    needed = policy["consecutive_drift_reports"]
    ordered = sorted(drift_reports, key=lambda report: _utc(report["generated_at"]))
    recent = ordered[-needed:]
    if len(recent) < needed:
        notes.append(f"drift: {len(recent)} de {needed} relatórios necessários")
    elif all(report["drift_detected"] is True for report in recent):
        columns = sorted(
            {c["column"] for report in recent for c in report["columns"] if c["drift_detected"]}
        )
        signals.append({"kind": "drift", "reports": needed, "columns": columns})

    if quality is None:
        notes.append("qualidade: nenhum relatório informado")
    elif quality.get("data_kind") != "observed":
        notes.append("qualidade: relatório sintético não aciona retreino")
    elif quality.get("status") != "ready" or quality["metrics"].get("roc_auc") is None:
        notes.append("qualidade: dados insuficientes ou ROC AUC indefinida")
    elif quality["metrics"]["roc_auc"] < policy["min_observed_roc_auc"]:
        signals.append(
            {
                "kind": "quality",
                "roc_auc": quality["metrics"]["roc_auc"],
                "minimum": policy["min_observed_roc_auc"],
                "outcome_coverage": quality.get("outcome_coverage"),
            }
        )

    age_days = (current - trained).days
    if age_days > policy["max_model_age_days"]:
        signals.append({"kind": "age", "days": age_days, "maximum": policy["max_model_age_days"]})

    approved = policy["status"] == "approved"
    return {
        "schema_version": 1,
        "evaluated_at": current.isoformat(),
        "trained_at": trained.isoformat(),
        "model_age_days": age_days,
        "policy_status": policy["status"],
        "status": "ready" if approved else "policy_not_approved",
        "signals": signals,
        "notes": notes,
        # Com política apenas proposta, os sinais são informativos e não há recomendação.
        "retrain_recommended": bool(signals) if approved else None,
        "interpretation": (
            "Recomendação para iniciar um retreino candidato; não treina, promove nem publica."
        ),
    }


def retraining_report(
    policy_path: Path,
    output: Path,
    *,
    trained_at: str,
    drift: list[Path],
    quality: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    inputs = {path.as_posix(): path.read_bytes() for path in [policy_path, *drift]}
    if quality is not None:
        inputs[quality.as_posix()] = quality.read_bytes()
    result = retraining_signals(
        load_policy(policy_path),
        now=now or datetime.now(UTC).isoformat(),
        trained_at=trained_at,
        drift_reports=[json.loads(inputs[path.as_posix()]) for path in drift],
        quality=json.loads(inputs[quality.as_posix()]) if quality is not None else None,
    )
    result["inputs_sha256"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result
