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


def _cmd_drift(args: argparse.Namespace) -> int:
    from hotelml.drift import report

    result = report(
        Path(args.reference),
        Path(args.current),
        Path(args.output),
        minimum=args.minimum_rows,
        psi_threshold=args.psi_threshold,
        tv_threshold=args.tv_threshold,
    )
    print(json.dumps({"report": args.output, "drift_detected": result["drift_detected"]}))
    return 2 if result["drift_detected"] else 0


def _cmd_reference(args: argparse.Namespace) -> int:
    from hotelml.reference import export_reference

    print(
        json.dumps(export_reference(Path(args.bundle), Path(args.output), Settings().tracking_uri))
    )
    return 0


def _cmd_quality(args: argparse.Namespace) -> int:
    from hotelml.quality import quality_report

    result = quality_report(
        Path(args.batch),
        Path(args.outcomes),
        Path(args.output),
        as_of=args.as_of,
        data_kind=args.data_kind,
        minimum=args.minimum_rows,
    )
    print(json.dumps({"report": args.output, "status": result["status"]}))
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    from hotelml.explain import explain_report

    result = explain_report(
        Path(args.bundle),
        Path(args.reference),
        Path(args.booking),
        Path(args.output),
        permutations=args.permutations,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "report": args.output,
                "probability": result["probability"],
                "baseline_probability": result["baseline_probability"],
                "top_factors": [factor["field"] for factor in result["factors"][:5]],
            }
        )
    )
    return 0


def _cmd_narrate(args: argparse.Namespace) -> int:
    from hotelml.llm import cost_usd, file_tracer_provider, load_prices, load_prompt, narrate
    from hotelml.narrative import build_facts, template_explanation

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    facts = build_facts(json.loads(Path(args.factors).read_text(encoding="utf-8")))
    prompt = load_prompt("explain_booking", args.prompt_version)
    prices = load_prices(Path(args.prices))
    # Falha cedo se o modelo do prompt não tiver preço: nenhuma chamada sem custo conhecido.
    cost_usd({"input_tokens": 0, "output_tokens": 0}, prompt.model, prices)
    if args.dry_run:
        result = {
            "schema_version": 1,
            "status": "dry_run",
            "source": "template",
            "explanation": template_explanation(facts).model_dump(),
            "facts": facts,
            "prompt": {"id": prompt.prompt_id, "version": prompt.version, "sha256": prompt.sha256},
            "model_requested": prompt.model,
        }
    else:
        import anthropic

        provider = file_tracer_provider(Path(args.trace_file)) if args.trace_file else None
        client = anthropic.Anthropic(
            open_telemetry={"tracer_provider": provider} if provider else False
        )
        try:
            result = narrate(facts, prompt, client, prices, tracer_provider=provider)
        except anthropic.AuthenticationError:
            print("erro: credencial da Anthropic ausente ou inválida", file=sys.stderr)
            return 1
        except anthropic.RateLimitError:
            print("erro: limite de taxa da API; tente novamente mais tarde", file=sys.stderr)
            return 1
        except anthropic.APIStatusError as exc:
            print(f"erro: a API respondeu {exc.status_code}", file=sys.stderr)
            return 1
        except anthropic.APIConnectionError:
            print("erro: não foi possível contactar a API da Anthropic", file=sys.stderr)
            return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    summary = {key: result.get(key) for key in ("status", "source", "cost_usd", "model_served")}
    print(json.dumps({"report": args.output, **summary}))
    # Um texto recusado pelos guardrails não é erro de execução: o relatório traz o motivo.
    return 0


