"""Verifica readiness, versão e inferência real; usado localmente e no CD."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

from hotelml.config import INPUT_COLUMNS
from hotelml.synthetic import make_synthetic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    url = args.url.rstrip("/")
    for attempt in range(60):
        try:
            with urllib.request.urlopen(f"{url}/health/ready", timeout=5) as response:
                ready = json.load(response)
            if ready["model_version"] == args.version:
                break
        except (urllib.error.URLError, TimeoutError):
            pass
        if attempt == 59:
            raise SystemExit("API não ficou pronta com a versão esperada")
        time.sleep(3)
    bookings = json.loads(make_synthetic(3)[INPUT_COLUMNS].to_json(orient="records"))
    request = urllib.request.Request(
        f"{url}/predict",
        data=json.dumps({"bookings": bookings}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    assert result["model_version"] == args.version, result
    assert len(result["predictions"]) == 3, result
    assert all(0 <= p["cancellation_probability"] <= 1 for p in result["predictions"]), result
    print(f"smoke OK: modelo versão {args.version}, 3 previsões válidas")


if __name__ == "__main__":
    main()
