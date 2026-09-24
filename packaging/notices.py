"""Collect evidence from the actual Linux bundle; refuse unresolved publication."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import io
import json
import runpy
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tomllib
from pathlib import Path

_helpers = runpy.run_path(str(Path(__file__).with_name("compliance.py")))
digest, fetch, save, archive_texts, validate, finalize = (
    _helpers[name] for name in ("digest", "fetch", "save", "archive_texts", "validate", "finalize")
)


def collect(root: Path, destination: Path, pure: list, binaries: list) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        root / "packaging/THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md"
    )
    cache = root / "build/compliance-evidence"
    components = []
    native_files = {target: digest(Path(source)) for target, source, _ in binaries}
    claimed = set()

    def component(name, version, license_id, native, source, obligations):
        result = dict(
            name=name,
            version=version,
            license=license_id,
            native_files=sorted(native),
            source=source,
            source_evidence=source,
            obligations=obligations,
            license_evidence=[],
            license_files=[],
            source_files=[],
            build_files=[],
            file_sha256={},
            source_required=False,
            collection_errors=[],
        )
        components.append(result)
        claimed.update(native)
        return result

    def license_file(c, filename, data, origin):
        relative = f"licenses/{c['name']}/{filename}"
        save(c, destination, relative, data, "license_files")
        c["license_evidence"].append(dict(file=relative, origin=origin))
        return relative

    def source_file(c, source):
        archive = fetch(source, cache)
        relative = "sources/" + archive.name
        save(c, destination, relative, archive.read_bytes(), "source_files")
        c["source_evidence"] = dict(
            origin=source, file=relative, version=c["version"], relationship=c["source_evidence"]
        )
        return archive

    project_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    project = component(
        "frogify",
        project_version,
        "MIT",
        [],
        "Included source snapshot",
        "Retain copyright and permission notice.",
    )
    license_file(project, "LICENSE", (root / "LICENSE").read_bytes(), "Frogify checkout LICENSE")
    for filename in (
        "Dockerfile",
        "build-linux.sh",
        "frogify.spec",
        "launcher.py",
        "notices.py",
        "compliance.py",
        "release_set.py",
        "GPL-3.0.txt",
        "native-evidence.json",
        "THIRD_PARTY_NOTICES.md",
        "SOURCE_BUILD.md",
    ):
        save(
            project,
            destination,
            "sources/build-info/packaging/" + filename,
            (root / "packaging" / filename).read_bytes(),
            "build_files",
        )
    for filename in ("pyproject.toml", "uv.lock", "install.sh"):
        save(
            project,
            destination,
            "sources/build-info/" + filename,
            (root / filename).read_bytes(),
            "build_files",
        )
    for path in sorted((root / "packaging/hooks").glob("*.py")):
        save(
            project,
            destination,
            "sources/build-info/packaging/hooks/" + path.name,
            path.read_bytes(),
            "build_files",
        )
    save(
        project,
        destination,
        "sources/build-info/SOURCE_BUILD.md",
        (root / "packaging/SOURCE_BUILD.md").read_bytes(),
        "build_files",
    )
    snapshot = io.BytesIO()
    with tarfile.open(fileobj=snapshot, mode="w") as archive:
        files = [
            root / filename for filename in ("LICENSE", "README.md", "pyproject.toml", "uv.lock")
        ]
        files += [
            p for directory in ("frogify", "mp3juice") for p in (root / directory).rglob("*.py")
        ]
        for path in sorted(files):
            data = path.read_bytes()
            entry = tarfile.TarInfo(path.relative_to(root).as_posix())
            entry.size, entry.mode, entry.mtime = len(data), 0o644, 946684800
            archive.addfile(entry, io.BytesIO(data))
    save(
        project,
        destination,
        f"sources/frogify-{project_version}.tar",
        snapshot.getvalue(),
        "source_files",
    )

    package_map = metadata.packages_distributions()
    modules = {name.split(".")[0] for name, _, _ in pure}
    modules.update(name.split("/")[0] for name, _, _ in binaries)
    distributions = {dist for module in modules for dist in package_map.get(module, [])}
    distributions.add("pyinstaller")
    locked = {p["name"]: p for p in tomllib.loads((root / "uv.lock").read_text())["package"]}
    for name in sorted(distributions, key=str.casefold):
        dist = metadata.distribution(name)
        canonical = dist.metadata["Name"].lower().replace("_", "-")
        files = sorted(dist.files or [], key=str)
        owned = {Path(dist.locate_file(f)).resolve() for f in files}
        native = [t for t, s, _ in binaries if Path(s).resolve() in owned]
        declaration = dist.metadata.get("License-Expression") or dist.metadata.get("License")
        if not declaration:
            declaration = (
                "; ".join(
                    c for c in dist.metadata.get_all("Classifier", []) if c.startswith("License ::")
                )
                or "UNRESOLVED"
            )
        pin = locked.get(canonical, {})
        source = pin.get("sdist", {})
        c = component(
            canonical,
            dist.version,
            declaration,
            native,
            source.get("url", "UNRESOLVED"),
            "Retain all supplied copyright/license/notice texts, including vendored components.",
        )
        if canonical == "pyinstaller":
            c["obligations"] = (
                "Retain COPYING.txt, bootloader exception and bundled notices. "
                "The exception applies only to PyInstaller, not dependencies."
            )
            bootloader = next(
                f for f in files if f.as_posix().endswith("bootloader/Linux-64bit-intel/run")
            )
            c["bootloader_sha256"] = digest(Path(dist.locate_file(bootloader)))
        c["source_required"] = canonical in {"mutagen", "certifi"}
        if canonical == "mutagen":
            license_file(
                c,
                "GPL-3.0.txt",
                (root / "packaging/GPL-3.0.txt").read_bytes(),
                "GNU GPLv3 text: COPYING3 from authenticated gcc-4.8.5-44.el7 RPM; "
                "later-version option in Mutagen's GPL-2.0-or-later grant",
            )
        copied_licenses = {}
        for index, file in enumerate(
            f
            for f in files
            if f.name.lower().startswith(("license", "copying", "notice", "copyright", "authors"))
            or ("licenses" in f.parts and any(p.endswith(".dist-info") for p in f.parts))
        ):
            copied_licenses[Path(dist.locate_file(file)).resolve()] = license_file(
                c,
                f"{index:03d}-{file.name}",
                Path(dist.locate_file(file)).read_bytes(),
                f"{canonical} {dist.version} distribution: {file.as_posix()}",
            )
        if pin.get("version") != dist.version:
            c["collection_errors"].append(
                f"Installed {canonical} {dist.version} does not match uv.lock"
            )
        if source:
            try:
                archive = source_file(
                    c, dict(url=source["url"], sha256=source["hash"].removeprefix("sha256:"))
                )
                # Inventory only vendor distributions whose code is actually in Analysis.
                vendor_root = Path(dist.locate_file(canonical + "/_vendor"))
                vendors = []
                if vendor_root.is_dir():
                    for vendor in metadata.distributions(path=[str(vendor_root)]):
                        owned_vendor = {
                            Path(vendor.locate_file(f)).resolve() for f in vendor.files or []
                        }
                        included = [
                            (n, Path(p).resolve())
                            for n, p, _ in pure
                            if Path(p).resolve() in owned_vendor
                        ]
                        if included:
                            license_id = vendor.metadata.get(
                                "License-Expression"
                            ) or vendor.metadata.get("License")
                            license_id = (
                                license_id
                                or "; ".join(
                                    v
                                    for v in vendor.metadata.get_all("Classifier", [])
                                    if v.startswith("License ::")
                                )
                                or "UNRESOLVED"
                            )
                            vendors.append(
                                (
                                    vendor.metadata["Name"],
                                    vendor.version,
                                    license_id,
                                    included,
                                    owned_vendor,
                                )
                            )
                if canonical == "typer":
                    included = [
                        (n, Path(p).resolve()) for n, p, _ in pure if n.startswith("typer._click")
                    ]
                    if included:
                        vendors.append(
                            (
                                "Click",
                                f"snapshot in Typer {dist.version}",
                                "BSD-3-Clause",
                                included,
                                {Path(dist.locate_file("typer/_click/LICENSE.txt")).resolve()},
                            )
                        )
                with tarfile.open(archive) as source_tar:
                    members = {
                        m.name.split("/", 1)[1]: m
                        for m in source_tar.getmembers()
                        if "/" in m.name and m.isfile()
                    }
                    for vendor_name, version, license_id, included, owned_vendor in sorted(vendors):
                        verified = True
                        for module, path in included:
                            relative = path.relative_to(
                                Path(dist.locate_file("")).resolve()
                            ).as_posix()
                            member = members.get(relative)
                            stream = source_tar.extractfile(member) if member else None
                            if stream is None or stream.read() != path.read_bytes():
                                verified = False
                                c["collection_errors"].append(
                                    "Bundled vendor source differs or is absent: "
                                    f"{canonical}/{module}"
                                )
                        c.setdefault("vendored_components", []).append(
                            dict(
                                name=vendor_name,
                                version=version,
                                license=license_id,
                                pure_modules=sorted(n for n, _ in included),
                                license_files=sorted(
                                    saved
                                    for path, saved in copied_licenses.items()
                                    if path in owned_vendor
                                ),
                                source_file=c["source_files"][0],
                                source_verified=verified,
                            )
                        )
                if canonical == "mutagen":
                    with tarfile.open(archive) as source_tar:
                        for file in files:
                            if file.parts[0] == "mutagen" and file.suffix == ".py":
                                member = source_tar.extractfile(
                                    f"mutagen-{dist.version}/{file.as_posix()}"
                                )
                                if (
                                    member is None
                                    or member.read() != Path(dist.locate_file(file)).read_bytes()
                                ):
                                    raise ValueError(
                                        f"Mutagen source differs from installed module {file}"
                                    )
                    c["obligations"] = (
                        "GPL-2.0-or-later. Locked sdist verified byte-for-byte against installed "
                        "Python sources; project snapshot and PyInstaller build/install recipe "
                        "included. Combined distribution source scope is checked separately."
                    )
            except (OSError, ValueError, KeyError, tarfile.TarError) as error:
                c["collection_errors"].append(
                    f"Source verification failed for {canonical}: {type(error).__name__}"
                )

    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    python_native = [
        t
        for t, s, _ in binaries
        if t not in claimed
        and (
            Path(s).resolve().is_relative_to(stdlib / "lib-dynload")
            or Path(s).resolve() == stdlib.parent / "libpython3.12.so.1.0"
        )
    ]
    python = component(
        "cpython",
        sys.version.split()[0],
        "PSF-2.0 and bundled notices",
        python_native,
        "https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz",
        "Retain CPython LICENSE and embedded source-component notices, including expat, "
        "mpdecimal and hashing implementations.",
    )
    license_file(
        python,
        "LICENSE.txt",
        (stdlib / "LICENSE.txt").read_bytes(),
        "Exact installed CPython stdlib LICENSE.txt",
    )
    python_pin = dict(
        url=python["source"],
        sha256="5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a",
    )
    if python["version"] != "3.12.14":
        python["collection_errors"].append(
            "CPython version differs from the reviewed 3.12.14 source pin"
        )
    else:
        archive = source_file(python, python_pin)
        import decimal
        import pyexpat

        python["embedded_source_components"] = [
            dict(
                name=name,
                version=version,
                source_file=python["source_files"][0],
                notices="CPython Doc/license.rst and embedded copyright/license files",
                native_files=[n for n in python_native if marker in n],
            )
            for name, version, marker in (
                ("libmpdec", decimal.__libmpdec_version__, "/_decimal."),
                ("Expat", pyexpat.EXPAT_VERSION, "/pyexpat."),
            )
            if any(marker in n for n in python_native)
        ]
        with tarfile.open(archive) as bundle:
            for index, member in enumerate(sorted(bundle.getmembers(), key=lambda m: m.name)):
                if member.isfile() and Path(member.name).name.upper().startswith(
                    ("LICENSE", "COPYING", "NOTICE", "COPYRIGHT")
                ):
                    stream = bundle.extractfile(member)
                    assert stream is not None
                    license_file(
                        python,
                        f"{index:05d}-{Path(member.name).name}",
                        stream.read(),
                        python_pin["url"] + "#" + member.name,
                    )
        for filename in (
            "build-cpython.sh",
            "build-openssl.sh",
            "build-sqlite3.sh",
            "build_utils.sh",
        ):
            save(
                python,
                destination,
                "sources/build-info/manylinux/" + filename,
                (Path("/opt/_internal/build_scripts") / filename).read_bytes(),
                "build_files",
            )
        configuration = {
            key: sysconfig.get_config_var(key)
            for key in ("CONFIG_ARGS", "CC", "CXX", "CFLAGS", "CFLAGS_NODIST", "LDFLAGS")
        }
        save(
            python,
            destination,
            "sources/build-info/manylinux/cpython-config.json",
            (json.dumps(configuration, indent=2, sort_keys=True) + "\n").encode(),
            "build_files",
        )

    manifest = json.loads((root / "packaging/native-evidence.json").read_text())
    groups = {}
    for target, path, _ in binaries:
        if target in claimed:
            continue
        result = subprocess.run(
            [
                "rpm",
                "-qf",
                "--qf",
                "%{NAME}|%{VERSION}-%{RELEASE}|%{SOURCERPM}",
                str(Path(path).resolve()),
            ],
            capture_output=True,
            text=True,
        )
        matches = [
            c
            for c in manifest["components"]
            if c["native_sha256"].get(target) == native_files[target]
        ]
        if len(matches) != 1:
            component(
                target,
                "UNRESOLVED",
                "UNRESOLVED",
                [target],
                "UNRESOLVED",
                "Identify exact native binary provenance and license/source materials.",
            )
            continue
        evidence = matches[0]
        if "source_rpm" in evidence and (
            result.returncode != 0
            or result.stdout != f"{evidence['name']}|{evidence['version']}|{evidence['source_rpm']}"
        ):
            component(
                target,
                "UNRESOLVED",
                "UNRESOLVED",
                [target],
                "UNRESOLVED",
                "RPM ownership/version/source RPM differs from reviewed evidence.",
            )
            continue
        groups.setdefault(evidence["name"], (evidence, []))[1].append(target)
    for name, (evidence, native) in sorted(groups.items()):
        c = component(
            name,
            evidence["version"],
            evidence["license"],
            native,
            evidence["source"]["url"],
            evidence["obligations"],
        )
        c["source_required"] = evidence["source_required"]
        c["source_evidence"] = dict(
            **evidence["source"],
            source_rpm=evidence.get("source_rpm"),
            binary_sha256={t: native_files[t] for t in sorted(native)},
        )
        c["package_license"] = evidence.get("package_license")
        try:
            for number, entry in enumerate(evidence["license_evidence"]):
                archive = fetch(entry, cache)
                for index, (member, data) in enumerate(
                    sorted(archive_texts(archive, entry).items())
                ):
                    license_file(
                        c,
                        f"{number}-{index}-{Path(member).name}",
                        data,
                        dict(
                            url=entry["url"],
                            sha256=entry["sha256"],
                            member=member,
                            inner=entry.get("inner"),
                        ),
                    )
            source_file(c, evidence["source"])
        except (
            OSError,
            ValueError,
            KeyError,
            subprocess.CalledProcessError,
            tarfile.TarError,
        ) as error:
            c["collection_errors"].append(
                f"License/source evidence collection failed for {name} {c['version']}: "
                f"{type(error).__name__}"
            )
    inventory = finalize(
        dict(
            schema=2,
            image=manifest["image"],
            freeze_distributions=sorted(
                (
                    dict(name=d.metadata["Name"], version=d.version)
                    for d in metadata.distributions(
                        path=sorted({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
                    )
                ),
                key=lambda d: d["name"].lower(),
            ),
            components=components,
            native_files=native_files,
            pure_modules=[name for name, _, _ in pure],
            combined_source_required=any(c["name"] in {"mutagen", "readline"} for c in components),
            combined_source_reason="Current bundled GPL components: "
            + ", ".join(
                sorted(c["name"] for c in components if c["name"] in {"mutagen", "readline"})
            ),
            source_distribution=dict(
                mechanism="GPLv3 section 6(d), GPLv2 section 3 network-access paragraph, "
                "and MPL-2.0 section 3.2; equivalent free access on the same versioned release",
                url=f"https://github.com/wittg3n/frogify-cli/releases/download/v{project_version}/"
                "frogify-linux-x86_64-sources.tar.gz",
            ),
        ),
        destination,
    )
    (destination / "inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check_release(path: Path) -> None:
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
        blockers = validate(inventory, path.parent)
        if inventory.get("blockers") != blockers:
            blockers.append("Serialized blockers differ from current verified evidence")
        if inventory.get("release_ready") is not (not blockers):
            blockers.append("Serialized release readiness differs from verified evidence")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        blockers = ["Invalid or unreadable compliance inventory"]
    if blockers:
        raise SystemExit("Standalone publication blocked:\n" + "\n".join(blockers))


def finalize_binary(directory: Path, executable: Path, *, stripped: bool) -> None:
    """Bind the inventory to actual frozen bytes, retaining pre-strip provenance."""
    from PyInstaller.archive.readers import CArchiveReader

    inventory_path = directory / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    archive = CArchiveReader(str(executable))
    if any(name.startswith("distribution/") for name in archive.toc):
        raise ValueError("Compliance evidence must not be embedded in the executable")
    native = {name for name, entry in archive.toc.items() if entry[-1] == "b"}
    if native != set(inventory["native_files"]):
        raise ValueError("Frozen native files differ from Analysis inventory")
    import hashlib

    inventory["native_input_sha256"] = inventory["native_files"]
    inventory["native_files"] = {
        name: hashlib.sha256(archive.extract(name)).hexdigest() for name in sorted(native)
    }
    inventory["native_symbols_stripped"] = stripped
    inventory["executable_sha256"] = digest(executable)
    finalize(inventory, directory)
    inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-release", type=Path, required=True)
    check_release(parser.parse_args().check_release)