def _cmd_outcomes(args: argparse.Namespace) -> int:
    from hotelml.outcomes import export_outcomes

    summary = export_outcomes(
        Path(args.source),
        Path(args.output),
        available_at=args.available_at,
        pending_statuses=args.pending_status,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def _cmd_retrain_check(args: argparse.Namespace) -> int:
    from hotelml.retraining import retraining_report

    result = retraining_report(
        Path(args.policy),
        Path(args.output),
        trained_at=args.trained_at,
        drift=[Path(path) for path in args.drift],
        quality=Path(args.quality) if args.quality else None,
        now=args.as_of,
    )
    print(
        json.dumps(
            {
                "report": args.output,
                "status": result["status"],
                "retrain_recommended": result["retrain_recommended"],
                "signals": [signal["kind"] for signal in result["signals"]],
            }
        )
    )
    return 2 if result["retrain_recommended"] else 0


def _cmd_slo(args: argparse.Namespace) -> int:
    from hotelml.slo import slo_report

    result = slo_report(
        Path(args.input),
        Path(args.output),
        input_format=args.input_format,
        start=args.start,
        end=args.end,
        availability_target=args.availability_target,
        latency_target=args.latency_target,
        latency_ms=args.latency_ms,
        data_kind=args.data_kind,
        complete_window=args.complete_window,
        minimum=args.minimum_requests,
    )
    print(json.dumps({"report": args.output, "status": result["status"]}))
    if result["status"] != "ready":
        return 0
    return 2 if not result["availability"]["met"] or not result["latency"]["met"] else 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from hotelml.probe import run_probe

    result = run_probe(
        args.url,
        Path(args.output),
        target=args.target,
        count=args.count,
        interval=args.interval,
        timeout=args.timeout,
        expected_version=args.expected_version,
    )
    print(json.dumps({"report": args.output, "failed_attempts": result["failed_attempts"]}))
    return 2 if result["failed_attempts"] else 0


def _cmd_monitored(args: argparse.Namespace) -> int:
    from hotelml.spark import create_spark, run_monitored_batch

    spark = create_spark(args.master)
    try:
        result = run_monitored_batch(
            spark,
            args.input,
            Path(args.output),
            Path(args.bundle),
            Path(args.reference),
            args.threshold,
            sample_rows=args.sample_rows,
            minimum=args.minimum_rows,
            psi_threshold=args.psi_threshold,
            tv_threshold=args.tv_threshold,
        )
        print(json.dumps(result, indent=2))
    finally:
        spark.stop()
    return 0  # Drift é um sinal; a execução completa continua bem-sucedida.


def _cmd_features(args: argparse.Namespace) -> int:
    from hotelml.spark import create_spark, run_features

    spark = create_spark(args.master)
    try:
        result = run_features(spark, args.input, args.output)
        print(json.dumps(result, indent=2))
    finally:
        spark.stop()
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    from hotelml.spark import create_spark, run_batch

    spark = create_spark(args.master)
    try:
        result = run_batch(spark, args.input, args.output, Path(args.bundle), args.threshold)
        print(json.dumps(result, indent=2))
    finally:
        spark.stop()
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

    probe = sub.add_parser("probe", help="sondagem externa finita com reserva sintética")
    probe.add_argument("--url", required=True)
    probe.add_argument("--output", required=True)
    probe.add_argument("--target", required=True, choices=["azure", "web"])
    probe.add_argument("--count", type=int, default=3)
    probe.add_argument("--interval", type=float, default=5)
    probe.add_argument("--timeout", type=float, default=30)
    probe.add_argument("--expected-version")
    probe.set_defaults(func=_cmd_probe)

    slo = sub.add_parser("slo", help="avalia SLIs e orçamento de erros da telemetria interna")
    for name in ("input", "output", "start", "end"):
        slo.add_argument(f"--{name}", required=True)
    for name in ("availability-target", "latency-target", "latency-ms"):
        slo.add_argument(f"--{name}", required=True, type=float)
    slo.add_argument("--data-kind", required=True, choices=["synthetic", "observed"])
    slo.add_argument("--minimum-requests", type=int, default=100)
    slo.add_argument("--input-format", choices=["jsonl", "azure"], default="jsonl")
    slo.add_argument("--complete-window", action="store_true")
    slo.set_defaults(func=_cmd_slo)

    quality = sub.add_parser("quality", help="avalia lote concluído contra desfechos finais")
    for name in ("batch", "outcomes", "output", "as-of"):
        quality.add_argument(f"--{name}", required=True)
    quality.add_argument("--data-kind", required=True, choices=["synthetic", "observed"])
    quality.add_argument("--minimum-rows", type=int, default=30)
    quality.set_defaults(func=_cmd_quality)

    explain = sub.add_parser("explain", help="fatores de uma previsão por valores de Shapley")
    for name in ("bundle", "reference", "booking", "output"):
        explain.add_argument(f"--{name}", required=True)
    explain.add_argument("--permutations", type=int, default=1000)
    explain.add_argument("--seed", type=int, default=0)
    explain.set_defaults(func=_cmd_explain)

    narrate = sub.add_parser("narrate", help="explica os fatores em linguagem natural (Claude)")
    narrate.add_argument("--factors", required=True, help="relatório de hotelml explain")
    narrate.add_argument("--output", required=True, help="novo relatório JSON")
    narrate.add_argument("--prompt-version", help="padrão: versão ativa do manifesto")
    narrate.add_argument("--prices", default="monitoring/llm-prices.json")
    narrate.add_argument("--trace-file", help="grava spans OpenTelemetry em JSONL")
    narrate.add_argument("--dry-run", action="store_true", help="não chama a API; usa o texto fixo")
    narrate.set_defaults(func=_cmd_narrate)

    outcomes = sub.add_parser("outcomes", help="converte estados finais da origem em desfechos")
    outcomes.add_argument("--source", required=True, help="Parquet/CSV com ID, estado e data")
    outcomes.add_argument("--output", required=True, help="novo Parquet no contrato de desfechos")
    outcomes.add_argument("--available-at", required=True, help="disponibilização, com fuso")
    outcomes.add_argument(
        "--pending-status", action="append", default=[], help="estado ainda aberto, a excluir"
    )
    outcomes.set_defaults(func=_cmd_outcomes)

    check = sub.add_parser("retrain-check", help="avalia gatilhos de retreino; código 2 recomenda")
    check.add_argument("--policy", default="monitoring/retraining-policy.json")
    check.add_argument("--trained-at", required=True, help="data do treino do modelo, com fuso")
    check.add_argument("--drift", action="append", default=[], help="relatório de drift (JSON)")
    check.add_argument("--quality", help="relatório de qualidade com desfechos observados")
    check.add_argument("--as-of", help="instante da avaliação, com fuso (padrão: agora)")
    check.add_argument("--output", required=True, help="novo relatório JSON")
    check.set_defaults(func=_cmd_retrain_check)

    reference = sub.add_parser("reference", help="exporta referência do run explícito de um bundle")
    reference.add_argument("--bundle", required=True)
    reference.add_argument("--output", required=True)
    reference.set_defaults(func=_cmd_reference)
    monitored = sub.add_parser("batch-monitor", help="drift amostrado e scoring Spark auditáveis")
    for name in ("input", "output", "bundle", "reference"):
        monitored.add_argument(f"--{name}", required=True)
    monitored.add_argument("--master")
    monitored.add_argument("--threshold", type=float, default=0.5)
    monitored.add_argument("--sample-rows", type=int, default=5000)
    monitored.add_argument("--minimum-rows", type=int, default=200)
    monitored.add_argument("--psi-threshold", type=float, default=0.2)
    monitored.add_argument("--tv-threshold", type=float, default=0.1)
    monitored.set_defaults(func=_cmd_monitored)

    drift = sub.add_parser("drift", help="compara reservas offline; código 2 indica drift")
    drift.add_argument("--reference", required=True, help="Parquet de referência do treino")
    drift.add_argument("--current", required=True, help="Parquet da janela atual")
    drift.add_argument("--output", required=True, help="novo relatório JSON")
    drift.add_argument("--minimum-rows", type=int, default=200)
    drift.add_argument("--psi-threshold", type=float, default=0.2)
    drift.add_argument("--tv-threshold", type=float, default=0.1)
    drift.set_defaults(func=_cmd_drift)

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
    features = sub.add_parser("features", help="prepara reservas em Parquet com PySpark")
    features.add_argument("--input", required=True, help="Parquet com booking_id e INPUT_COLUMNS")
    features.add_argument("--output", required=True, help="diretório novo de Parquet")
    features.add_argument("--master", help="master Spark; exemplo local[2]")
    features.set_defaults(func=_cmd_features)
    batch = sub.add_parser("batch", help="calcula previsões em lote com um snapshot exportado")
    batch.add_argument("--input", required=True, help="Parquet com booking_id e INPUT_COLUMNS")
    batch.add_argument("--output", required=True, help="diretório novo de Parquet")
    batch.add_argument("--bundle", required=True, help="diretório exportado por hotelml export")
    batch.add_argument("--threshold", type=float, default=0.5)
    batch.add_argument("--master", help="master Spark; exemplo local[2]")
    batch.set_defaults(func=_cmd_batch)
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
