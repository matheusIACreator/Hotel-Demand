"""Chamada ao modelo de linguagem: prompt versionado, custo, tracing e guardrails aplicados."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import transform_schema
from pydantic import ValidationError

from hotelml.narrative import Explanation, check_explanation, template_explanation

PROMPTS = Path(__file__).parent / "prompts"
# Sem `fallbacks`, uma recusa dos classificadores de segurança encerra o pedido. No modo
# "default" a própria API escolhe o modelo substituto conforme a categoria da recusa.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    version: str
    sha256: str
    system: str
    model: str
    effort: str
    max_tokens: int


def _normalized(path: Path) -> str:
    # O hash não pode depender do fim de linha que o Git usa em cada sistema.
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def load_prompt(name: str, version: str | None = None, root: Path = PROMPTS) -> Prompt:
    """Carrega uma versão do prompt e recusa texto alterado sem nova versão."""
    manifest = json.loads((root / name / "manifest.json").read_text(encoding="utf-8"))
    version = version or manifest["active"]
    if version not in manifest["versions"]:
        raise ValueError(f"versão de prompt desconhecida: {version}")
    entry = manifest["versions"][version]
    system = _normalized(root / name / entry["file"])
    digest = hashlib.sha256(system.encode("utf-8")).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(
            f"o texto de {name}/{version} mudou sem nova versão: crie uma versão em vez de editar"
        )
    return Prompt(
        manifest["prompt_id"],
        version,
        digest,
        system,
        entry["model"],
        entry["effort"],
        entry["max_tokens"],
    )


def load_prices(path: Path) -> dict[str, Any]:
    prices = json.loads(path.read_text(encoding="utf-8"))
    if prices.get("schema_version") != 1 or not prices.get("models"):
        raise ValueError("tabela de preços inválida")
    return prices


def cost_usd(usage: dict[str, int], model: str, prices: dict[str, Any]) -> float:
    """Custo de uma chamada; modelo fora da tabela é erro, nunca custo zero."""
    if model not in prices["models"]:
        raise ValueError(f"modelo sem preço na tabela: {model}")
    rate = prices["models"][model]
    tokens = (
        usage["input_tokens"] * rate["input"]
        + usage["output_tokens"] * rate["output"]
        + usage.get("cache_read_input_tokens", 0) * rate["cache_read"]
        + usage.get("cache_creation_input_tokens", 0)
        * rate["input"]
        * prices["cache_write_multiplier"]
    )
    return tokens / 1_000_000


def file_tracer_provider(path: Path) -> Any:
    """Provider OpenTelemetry que grava cada span como uma linha JSON, sem backend externo."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

    class JsonlExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                for span in spans:
                    stream.write(json.dumps(json.loads(span.to_json()), ensure_ascii=False) + "\n")
            return SpanExportResult.SUCCESS

    provider = TracerProvider(resource=Resource.create({"service.name": "hotelml"}))
    provider.add_span_processor(SimpleSpanProcessor(JsonlExporter()))
    return provider


def _usage(response: Any) -> dict[str, int]:
    usage = response.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None) or 0,
    }


def narrate(
    facts: dict[str, Any],
    prompt: Prompt,
    client: Any,
    prices: dict[str, Any],
    *,
    tracer_provider: Any | None = None,
) -> dict[str, Any]:
    """Pede a explicação ao modelo e só a devolve se passar em todos os guardrails."""
    from opentelemetry import trace

    tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer("hotelml.llm")
    with tracer.start_as_current_span("hotelml.explain_booking") as span:
        span.set_attributes(
            {
                "hotelml.prompt.id": prompt.prompt_id,
                "hotelml.prompt.version": prompt.version,
                "hotelml.prompt.sha256": prompt.sha256,
                "gen_ai.request.model": prompt.model,
            }
        )
        start = time.perf_counter()
        # `create` com o esquema explícito, em vez de `parse`: uma saída inválida ou truncada
        # tem de ficar registrada com o seu consumo, e não se perder numa exceção.
        response = client.beta.messages.create(
            model=prompt.model,
            max_tokens=prompt.max_tokens,
            system=prompt.system,
            messages=[
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False, sort_keys=True)}
            ],
            thinking={"type": "adaptive"},
            output_config={
                "effort": prompt.effort,
                "format": {"type": "json_schema", "schema": transform_schema(Explanation)},
            },
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        usage = _usage(response)
        # O preço segue o modelo que respondeu, que difere do pedido quando há fallback.
        cost = cost_usd(usage, response.model, prices)

        violations: list[dict[str, str]] = []
        rejected: Any = None
        parsed = None
        text = next((block.text for block in response.content if block.type == "text"), None)
        if response.stop_reason == "refusal":
            status = "refused"
        elif response.stop_reason == "max_tokens":
            status = "truncated"
        else:
            try:
                parsed = Explanation.model_validate_json(text or "")
            except ValidationError:
                status, rejected = "invalid_output", text
            else:
                violations = check_explanation(parsed, facts)
                status = "blocked" if violations else "ok"
                if violations:
                    rejected = parsed.model_dump()
        explanation = parsed if status == "ok" and parsed else template_explanation(facts)

        span.set_attributes(
            {
                "gen_ai.response.model": response.model,
                "gen_ai.usage.input_tokens": usage["input_tokens"],
                "gen_ai.usage.output_tokens": usage["output_tokens"],
                "hotelml.cost_usd": cost,
                "hotelml.status": status,
                "hotelml.stop_reason": str(response.stop_reason),
                "hotelml.guardrail.violations": [v["code"] for v in violations],
            }
        )
        return {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "status": status,
            # "template" quando o texto do modelo não pôde ser usado.
            "source": "llm" if status == "ok" else "template",
            "explanation": explanation.model_dump(),
            "violations": violations,
            "rejected_output": rejected,
            "facts": facts,
            "prompt": {"id": prompt.prompt_id, "version": prompt.version, "sha256": prompt.sha256},
            "model_requested": prompt.model,
            "model_served": response.model,
            "effort": prompt.effort,
            "stop_reason": response.stop_reason,
            "usage": usage,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "request_id": getattr(response, "_request_id", None),
        }
