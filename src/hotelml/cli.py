"""Interface de linha de comando: treinar, consultar estado e fazer rollback."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from mlflow import MlflowClient

from hotelml import registry
from hotelml.config import Settings
from hotelml.data import load_raw
from hotelml.train import train_and_register


def _cmd_export(args: argparse.Namespace) -> int:
    from hotelml.bundle import export_champion

    manifest = export_champion(Settings(), Path(args.output))
    print(json.dumps(manifest, indent=2))
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    settings = Settings()
    raw = load_raw(args.source, settings, synthetic_rows=args.rows)
    result = train_and_register(
        raw,
        settings,
        model_type=args.model,
        data_source=args.source,
        promote=not args.no_promote,
        min_delta=args.min_delta,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "version": result.model_version,
                "metrics": {k: round(v, 4) for k, v in result.metrics.items()},
                "promoted": result.decision.promoted if result.decision else None,
                "reason": result.decision.reason if result.decision else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_status(_: argparse.Namespace) -> int:
    settings = Settings()
    client = MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)
    state = {
        alias: registry.get_version(client, settings.model_name, alias)
        for alias in (registry.CHAMPION, registry.CHALLENGER, registry.PREVIOUS)
    }
    print(json.dumps({"model": settings.model_name, **state}, indent=2))
    return 0


def _cmd_rollback(_: argparse.Namespace) -> int:
    settings = Settings()
    client = MlflowClient(tracking_uri=settings.tracking_uri, registry_uri=settings.tracking_uri)
    try:
        version = registry.rollback(client, settings.model_name)
    except registry.RollbackError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"rollback concluído: champion agora é a versão {version}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hotelml", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="treina, registra e tenta promover um modelo")
    train.add_argument(
        "--source", default="synthetic", help="hf | synthetic | caminho .parquet/.csv"
    )
    train.add_argument("--model", default="hgb", choices=["hgb", "logreg"])
    train.add_argument("--rows", type=int, default=20000, help="linhas (só para synthetic)")
    train.add_argument("--no-promote", action="store_true")
    train.add_argument("--min-delta", type=float, default=0.0, help="ganho mínimo de roc_auc")
    train.set_defaults(func=_cmd_train)

    sub.add_parser("status", help="mostra versões champion/challenger").set_defaults(
        func=_cmd_status
    )
    sub.add_parser("rollback", help="volta o champion para a versão anterior").set_defaults(
        func=_cmd_rollback
    )
    export = sub.add_parser("export", help="exporta o champion para uma imagem de serving")
    export.add_argument("--output", default="model-bundle")
    export.set_defaults(func=_cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=False)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
