from __future__ import annotations

import hashlib
import io
import json
import runpy
import tarfile
from pathlib import Path

import pytest

unpack = runpy.run_path(str(Path(__file__).parents[1] / "scripts/model_release.py"))["unpack"]


def bundle(tmp_path, extra=None):
    path = tmp_path / "bundle.tar.gz"
    members = {
        "manifest.json": json.dumps(
            {"model_name": "hotel", "model_version": "1", "run_id": "run"}
        ).encode(),
        "model/MLmodel": b"flavors: {}",
    }
    if extra:
        members.update(extra)
    with tarfile.open(path, "w:gz") as archive:
        for name, content in members.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_extract_approved_bundle(tmp_path):
    path, digest = bundle(tmp_path)
    output = tmp_path / "output"
    assert unpack(path, output, digest, "1")["run_id"] == "run"
    assert (output / "model/MLmodel").is_file()
    with pytest.raises(FileExistsError):
        unpack(path, output, digest, "1")


@pytest.mark.parametrize("digest,version", [("0" * 64, "1"), (None, "2"), ("oops", "1")])
def test_reject_integrity_or_version_mismatch(tmp_path, digest, version):
    path, actual = bundle(tmp_path)
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        unpack(path, output, digest or actual, version)
    assert not output.exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "..\\escape"])
def test_reject_paths_outside_destination(tmp_path, name):
    path, digest = bundle(tmp_path, {name: b"bad"})
    with pytest.raises(ValueError, match="inseguro"):
        unpack(path, tmp_path / "output", digest, "1")


def test_reject_symlink(tmp_path):
    path, _ = bundle(tmp_path)
    # Tar não permite append comprimido; este arquivo é deliberadamente sem compressão.
    with tarfile.open(path, "w") as archive:
        entry = tarfile.TarInfo("link")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../outside"
        archive.addfile(entry)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="inseguro"):
        unpack(path, tmp_path / "output", digest, "1")
