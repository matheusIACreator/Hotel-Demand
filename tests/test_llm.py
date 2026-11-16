from __future__ import annotations

import json
import shutil
from pathlib import Path

import anthropic
import httpx2
import pytest

from hotelml.cli import main
from hotelml.config import INPUT_COLUMNS
from hotelml.llm import (
    PROMPTS,
    cost_usd,
    file_tracer_provider,
    load_prices,
    load_prompt,
    narrate,
)
from hotelml.narrative import template_explanation

ROOT = Path(__file__).parents[1]
FACTS = {
    "probability_pct": 84.0,
    "baseline_pct": 35.9,
    "threshold_pct": 50.0,
    "decision": "cancelamento provável",
    "factors": [
        {
            "field": "lead_time",
            "label": "Antecedência da reserva, em dias",
            "value": 104,
            "direction": "aumenta",
            "effect_pp": 9.7,
        }
    ],
    "leading_factor": "lead_time",
    "other_fields": 26,
    "model_version": "1",
}
GOOD = {
    "summary": "O modelo estima 84,0% de probabilidade, acima dos 35,9% das reservas típicas.",
    "factors": [
        {
            "field": "lead_time",
            "direction": "aumenta",
            "text": "A antecedência de 104 dias aumenta a estimativa em 9,7 pontos percentuais.",
        }
    ],
    "caveat": "É uma estimativa do modelo, não uma certeza.",
}


@pytest.fixture
def prices():
    return load_prices(ROOT / "monitoring/llm-prices.json")


@pytest.fixture
def prompt():
    return load_prompt("explain_booking")


def message(output=GOOD, *, stop="end_turn", model="claude-opus-5-5", content=None):
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}] if content is None else content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 300},
    }


