from __future__ import annotations

import hashlib
import http.client
import io
import json
import urllib.error

import pytest

from hotelml import probe
from hotelml.cli import main


def prediction(target="azure"):
    if target == "azure":
        return {
            "model_name": "hotel",
            "model_version": "1",
            "predictions": [{"cancellation_probability": 0.3, "is_canceled": False}],
        }
    return {
        "ok": True,
        "modelName": "hotel",
        "modelVersion": "1",
        "threshold": 0.5,
        "probability": 0.3,
        "isCanceled": False,
    }


@pytest.mark.parametrize(
    "target,path,field", [("azure", "/predict", "bookings"), ("web", "/api/predict", "booking")]
)
def test_real_contract_payload_and_complete_report(tmp_path, target, path, field):
    calls, sleeps = [], []

    def fetch(url, payload, timeout):
        calls.append((url, json.loads(payload), timeout))
        return 200, json.dumps(prediction(target)).encode()

    output = tmp_path / "probe"
    result = probe.run_probe(
        "https://example.test",
        output,
        target=target,
        fetch=fetch,
        sleep=sleeps.append,
        expected_version="1",
    )
    assert len(calls) == 3 and sleeps == [5, 5]
    assert all(url == "https://example.test" + path and timeout == 30 for url, _, timeout in calls)
    assert all(set(payload) == {field} for _, payload, _ in calls)
    assert result["successful_attempts"] == 3 and result["failed_attempts"] == 0
    assert result["success_rate"] == 1
    assert result["slo_status"] == "not_evaluated"
    assert (
        result["attempts_sha256"]
        == hashlib.sha256((output / "attempts.jsonl").read_bytes()).hexdigest()
    )
    assert result["run_sha256"] == hashlib.sha256((output / "run.json").read_bytes()).hexdigest()
    assert json.loads((output / "run.json").read_text())["payload_kind"] == "synthetic"
    assert json.loads((output / "summary.json").read_text(encoding="utf-8")) == result
    assert (output / "_SUCCESS").is_file()
    attempts = (output / "attempts.jsonl").read_text()
    assert "probability" not in attempts and "bookings" not in attempts
    assert result["successful_latency_ms"]["p95"] is not None
    with pytest.raises(FileExistsError):
        probe.run_probe("https://example.test", output, target=target, fetch=fetch)
    assert len(calls) == 3  # Não houve nova chamada ao rejeitar sobrescrita.


@pytest.mark.parametrize(
    "response,expected",
    [
        ((503, b"segredo"), "http_error"),
        ((429, b"segredo"), "http_error"),
        ((302, b""), "http_error"),
        ((200, b"not json"), "invalid_response"),
        ((200, b"x" * (probe.MAX_RESPONSE_BYTES + 1)), "response_too_large"),
        (TimeoutError("segredo"), "timeout"),
        (urllib.error.URLError(TimeoutError("segredo")), "timeout"),
        (urllib.error.URLError("segredo"), "network_error"),
        (ConnectionError("segredo"), "network_error"),
        (http.client.IncompleteRead(b"segredo", 100), "network_error"),
    ],
)
def test_failures_are_counted_without_retry_or_sensitive_messages(tmp_path, response, expected):
    calls = []

    def fetch(*args):
        calls.append(args)
        if isinstance(response, Exception):
            raise response
        return response

    result = probe.run_probe(
        "https://example.test", tmp_path / "probe", target="azure", count=1, fetch=fetch
    )
    assert len(calls) == 1
    assert result["outcomes"] == {expected: 1}
    assert result["success_rate"] == 0
    assert result["successful_latency_ms"]["p95"] is None
    assert (tmp_path / "probe/_SUCCESS").exists()  # Conclusão da coleta, mesmo com falha.
    assert "segredo" not in (tmp_path / "probe/attempts.jsonl").read_text()


