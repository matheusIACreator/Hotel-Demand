from __future__ import annotations

import io
import json
import runpy
import sys
import time
import urllib.request
from http.client import RemoteDisconnected
from pathlib import Path

import pytest


def smoke_main():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_api.py"
    return runpy.run_path(str(path))["main"]


@pytest.mark.parametrize("error", [ConnectionResetError(), RemoteDisconnected(), TimeoutError()])
def test_readiness_retries_transient_disconnect(monkeypatch, error):
    responses = iter(
        [
            error,
            {"model_version": "1"},
            {"model_version": "1", "predictions": [{"cancellation_probability": 0.5}] * 3},
        ]
    )
    calls = []

    def urlopen(request, **kwargs):
        calls.append(request)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return io.StringIO(json.dumps(response))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(sys, "argv", ["smoke_api.py", "http://localhost:8000", "--version", "1"])
    smoke_main()()
    assert len(calls) == 3
    assert calls[-1].get_method() == "POST"


def test_readiness_fails_when_api_never_starts(monkeypatch):
    def urlopen(*args, **kwargs):
        raise ConnectionResetError()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(sys, "argv", ["smoke_api.py", "http://localhost:8000", "--version", "1"])
    with pytest.raises(SystemExit, match="não ficou pronta"):
        smoke_main()()
