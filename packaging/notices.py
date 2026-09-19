"""Collect evidence from the actual Linux bundle; refuse unresolved publication."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import shutil
import ssl
import subprocess
import sys
import sysconfig
import tomllib
import urllib.request
from pathlib import Path


def collect(root: Path, destination: Path, pure: list, binaries: list) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        root / "packaging/THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md"
    )
    components = []
    blockers = [
        "Combined Mutagen/readline distribution terms and complete native "
        "corresponding source need review."
    ]

    def copy_licenses(name: str, paths: list[Path]) -> list[str]:
        copied = []
        for index, path in enumerate(paths):
            if path.is_file():
                output = destination / "licenses" / name / f"{index}-{path.name}"
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, output)
                copied.append(output.relative_to(destination).as_posix())
        if not copied:
            blockers.append(f"Missing license/notice text: {name}")
        return copied

    def component(name, version, license_id, paths, native, source, obligations):
        components.append(
            {
                "name": name,
                "version": version,
                "license": license_id,
                "license_files": copy_licenses(name, paths),
                "native_files": native,
                "source": source,
                "obligations": obligations,
            }
        )

    component(
        "frogify",
        tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"],
        "MIT",
        [root / "LICENSE"],
        [],
        "Frogify source distribution",
        "Retain copyright and permission notice.",
    )
    package_map = metadata.packages_distributions()
    modules = {name.split(".")[0] for name, _, _ in pure}
    modules.update(name.split("/")[0] for name, _, _ in binaries)
    distributions = {dist for module in modules for dist in package_map.get(module, [])}
    distributions.add("pyinstaller")
    lock = tomllib.loads((root / "uv.lock").read_text())
    locked = {package["name"]: package for package in lock["package"]}
    for name in sorted(distributions, key=str.casefold):
        dist = metadata.distribution(name)
        canonical = dist.metadata["Name"].lower().replace("_", "-")
        files = list(dist.files or [])
        license_paths = [
            Path(dist.locate_file(file))
            for file in files
            if any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts)
        ]
        native = [
            target
            for target, source, _ in binaries
            if any(Path(dist.locate_file(file)) == Path(source) for file in files)
        ]
        if canonical == "pyinstaller":
            native.append("frogify (PyInstaller bootloader)")
        declaration = dist.metadata.get("License-Expression") or dist.metadata.get("License")
        if not declaration:
            declaration = (
                "; ".join(
                    c for c in dist.metadata.get_all("Classifier", []) if c.startswith("License ::")
                )
                or "UNRESOLVED"
            )
        source = locked.get(canonical, {}).get("sdist", {})
        component(
            canonical,
            dist.version,
            declaration,
            license_paths,
            native,
            source.get("url", dist.metadata.get("Home-page", "")),
            "Retain supplied license/copyright/notice texts; "
            "review source obligations for copyleft components.",
        )
        if canonical in {"mutagen", "certifi"}:
            output = destination / "sources" / source["url"].rsplit("/", 1)[-1]
            output.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(source["url"], timeout=60) as response:
                data = response.read()
            if "sha256:" + hashlib.sha256(data).hexdigest() != source["hash"]:
                raise RuntimeError(f"{canonical} source checksum mismatch")
            output.write_bytes(data)

    python_files = [
        target
        for target, source, _ in binaries
        if "site-packages" not in source and ("python" in target or "lib-dynload" in target)
    ]
    component(
        "cpython",
        sys.version.split()[0],
        "PSF-2.0 and bundled notices",
        [Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"],
        python_files,
        "https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz",
        "Retain PSF and embedded third-party notices; inventory statically linked components too.",
    )
    rpm_components = {}
    for target, source, kind in binaries:
        if kind != "BINARY" or target in python_files:
            continue
        result = subprocess.run(
            ["rpm", "-qf", "--qf", "%{NAME}|%{VERSION}-%{RELEASE}|%{LICENSE}|%{SOURCERPM}", source],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            name, version, license_id, source_rpm = result.stdout.split("|")
            if name not in rpm_components:
                docs = subprocess.run(
                    ["rpm", "-qd", name], check=True, capture_output=True, text=True
                )
                paths = [
                    Path(path)
                    for path in docs.stdout.splitlines()
                    if Path(path)
                    .name.upper()
                    .startswith(("COPYING", "LICENSE", "NOTICE", "README"))
                ]
                rpm_components[name] = (version, license_id, source_rpm, paths, [])
            rpm_components[name][-1].append(target)
        else:
            version = (
                ssl.OPENSSL_VERSION if target in {"libssl.so.3", "libcrypto.so.3"} else "UNRESOLVED"
            )
            if "sqlite" in target:
                import sqlite3

                version = sqlite3.sqlite_version
            component(
                target,
                version,
                "UNRESOLVED",
                [],
                [target],
                "Official pinned manylinux build",
                "Supply exact upstream license and native build/source materials.",
            )
    for name, (version, license_id, source_rpm, paths, native) in rpm_components.items():
        component(
            name,
            version,
            license_id,
            paths,
            native,
            source_rpm,
            "Review component-specific terms; "
            "RPM license declaration may cover additional unbundled files.",
        )
    inventory = {
        "schema": 1,
        "release_ready": False,
        "blockers": blockers,
        "components": components,
    }
    (destination / "inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )


def check_release(path: Path) -> None:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    if inventory.get("release_ready") is not True or inventory.get("blockers"):
        raise SystemExit(
            "Standalone publication blocked:\n" + "\n".join(inventory.get("blockers", []))
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-release", type=Path, required=True)
    check_release(parser.parse_args().check_release)