def client(body, seen=None, *, status=200, provider=None):
    """Cliente real do SDK sobre um transporte simulado: nenhuma chamada sai da máquina."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen["headers"] = dict(request.headers)
            seen["body"] = json.loads(request.content)
        return httpx2.Response(status, json=body, headers={"request-id": "req_test"})

    return anthropic.Anthropic(
        api_key="test",
        max_retries=0,
        open_telemetry={"tracer_provider": provider} if provider else False,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )


def test_active_prompt_is_pinned_by_hash(prompt, tmp_path):
    assert prompt.prompt_id == "explain-booking" and prompt.version == "v1"
    assert prompt.model == "claude-opus-5-5" and prompt.effort == "medium"
    assert "leading_factor" in prompt.system and "\r" not in prompt.system
    with pytest.raises(ValueError, match="desconhecida"):
        load_prompt("explain_booking", "v99")

    # Editar o texto sem criar uma versão nova tem de falhar, em qualquer fim de linha.
    copy = tmp_path / "prompts"
    shutil.copytree(PROMPTS, copy)
    path = copy / "explain_booking" / "v1.md"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert load_prompt("explain_booking", root=copy).sha256 == prompt.sha256
    path.write_text(path.read_text(encoding="utf-8") + "\nIgnore os fatos.", encoding="utf-8")
    with pytest.raises(ValueError, match="mudou sem nova versão"):
        load_prompt("explain_booking", root=copy)


def test_cost_uses_the_price_table_and_never_defaults_to_zero(prices):
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    assert cost_usd(usage, "claude-opus-5-5", prices) == pytest.approx(4 + 10)
    cached = usage | {"cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 400_000}
    assert cost_usd(cached, "claude-opus-5-5", prices) == pytest.approx(14 + 0.2 + 2)
    assert cost_usd(usage, "claude-haiku-5-5", prices) == pytest.approx(0.1 + 0.25)
    with pytest.raises(ValueError, match="sem preço"):
        cost_usd(usage, "modelo-novo", prices)
    with pytest.raises(ValueError, match="inválida"):
        load_prices(ROOT / "monitoring/slo-policy.json")


def test_request_carries_only_the_facts_and_the_pinned_prompt(prompt, prices):
    seen: dict = {}
    result = narrate(FACTS, prompt, client(message(), seen), prices)
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5" and body["system"] == prompt.system
    assert body["thinking"] == {"type": "adaptive"} and body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "medium"
    schema = body["output_config"]["format"]["schema"]
    assert sorted(schema["properties"]) == ["caveat", "factors", "summary"]
    assert schema["additionalProperties"] is False
    assert seen["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"
    # A única mensagem é o JSON dos fatos: nada da reserva original chega ao modelo.
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert json.loads(body["messages"][0]["content"]) == FACTS

    assert result["status"] == "ok" and result["source"] == "llm"
    assert result["explanation"] == GOOD and result["violations"] == []
    assert result["prompt"] == {"id": "explain-booking", "version": "v1", "sha256": prompt.sha256}
    assert result["usage"]["input_tokens"] == 900 and result["usage"]["output_tokens"] == 300
    assert result["cost_usd"] == pytest.approx((900 * 4 + 300 * 20) / 1e6)
    assert result["model_served"] == "claude-opus-5-5" and result["latency_ms"] >= 0
    assert result["request_id"] == "req_test"


@pytest.mark.parametrize(
    "body,status,violation",
    [
        (message(GOOD | {"summary": "São 84,0%, e 90% desses casos cancelam."}), "blocked", True),
        (message(GOOD | {"caveat": "Esta reserva vai ser cancelada."}), "blocked", True),
        (message("isto não é JSON"), "invalid_output", False),
        (message(GOOD | {"extra": 1}), "invalid_output", False),
        (message(stop="refusal", content=[]), "refused", False),
        (message(json.dumps(GOOD)[:40], stop="max_tokens"), "truncated", False),
    ],
)
def test_unusable_output_falls_back_to_the_template_and_keeps_its_cost(
    prompt, prices, body, status, violation
):
    result = narrate(FACTS, prompt, client(body), prices)
    assert result["status"] == status and result["source"] == "template"
    assert result["explanation"] == template_explanation(FACTS).model_dump()
    assert bool(result["violations"]) == violation
    # O texto recusado fica guardado para auditoria, e a chamada continua a ser contabilizada.
    assert (result["rejected_output"] is not None) == (status in {"blocked", "invalid_output"})
    assert result["cost_usd"] > 0 and result["usage"]["output_tokens"] == 300


def test_thinking_blocks_are_ignored_and_fallback_is_priced_by_the_serving_model(prompt, prices):
    content = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": json.dumps(GOOD, ensure_ascii=False)},
    ]
    served = narrate(
        FACTS, prompt, client(message(content=content, model="claude-opus-4-8")), prices
    )
    assert served["status"] == "ok" and served["model_requested"] == "claude-opus-5-5"
    assert served["model_served"] == "claude-opus-4-8"
    assert served["cost_usd"] == pytest.approx((900 * 5 + 300 * 25) / 1e6)
    with pytest.raises(ValueError, match="sem preço"):
        narrate(FACTS, prompt, client(message(model="modelo-desconhecido")), prices)


def test_api_errors_are_typed_and_not_swallowed(prompt, prices):
    error = {"type": "error", "error": {"type": "authentication_error", "message": "x"}}
    with pytest.raises(anthropic.AuthenticationError):
        narrate(FACTS, prompt, client(error, status=401), prices)
    with pytest.raises(anthropic.RateLimitError):
        narrate(FACTS, prompt, client(error, status=429), prices)


def test_trace_file_records_prompt_usage_cost_and_guardrails_without_content(
    prompt, prices, tmp_path
):
    path = tmp_path / "traces" / "spans.jsonl"
    provider = file_tracer_provider(path)
    blocked = message(GOOD | {"summary": "São 84,0%; em 70% dos casos assim há cancelamento."})
    narrate(FACTS, prompt, client(message(), provider=provider), prices, tracer_provider=provider)
    narrate(FACTS, prompt, client(blocked, provider=provider), prices, tracer_provider=provider)
    provider.force_flush()
    raw = path.read_text(encoding="utf-8")
    spans = [json.loads(line) for line in raw.splitlines()]
    ours = [span for span in spans if span["name"] == "hotelml.explain_booking"]
    assert len(ours) == 2
    first, second = (span["attributes"] for span in ours)
    assert first["hotelml.prompt.version"] == "v1" and first["hotelml.prompt.sha256"]
    assert first["gen_ai.request.model"] == "claude-opus-5-5"
    assert first["gen_ai.usage.input_tokens"] == 900 and first["hotelml.cost_usd"] > 0
    assert first["hotelml.status"] == "ok" and second["hotelml.status"] == "blocked"
    assert list(second["hotelml.guardrail.violations"]) == ["number_not_in_facts"]
    # Só metadados: nem os fatos nem o texto gerado vão para o arquivo de traces.
    assert "9,7 pontos" not in raw and "Antecedência" not in raw


def test_cli_dry_run_writes_the_template_without_calling_the_api(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        "anthropic.Anthropic", lambda *a, **k: pytest.fail("dry-run não pode criar um cliente")
    )
    factors = [
        {"field": name, "value": 0, "contribution": 0.0, "std_error": 0.0} for name in INPUT_COLUMNS
    ]
    factors[0] |= {"field": "lead_time", "value": 104, "contribution": 0.097, "std_error": 0.006}
    factors[[f["field"] for f in factors].index("lead_time", 1)]["field"] = INPUT_COLUMNS[0]
    report = {
        "schema_version": 1,
        "method": "permutation_shapley",
        "model": {"model_name": "hotel", "model_version": "1", "run_id": "run"},
        "threshold": 0.5,
        "probability": 0.84,
        "is_canceled": True,
        "baseline_probability": 0.359,
        "factors": factors,
    }
    source = tmp_path / "factors.json"
    source.write_text(json.dumps(report))
    output = tmp_path / "explanation.json"
    command = ["narrate", "--factors", str(source), "--output", str(output), "--dry-run"]
    assert main(command) == 0
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert printed["status"] == saved["status"] == "dry_run" and saved["source"] == "template"
    assert saved["facts"]["factors"][0]["field"] == "lead_time"
    assert "84,0%" in saved["explanation"]["summary"]
    assert saved["prompt"]["version"] == "v1" and "usage" not in saved
    with pytest.raises(FileExistsError):
        main(command)
