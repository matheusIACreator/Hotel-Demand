"""Exporta, para o frontend, as categorias que o OneHotEncoder do bundle aprendeu no treino.

Categorias raras (abaixo de `min_frequency`) ficam separadas: o modelo trata-as como um único
grupo "infrequente", tal como faz com valores nunca vistos.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hotelml.bundle import load_bundle
from hotelml.config import CATEGORICAL_MODEL

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=ROOT / "model-bundle")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "web" / "lib" / "contract" / "categories.json"
    )
    args = parser.parse_args()
    loaded = load_bundle(args.bundle)
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    encoder = loaded.model.named_steps["preprocess"].named_transformers_["cat"]
    infrequent = encoder.infrequent_categories_
    columns = {}
    for name, cats, rare in zip(CATEGORICAL_MODEL, encoder.categories_, infrequent, strict=True):
        rare_set = {str(c) for c in rare} if rare is not None else set()
        values = [str(c) for c in cats if isinstance(c, str)]
        columns[name] = {
            "frequent": [v for v in values if v not in rare_set],
            "infrequent": sorted(rare_set),
        }
    payload = {
        "source": "OneHotEncoder do bundle exportado",
        "model_name": manifest["model_name"],
        "model_version": manifest["model_version"],
        "run_id": manifest["run_id"],
        "min_frequency": encoder.min_frequency,
        "columns": columns,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"categorias da versão {manifest['model_version']} exportadas para {args.output}")


if __name__ == "__main__":
    main()