@pytest.mark.parametrize(
    "target,mutate",
    [
        ("azure", lambda data: data.update(model_version="")),
        ("azure", lambda data: data.update(predictions=[])),
        (
            "azure",
            lambda data: data["predictions"][0].update(cancellation_probability=float("nan")),
        ),
        ("azure", lambda data: data["predictions"][0].update(cancellation_probability=True)),
        ("azure", lambda data: data["predictions"][0].update(is_canceled=True)),
        ("web", lambda data: data.update(ok=False)),
        ("web", lambda data: data.update(threshold=0.9)),
        ("web", lambda data: data.update(probability=2)),
    ],
)
def test_success_status_with_invalid_prediction_is_failure(tmp_path, target, mutate):
    body = prediction(target)
    mutate(body)
    result = probe.run_probe(
        "https://example.test",
        tmp_path / "probe",
        target=target,
        count=1,
        fetch=lambda *_: (200, json.dumps(body).encode()),
    )
    assert result["outcomes"] == {"invalid_response": 1}


def test_version_mismatch_is_failure(tmp_path):
    result = probe.run_probe(
        "https://example.test",
        tmp_path / "probe",
        target="azure",
        count=1,
        expected_version="2",
        fetch=lambda *_: (200, json.dumps(prediction()).encode()),
    )
    assert result["outcomes"] == {"version_mismatch": 1}


@pytest.mark.parametrize(
    "url,options",
    [
        ("http://example.test", {}),
        ("https://user:password@example.test", {}),
        ("https://example.test/path", {}),
        ("https://example.test?token=x", {}),
        ("https://example.test#fragment", {}),
        ("https://example.test", {"count": 21}),
        ("https://example.test", {"count": 0}),
        ("https://example.test", {"interval": -1}),
        ("https://example.test", {"timeout": float("nan")}),
        ("https://example.test", {"timeout": 61}),
    ],
)
def test_invalid_configuration_rejected_before_io(tmp_path, url, options):
    def fetch(*_):
        pytest.fail("não deveria enviar pedidos")

    with pytest.raises(ValueError):
        probe.run_probe(url, tmp_path / "probe", target="azure", fetch=fetch, **options)
    assert not (tmp_path / "probe").exists()


def test_interruption_preserves_journal_without_success_marker(tmp_path):
    calls = []

    def fetch(*_):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return 200, json.dumps(prediction()).encode()

    output = tmp_path / "probe"
    with pytest.raises(KeyboardInterrupt):
        probe.run_probe(
            "https://example.test", output, target="azure", fetch=fetch, sleep=lambda _: None
        )
    assert len((output / "attempts.jsonl").read_text().splitlines()) == 1
    assert json.loads((output / "run.json").read_text())["planned_attempts"] == 3
    assert not (output / "_SUCCESS").exists()
    assert not (output / "summary.json").exists()


def test_http_transport_no_redirects_bounds_response_and_closes_errors(monkeypatch):
    captured = []

    class Response(io.BytesIO):
        status = 200

    class Opener:
        def open(self, request, timeout):
            captured.append((request, timeout))
            return Response(b"x" * (probe.MAX_RESPONSE_BYTES + 5))

    def build(handler):
        assert handler.redirect_request(None, None, None, None, None, None) is None
        return Opener()

    monkeypatch.setattr(probe.urllib.request, "build_opener", build)
    status, body = probe._fetch("https://example.test/predict", b"{}", 2)
    assert status == 200 and len(body) == probe.MAX_RESPONSE_BYTES + 1
    assert captured[0][0].get_method() == "POST" and captured[0][1] == 2
    error = urllib.error.HTTPError("https://example.test", 302, "redirect", {}, io.BytesIO())

    def fail(*_, **kwargs):
        raise error

    monkeypatch.setattr(Opener, "open", fail)
    assert probe._fetch("https://example.test/predict", b"{}", 2) == (302, b"")
    assert error.closed


@pytest.mark.parametrize("status,expected_code", [(200, 0), (503, 2)])
def test_cli_exit_codes(tmp_path, monkeypatch, status, expected_code):
    run_probe = probe.run_probe

    def run(*args, **kwargs):
        return run_probe(
            *args, **kwargs, fetch=lambda *_: (status, json.dumps(prediction()).encode())
        )

    monkeypatch.setattr(probe, "run_probe", run)
    assert (
        main(
            [
                "probe",
                "--url",
                "https://example.test",
                "--output",
                str(tmp_path / "probe"),
                "--target",
                "azure",
                "--count",
                "1",
            ]
        )
        == expected_code
    )
