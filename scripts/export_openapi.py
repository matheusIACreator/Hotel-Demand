"""Exporta o contrato OpenAPI para o frontend; um teste falha se o ficheiro ficar desatualizado."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hotelml.api import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "web" / "lib" / "contract" / "openapi.json"


def render() -> str:
    # O schema não depende do modelo: o loader nunca é chamado fora do lifespan.
    def no_model() -> Any:
        raise RuntimeError("o contrato não carrega modelos")

    schema = create_app(no_model).openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(), encoding="utf-8", newline="\n")
    print(f"contrato exportado para {args.output}")


if __name__ == "__main__":
    main()
