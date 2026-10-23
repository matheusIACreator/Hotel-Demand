"""Empacota e verifica um bundle aprovado para entrega sem registry remoto."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path


def unpack(archive: Path, output: Path, digest: str, version: str) -> dict[str, str]:
    """Verifica integridade e membros antes de extrair; nunca sobrescreve o destino."""
    if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        raise ValueError("SHA-256 inválido")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest.lower():
            raise ValueError("SHA-256 não corresponde ao arquivo aprovado")
    if output.exists():
        raise FileExistsError(output)
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            parts = member.name.replace("\\", "/").split("/")
            if (
                member.name.startswith("/")
                or ".." in parts
                or ":" in member.name
                or "\\" in member.name
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("membro inseguro no bundle")
        manifest_file = source.extractfile("manifest.json")
        if manifest_file is None:
            raise ValueError("manifesto ausente")
        manifest = json.load(manifest_file)
        if manifest.get("model_version") != version:
            raise ValueError("versão diferente da aprovada")
        if not all(
            isinstance(manifest.get(k), str) and manifest[k]
            for k in ("model_name", "model_version", "run_id")
        ):
            raise ValueError("manifesto incompleto")
        if not any(m.name == "model/MLmodel" for m in source.getmembers()):
            raise ValueError("modelo MLflow ausente")
        source.extractall(output, filter="data")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("--bundle", type=Path, default=Path("model-bundle"))
    pack.add_argument("--output", type=Path, required=True)
    extract = commands.add_parser("unpack")
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--output", type=Path, default=Path("model-bundle"))
    extract.add_argument("--sha256", required=True)
    extract.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "pack":
        # Inclui apenas manifesto e modelo, nunca dados, registry ou segredos locais.
        with tarfile.open(args.output, "x:gz") as archive:
            for name in ("manifest.json", "model"):
                archive.add(args.bundle / name, arcname=name)
        with args.output.open("rb") as stream:
            print(hashlib.file_digest(stream, "sha256").hexdigest())
    else:
        print(json.dumps(unpack(args.archive, args.output, args.sha256, args.version)))


if __name__ == "__main__":
    main()
