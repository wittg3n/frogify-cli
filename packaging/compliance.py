"""Evidence I/O and fail-closed validation for the standalone distribution."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative_file(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and not any(part in {"..", "."} or ":" in part or "\\" in part for part in path.parts)
    )


def fetch(source: dict, cache: Path) -> Path:
    """Never use a downloaded or cached archive before verifying its pinned hash."""
    expected = source["sha256"]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Missing SHA-256 source pin")
    url = source["url"]
    if not url.startswith("https://"):
        raise ValueError("Source origin must use HTTPS")
    output = cache / url.rsplit("/", 1)[-1]
    cache.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        with urllib.request.urlopen(url, timeout=120) as response:
            output.write_bytes(response.read())
    if digest(output) != expected:
        raise ValueError(f"Source checksum mismatch: {output.name}")
    return output


def archive_texts(archive: Path, evidence: dict) -> dict[str, bytes]:
    """Read named files without extracting archive paths onto the filesystem."""
    if archive.suffix == ".rpm":
        payload = subprocess.check_output(["rpm2cpio", str(archive)])
        members = set(
            subprocess.check_output(
                ["cpio", "--quiet", "-t"], input=payload, stderr=subprocess.PIPE
            )
            .decode()
            .splitlines()
        )

        def rpm_member(member):
            if not relative_file(member):
                raise ValueError("Unsafe RPM member")
            stored = next((name for name in (member, "./" + member) if name in members), None)
            if stored is None:
                raise ValueError(f"Missing RPM member: {member}")
            return subprocess.check_output(
                ["cpio", "--quiet", "-i", "--to-stdout", stored],
                input=payload,
                stderr=subprocess.PIPE,
            )

        if "inner" not in evidence:
            return {member: rpm_member(member) for member in evidence["members"]}
        stream = io.BytesIO(rpm_member(evidence["inner"]))
    else:
        stream = archive.open("rb")
    with stream, tarfile.open(fileobj=stream) as bundle:
        result = {}
        for member in evidence["members"]:
            entry = bundle.getmember(member)
            if not entry.isfile() or not relative_file(member):
                raise ValueError(f"Invalid license member: {member}")
            contents = bundle.extractfile(entry)
            assert contents is not None
            result[member] = contents.read()
        return result


def save(component: dict, directory: Path, filename: str, data: bytes, field: str) -> None:
    if not relative_file(filename) or not data:
        raise ValueError("Empty or unsafe evidence file")
    output = directory / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256(data).hexdigest()
    if not output.is_file() or digest(output) != sha256:
        output.write_bytes(data)
    component[field].append(filename)
    component["file_sha256"][filename] = sha256


def validate(inventory: dict, directory: Path) -> list[str]:
    """Recompute blockers; do not trust the serialized readiness assertion."""
    if inventory.get("schema") != 2:
        return ["Missing or unsupported compliance inventory schema"]
    components = inventory.get("components", [])
    if not components:
        return ["Missing bundled component inventory"]
    blockers = []
    names = [c["name"] for c in components]
    if len(names) != len(set(names)):
        blockers.append("Duplicate bundled component identity")
    for required in ("frogify", "cpython", "pyinstaller"):
        if required not in names:
            blockers.append(f"Missing bundled component: {required}")
    native = inventory.get("native_files", {})
    if not native or not inventory.get("pure_modules"):
        blockers.append("Missing PyInstaller native/pure Analysis inventory")
    owners = {}
    for component in components:
        name = component["name"]
        label = f"{name} {component.get('version', 'UNRESOLVED')}"
        for field in ("version", "license", "license_evidence", "source_evidence", "obligations"):
            if not component.get(field) or component[field] == "UNRESOLVED":
                blockers.append(f"Missing authoritative {field}: {label}")
        blockers.extend(component.get("collection_errors", []))
        licenses = component.get("license_files", [])
        if not licenses:
            blockers.append(f"Missing exact license/notice text: {label}")
        evidence = component.get("license_evidence")
        if not isinstance(evidence, list) or {
            entry.get("file")
            for entry in evidence
            if isinstance(entry, dict) and entry.get("origin")
        } != set(licenses):
            blockers.append(f"License files lack matching authoritative origins: {label}")
        sources = component.get("source_files", [])
        if sources and name != "frogify":
            evidence = component.get("source_evidence")
            if not isinstance(evidence, dict) or (
                evidence.get("file") not in sources
                or evidence.get("version") != component.get("version")
                or not isinstance(evidence.get("origin"), dict)
                or evidence["origin"].get("sha256")
                != component.get("file_sha256", {}).get(evidence.get("file"))
                or not evidence["origin"].get("url", "").startswith("https://")
            ):
                blockers.append(f"Source archive lacks matching version/origin/checksum: {label}")
        if not isinstance(component.get("source_required"), bool):
            blockers.append(f"Missing source-obligation decision: {label}")
        for vendor in component.get("vendored_components", []):
            vendor_label = f"{name}/{vendor['name']} {vendor.get('version', 'UNRESOLVED')}"
            if not vendor.get("license") or vendor["license"] == "UNRESOLVED":
                blockers.append(f"Missing authoritative vendor license: {vendor_label}")
            if not vendor.get("license_files") or not set(vendor["license_files"]) <= set(licenses):
                blockers.append(f"Missing exact vendor license text: {vendor_label}")
            if (
                vendor.get("source_verified") is not True
                or vendor.get("source_file") not in sources
            ):
                blockers.append(f"Missing verified vendor corresponding source: {vendor_label}")
        if component.get("source_required") is not False and not sources:
            blockers.append(f"Missing required corresponding-source archive: {label}")
        # Conservative packaging policy for the GPL combined work. This does not
        # assert that every component's individual license requires source delivery.
        if inventory.get("combined_source_required") and not sources:
            blockers.append(f"GPL combined-distribution source closure: missing source for {label}")
        files = licenses + sources + component.get("build_files", [])
        hashes = component.get("file_sha256", {})
        for filename in files:
            if not relative_file(filename):
                blockers.append(f"Unsafe or absolute evidence path: {name}")
                continue
            path = directory / filename
            if not path.resolve().is_relative_to(directory.resolve()):
                blockers.append(f"Evidence file escapes the distribution: {filename}")
                continue
            if not path.is_file() or path.stat().st_size == 0:
                blockers.append(f"Missing or empty evidence file: {filename}")
            elif digest(path) != hashes.get(filename):
                blockers.append(f"Evidence checksum mismatch: {filename}")
        for filename in component.get("native_files", []):
            if filename in owners:
                blockers.append(f"Native file assigned more than once: {filename}")
            owners[filename] = name
            if filename not in native:
                blockers.append(f"Native file absent from Analysis: {filename}")
    for filename, sha256 in native.items():
        if not relative_file(filename):
            blockers.append("Absolute or unsafe native Analysis path")
        if filename not in owners:
            blockers.append(f"Unaccounted bundled native library: {filename}")
        if not isinstance(sha256, str) or len(sha256) != 64:
            blockers.append(f"Missing native binary hash: {filename}")
    if {"mutagen", "readline"} & set(names) and inventory.get(
        "combined_source_required"
    ) is not True:
        blockers.append("Bundled GPL components require the combined-source closure check")
    if not any(c.get("build_files") for c in components if c["name"] == "frogify"):
        blockers.append("Missing Frogify standalone build/install materials")
    if "executable_sha256" in inventory:
        executable = directory / "frogify"
        if not executable.is_file() or digest(executable) != inventory["executable_sha256"]:
            blockers.append("Frozen executable checksum mismatch")
        if set(inventory.get("native_input_sha256", {})) != set(native):
            blockers.append("Missing native input provenance after freezing")
    return sorted(set(blockers))


def finalize(inventory: dict, directory: Path) -> dict:
    for component in inventory["components"]:
        for field in ("license_files", "native_files", "source_files", "build_files"):
            component[field] = sorted(set(component.get(field, [])))
    inventory["components"].sort(key=lambda c: c["name"])
    inventory["pure_modules"] = sorted(set(inventory["pure_modules"]))
    inventory["native_files"] = dict(sorted(inventory["native_files"].items()))
    inventory["blockers"] = validate(inventory, directory)
    inventory["release_ready"] = not inventory["blockers"]
    return inventory
