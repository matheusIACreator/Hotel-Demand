"""Carregamento de dados: Hugging Face, arquivo local ou sintético."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from hotelml.config import HF_FILENAME, HF_REPO_ID, Settings
from hotelml.synthetic import make_synthetic

log = logging.getLogger(__name__)


def download_hf(data_dir: Path) -> Path:
    """Baixa (ou reaproveita do cache) o parquet do dataset no Hugging Face."""
    from huggingface_hub import hf_hub_download

    data_dir.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        repo_id=HF_REPO_ID,
        filename=HF_FILENAME,
        repo_type="dataset",
        local_dir=data_dir,
    )
    log.info("dataset em %s", path)
    return Path(path)


def load_raw(
    source: str, settings: Settings | None = None, synthetic_rows: int = 20000
) -> pd.DataFrame:
    """Carrega o dataset bruto.

    `source` pode ser "hf" (Hugging Face), "synthetic" ou o caminho de um .parquet/.csv.
    """
    settings = settings or Settings()
    if source == "synthetic":
        return make_synthetic(n=synthetic_rows)
    if source == "hf":
        return pd.read_parquet(download_hf(settings.data_dir))
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"fonte de dados não encontrada: {source}")
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)
