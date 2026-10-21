"""Operações de Model Registry baseadas em aliases do MLflow.

Aliases usados:
- `challenger`: versão recém-treinada, aguardando avaliação.
- `champion`: versão em produção.
- `previous_champion`: versão anterior, usada para rollback instantâneo.

Rollback e promoção só mexem em aliases: não há rebuild nem redeploy de artefatos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from hotelml.metrics import evaluate

log = logging.getLogger(__name__)

CHAMPION = "champion"
CHALLENGER = "challenger"
PREVIOUS = "previous_champion"


class RollbackError(RuntimeError):
    """Não há versão anterior para voltar."""


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    reason: str
    challenger_version: str
    challenger_score: float
    champion_version: str | None
    champion_score: float | None


def get_version(client: MlflowClient, name: str, alias: str) -> str | None:
    """Versão apontada por um alias, ou None se o alias não existir."""
    try:
        return str(client.get_model_version_by_alias(name, alias).version)
    except MlflowException:
        return None


def set_challenger(client: MlflowClient, name: str, version: str) -> None:
    client.set_registered_model_alias(name, CHALLENGER, version)


def promote_to_champion(client: MlflowClient, name: str, version: str) -> None:
    """Torna `version` o champion, guardando o champion anterior para rollback."""
    current = get_version(client, name, CHAMPION)
    if current is not None and current != version:
        client.set_registered_model_alias(name, PREVIOUS, current)
    client.set_registered_model_alias(name, CHAMPION, version)
    log.info("champion de %s agora é a versão %s (anterior: %s)", name, version, current)


def rollback(client: MlflowClient, name: str) -> str:
    """Volta o champion para a versão anterior. Retorna a versão que ficou em produção.

    A operação troca champion e previous_champion, então executá-la duas vezes desfaz o rollback.
    """
    previous = get_version(client, name, PREVIOUS)
    current = get_version(client, name, CHAMPION)
    if previous is None or current is None:
        raise RollbackError(f"{name}: não há versão anterior registrada para rollback")
    client.set_registered_model_alias(name, CHAMPION, previous)
    client.set_registered_model_alias(name, PREVIOUS, current)
    log.warning("rollback de %s: versão %s -> %s", name, current, previous)
    return previous


def promote_if_better(
    client: MlflowClient,
    name: str,
    version: str,
    candidate_score: float,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    metric: str = "roc_auc",
    min_delta: float = 0.0,
) -> PromotionDecision:
    """Promove o candidato se superar o champion atual em `metric` por mais de `min_delta`.

    Sem champion existente, o primeiro modelo é promovido automaticamente.
    O champion é reavaliado no MESMO conjunto de teste, para a comparação ser justa.
    """
    champion_version = get_version(client, name, CHAMPION)
    if champion_version is None:
        promote_to_champion(client, name, version)
        return PromotionDecision(
            True, "sem champion: primeiro modelo promovido", version, candidate_score, None, None
        )
    if champion_version == version:
        return PromotionDecision(
            False,
            "versão já é o champion",
            version,
            candidate_score,
            champion_version,
            candidate_score,
        )

    champion_model = mlflow.sklearn.load_model(f"models:/{name}@{CHAMPION}")
    champion_score = evaluate(champion_model, x_test, y_test)[metric]

    if candidate_score > champion_score + min_delta:
        promote_to_champion(client, name, version)
        reason = f"{metric} {candidate_score:.4f} > champion {champion_score:.4f} + {min_delta}"
        promoted = True
    else:
        reason = (
            f"{metric} {candidate_score:.4f} não supera champion {champion_score:.4f} + {min_delta}"
        )
        promoted = False
    return PromotionDecision(
        promoted, reason, version, candidate_score, champion_version, champion_score
    )
