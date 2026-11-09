from __future__ import annotations

import json

import pytest

from hotelml.cli import main
from hotelml.slo import evaluate_slo, slo_report


@pytest.fixture
def events():
    return [
        {
            "schema_version": 1,
            "event": "http_request",
            "timestamp": "2026-11-01T12:00:00Z",
            "request_id": f"request-{i}",
            "route": "/predict",
            "method": "POST",
            "status_code": status,
            "duration_ms": duration,
        }
        for i, (status, duration) in enumerate([(200, 10), (200, 100), (500, 5), (422, 2)])
    ]


@pytest.fixture
def options():
    return {
        "start": "2026-11-01T00:00:00Z",
        "end": "2026-11-02T00:00:00Z",
        "availability_target": 0.9,
        "latency_target": 0.8,
        "latency_ms": 50,
        "data_kind": "synthetic",
        "minimum": 3,
        "complete_window": True,
    }


def test_known_slis_budgets_and_no_individual_data(events, options):
    result = evaluate_slo(events, **options)
    assert result["status"] == "ready"
    assert result["observed_requests"] == 4
    assert result["excluded_client_errors"] == 1
    assert result["eligible_requests"] == 3
    availability, latency = result["availability"], result["latency"]
    assert availability["sli"] == pytest.approx(2 / 3)
    assert availability["bad_requests"] == 1
    assert availability["allowed_bad_requests"] == pytest.approx(0.3)
    assert availability["remaining_bad_requests"] == pytest.approx(-0.7)
    assert availability["burn_rate"] == pytest.approx(10 / 3)
    assert availability["budget_consumed_ratio"] == pytest.approx(10 / 3)
    assert availability["met"] is False
    assert latency["sli"] == pytest.approx(1 / 3)  # Falha rápida também consome orçamento.
    assert latency["bad_requests"] == 2
    assert latency["met"] is False
    assert result["successful_latency_ms"]["p95"] == pytest.approx(95.5)
    assert "request-" not in json.dumps(result)


def test_boundaries_timezone_and_irrelevant_events(events, options):
    events[0]["timestamp"] = "2026-11-01T01:00:00+01:00"  # Início incluído.
    events[1]["timestamp"] = options["end"]  # Fim excluído.
    events[2]["timestamp"] = "2026-10-31T23:59:59Z"
    events[3]["route"] = "/health/ready"
    events.append({"event": "model_ready"})
    options["minimum"] = 1
    result = evaluate_slo(events, **options)
    assert result["eligible_requests"] == 1
    assert result["availability"]["met"] is True
    assert result["latency"]["met"] is True


@pytest.mark.parametrize("complete,minimum", [(False, 3), (True, 4), (False, 4)])
def test_incomplete_or_sparse_window_never_claims_slo(events, options, complete, minimum):
    options.update(complete_window=complete, minimum=minimum)
    result = evaluate_slo(events, **options)
    assert result["status"] == "inconclusive"
    assert result["inconclusive_reasons"]
    for name in ("availability", "latency"):
        assert result[name]["met"] is None
        assert result[name]["burn_rate"] is None
        assert result[name]["remaining_bad_requests"] is None


def test_no_traffic_and_all_failures(events, options):
    result = evaluate_slo([], **options)
    assert result["status"] == "inconclusive"
    assert result["availability"]["sli"] is None
    assert result["successful_latency_ms"]["p95"] is None
    for event in events:
        event["status_code"] = 503
    result = evaluate_slo(events, **options)
    assert result["availability"]["sli"] == result["latency"]["sli"] == 0
    assert result["latency"]["met"] is False
    assert result["successful_latency_ms"]["p95"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("status_code", True),
        ("status_code", 600),
        ("status_code", "200"),
        ("duration_ms", -1),
        ("duration_ms", float("nan")),
        ("duration_ms", float("inf")),
        ("duration_ms", True),
        ("request_id", ""),
        ("timestamp", "2026-11-01"),
        ("timestamp", "invalid"),
        ("schema_version", 2),
        ("schema_version", True),
    ],
)
def test_invalid_telemetry_rejected(events, options, field, value):
    events[0][field] = value
    with pytest.raises(ValueError):
        evaluate_slo(events, **options)


def test_duplicate_requests_rejected(events, options):
    events[1]["request_id"] = events[0]["request_id"]
    with pytest.raises(ValueError, match="duplicado"):
        evaluate_slo(events, **options)


@pytest.mark.parametrize(
    "field,value",
    [
        ("availability_target", 1),
        ("latency_target", 0),
        ("latency_target", float("nan")),
        ("latency_ms", 0),
        ("latency_ms", float("inf")),
        ("minimum", 0),
        ("start", "2026-11-03T00:00:00Z"),
        ("end", "2026-11-02"),
        ("data_kind", "unknown"),
    ],
)
def test_invalid_policy_rejected(events, options, field, value):
    options[field] = value
    with pytest.raises(ValueError):
        evaluate_slo(events, **options)


def test_report_provenance_azure_partial_rejection_and_cli(events, options, tmp_path):
    source, output = tmp_path / "events.json", tmp_path / "slo.json"
    response = {
        "tables": [
            {
                "columns": [{"name": "event_json", "type": "string"}],
                "rows": [[json.dumps(event)] for event in events],
            }
        ]
    }
    source.write_text(json.dumps(response), encoding="utf-8-sig")
    args = [
        "slo",
        "--input",
        str(source),
        "--output",
        str(output),
        "--input-format",
        "azure",
        "--start",
        options["start"],
        "--end",
        options["end"],
        "--availability-target",
        "0.9",
        "--latency-target",
        "0.8",
        "--latency-ms",
        "50",
        "--minimum-requests",
        "3",
        "--data-kind",
        "synthetic",
        "--complete-window",
    ]
    assert main(args) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert len(result["provenance"]["events_sha256"]) == 64
    with pytest.raises(FileExistsError):
        slo_report(source, output, input_format="azure", **options)
    response["error"] = {"code": "PartialError"}
    source.write_text(json.dumps(response), encoding="utf-8")
    with pytest.raises(ValueError, match="parcial"):
        slo_report(source, tmp_path / "partial.json", input_format="azure", **options)
    assert not (tmp_path / "partial.json").exists()


def test_jsonl_healthy_and_inconclusive_cli(events, options, tmp_path):
    source = tmp_path / "events.jsonl"
    for event in events:
        event.update(status_code=200, duration_ms=10)
    source.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    report = slo_report(source, tmp_path / "healthy.json", **options)
    assert report["availability"]["met"] and report["latency"]["met"]
    assert report["availability"]["budget_consumed_ratio"] == 0
    assert (
        main(
            [
                "slo",
                "--input",
                str(source),
                "--output",
                str(tmp_path / "unknown.json"),
                "--start",
                options["start"],
                "--end",
                options["end"],
                "--availability-target",
                "0.9",
                "--latency-target",
                "0.8",
                "--latency-ms",
                "50",
                "--data-kind",
                "synthetic",
            ]
        )
        == 0
    )
    assert json.loads((tmp_path / "unknown.json").read_text())["status"] == "inconclusive"
