"""Inspect the executable itself, not only the spec's exclusion settings."""

import hashlib
import json
import os
from pathlib import Path

import pytest

EXECUTABLE = os.environ.get("FROGIFY_TEST_EXECUTABLE")
pytestmark = pytest.mark.skipif(not EXECUTABLE, reason="requires Linux standalone executable")


def test_runtime_payload_and_native_inventory():
    from PyInstaller.archive.readers import CArchiveReader

    executable = Path(EXECUTABLE)
    archive = CArchiveReader(str(executable))
    assert not any(name.startswith("distribution/") for name in archive.toc)
    assert not any(name.endswith((".src.rpm", ".tar.xz", ".tar.gz")) for name in archive.toc)
    pure = set(archive.open_embedded_archive("PYZ.pyz").toc)
    for name in ("setuptools", "_distutils_hack", "readline", "bz2", "lzma"):
        assert not any(module == name or module.startswith(name + ".") for module in pure)
    assert not any("pyi_rth_setuptools" in name for name in archive.toc)
    assert "pygments.lexers.python" in pure
    assert not {"pygments.lexers.javascript", "pygments.formatters.img"} & pure
    native = {name for name, entry in archive.toc.items() if entry[-1] == "b"}
    for name in native:
        assert not any(
            excluded in name
            for excluded in (
                "readline",
                "libstdc++",
                "libgcc",
                "libbz2",
                "liblzma",
                "/_bz2.",
                "/_lzma.",
            )
        )
        assert not (name.startswith("rapidfuzz/") and name.endswith(".so"))
    inventory = json.loads(executable.with_name("inventory.json").read_text())
    assert native == set(inventory["native_files"])
    for name in native:
        assert hashlib.sha256(archive.extract(name)).hexdigest() == inventory["native_files"][name]
    assert not {"setuptools", "readline", "libgcc", "libstdc++", "bzip2-libs", "xz-libs"} & {
        c["name"] for c in inventory["components"]
    }
    assert not {"ninja", "scikit-build-core"} & {
        d["name"].lower() for d in inventory["freeze_distributions"]
    }
