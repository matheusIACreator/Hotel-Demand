from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_contract_is_up_to_date():
    render = runpy.run_path(str(ROOT / "scripts" / "export_openapi.py"))["render"]
    committed = (ROOT / "web" / "lib" / "contract" / "openapi.json").read_text(encoding="utf-8")
    assert committed == render(), "contrato desatualizado: rode python scripts/export_openapi.py"
