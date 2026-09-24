"""Build and verify the inseparable binary/corresponding-source release set."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import runpy
import tarfile
import tempfile
from pathlib import Path

HELPERS = runpy.run_path(str(Path(__file__).with_name("compliance.py")))
BINARY = "frogify-linux-x86_64.tar.gz"
SOURCES = "frogify-linux-x86_64-sources.tar.gz"


def digest(path):
    return HELPERS["digest"](path)


def version_of(inventory):
    return next(c["version"] for c in inventory["components"] if c["name"] == "frogify")


def require_binary_binding(inventory):
    if not inventory.get("executable_sha256") or not inventory.get("native_input_sha256"):
        raise ValueError("Missing frozen executable/native provenance binding")


def archive(root, files, output):
    names = set(files)
    for name in files:
        names.update(p.as_posix() for p in Path(name).parents if p.as_posix() != ".")
    with (
        output.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz,
        tarfile.open(fileobj=gz, mode="w") as bundle,
    ):
        for name in sorted(names):
            path = root / name
            info = tarfile.TarInfo(name)
            info.mtime = 946684800
            info.mode = 0o755 if path.is_dir() or name == "frogify" else 0o644
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                bundle.addfile(info)
            else:
                info.size = path.stat().st_size
                with path.open("rb") as stream:
                    bundle.addfile(info, stream)


def build(root: Path, output: Path):
    inventory = json.loads((root / "inventory.json").read_text())
    require_binary_binding(inventory)
    blockers = HELPERS["validate"](inventory, root)
    if blockers or inventory.get("blockers") != [] or inventory.get("release_ready") is not True:
        raise ValueError("Cannot package unresolved compliance evidence: " + "; ".join(blockers))
    binary_files = {"frogify", "inventory.json", "THIRD_PARTY_NOTICES.md"}
    source_files = {"inventory.json"}
    source_hashes = {}
    for component in inventory["components"]:
        binary_files.update(component["license_files"])
        source_files.update(component["source_files"] + component["build_files"])
        for name in component["source_files"]:
            sha = component["file_sha256"][name]
            # Shared source RPMs are stored once; reject aliases that would duplicate bytes.
            if source_hashes.setdefault(sha, name) != name:
                raise ValueError("Duplicate source content under different filenames: " + name)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".release-set-", dir=output) as temporary:
        stage = Path(temporary)
        archive(root, binary_files, stage / BINARY)
        archive(root, source_files, stage / SOURCES)
        manifest = dict(
            schema=1,
            version=version_of(inventory),
            inventory_sha256=digest(root / "inventory.json"),
            assets={},
        )
        for name in (BINARY, SOURCES):
            sha = digest(stage / name)
            manifest["assets"][name] = dict(sha256=sha, bytes=(stage / name).stat().st_size)
            (stage / (name + ".sha256")).write_text(f"{sha}  {name}\n")
        (stage / "release-set.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        check(stage)
        for path in stage.iterdir():
            path.replace(output / path.name)


def check(directory: Path):
    manifest = json.loads((directory / "release-set.json").read_text())
    if manifest.get("schema") != 1 or set(manifest.get("assets", {})) != {BINARY, SOURCES}:
        raise ValueError("Incomplete release asset set")
    inventories = []
    with tempfile.TemporaryDirectory(prefix="frogify-release-check-") as temporary:
        root = Path(temporary)
        for asset in (BINARY, SOURCES):
            expected = manifest["assets"][asset]
            path = directory / asset
            if path.stat().st_size != expected["bytes"] or digest(path) != expected["sha256"]:
                raise ValueError("Release asset checksum mismatch: " + asset)
            if (directory / (asset + ".sha256")).read_text().split() != [expected["sha256"], asset]:
                raise ValueError("Missing or inconsistent release checksum: " + asset)
            seen = set()
            with tarfile.open(path, "r|gz") as bundle:
                for member in bundle:
                    name = member.name
                    if not HELPERS["relative_file"](name) or name in seen:
                        raise ValueError("Unsafe or duplicate release member: " + name)
                    seen.add(name)
                    allowed = (
                        (
                            name
                            in {"frogify", "THIRD_PARTY_NOTICES.md", "inventory.json", "licenses"}
                            or name.startswith("licenses/")
                        )
                        if asset == BINARY
                        else name in {"inventory.json", "sources"} or name.startswith("sources/")
                    )
                    if not allowed or not (member.isfile() or member.isdir()):
                        raise ValueError("Unexpected release member: " + name)
                    if member.isdir():
                        (root / name).mkdir(parents=True, exist_ok=True)
                        continue
                    stream = bundle.extractfile(member)
                    assert stream is not None
                    if name == "inventory.json":
                        data = stream.read()
                        if hashlib.sha256(data).hexdigest() != manifest["inventory_sha256"]:
                            raise ValueError("Binary/source inventory mismatch")
                        inventories.append(json.loads(data))
                    else:
                        (root / name).parent.mkdir(parents=True, exist_ok=True)
                        with (root / name).open("wb") as target:
                            while chunk := stream.read(1024 * 1024):
                                target.write(chunk)
            required = (
                {"frogify", "THIRD_PARTY_NOTICES.md", "inventory.json"}
                if asset == BINARY
                else {"inventory.json", "sources"}
            )
            if not required <= seen:
                raise ValueError("Release asset missing required members: " + asset)
        if len(inventories) != 2 or inventories[0] != inventories[1]:
            raise ValueError("Missing or inconsistent paired inventories")
        inventory = inventories[0]
        require_binary_binding(inventory)
        version = version_of(inventory)
        if version != manifest["version"]:
            raise ValueError("Release-set version mismatch")
        expected_url = (
            f"https://github.com/wittg3n/frogify-cli/releases/download/v{version}/{SOURCES}"
        )
        if inventory.get("source_distribution", {}).get("url") != expected_url:
            raise ValueError("Missing exact versioned corresponding-source location")
        blockers = HELPERS["validate"](inventory, root)
        if (
            blockers
            or inventory.get("blockers") != []
            or inventory.get("release_ready") is not True
        ):
            raise ValueError("Unresolved release-set compliance: " + "; ".join(blockers))
        if not (root / "frogify").stat().st_size:
            raise ValueError("Empty standalone executable")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        if args.output is None:
            parser.error("build requires --output")
        build(args.directory, args.output)
    else:
        check(args.directory)
