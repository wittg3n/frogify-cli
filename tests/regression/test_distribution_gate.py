import copy
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
NOTICES = runpy.run_path(str(ROOT / "packaging/notices.py"))
HELPERS = runpy.run_path(str(ROOT / "packaging/compliance.py"))
RELEASE = runpy.run_path(str(ROOT / "packaging/release_set.py"))


@pytest.fixture
def resolved(tmp_path):
    components = []
    for name in ("frogify", "cpython", "pyinstaller"):
        component = dict(
            name=name,
            version="fixture",
            license="MIT",
            obligations="Retain notice",
            license_evidence=[dict(file=f"licenses/{name}/LICENSE", origin="Synthetic fixture")],
            source_evidence="Synthetic fixture",
            license_files=[],
            source_files=[],
            build_files=[],
            native_files=[],
            file_sha256={},
            source_required=False,
        )
        HELPERS["save"](
            component, tmp_path, f"licenses/{name}/LICENSE", b"fixture notice", "license_files"
        )
        components.append(component)
    HELPERS["save"](
        components[0], tmp_path, "sources/build-info/build.sh", b"fixture recipe", "build_files"
    )
    components[1]["native_files"] = ["libpython.so"]
    return dict(
        schema=2,
        components=components,
        native_files={"libpython.so": "0" * 64},
        pure_modules=["frogify"],
        combined_source_required=False,
    )


def write_inventory(inventory, directory):
    result = HELPERS["finalize"](inventory, directory)
    path = directory / "inventory.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path, result


def test_readiness_and_successful_component(tmp_path, resolved):
    path, inventory = write_inventory(resolved, tmp_path)
    assert inventory["blockers"] == []
    assert inventory["release_ready"] is True
    NOTICES["check_release"](path)


@pytest.mark.parametrize(
    "failure", ["license", "empty_license", "source", "checksum", "unknown", "native"]
)
def test_missing_evidence_blocks(tmp_path, resolved, failure):
    component = resolved["components"][0]
    if failure == "license":
        component["license_files"] = []
    elif failure == "empty_license":
        (tmp_path / component["license_files"][0]).write_bytes(b"")
    elif failure == "source":
        component["source_required"] = True
    elif failure == "checksum":
        component["file_sha256"][component["license_files"][0]] = "0" * 64
    elif failure == "unknown":
        component["license"] = "UNRESOLVED"
    else:
        resolved["native_files"]["unknown.so"] = "1" * 64
    path, inventory = write_inventory(resolved, tmp_path)
    assert inventory["blockers"]
    assert inventory["release_ready"] is False
    with pytest.raises(SystemExit, match="publication blocked"):
        NOTICES["check_release"](path)


def test_source_material_clears_source_blocker(tmp_path, resolved):
    component = resolved["components"][0]
    component["source_required"] = True
    HELPERS["save"](component, tmp_path, "sources/source.tar", b"synthetic source", "source_files")
    assert HELPERS["finalize"](resolved, tmp_path)["release_ready"] is True


def test_checker_revalidates_files_and_does_not_trust_flags(tmp_path, resolved):
    path, inventory = write_inventory(resolved, tmp_path)
    (tmp_path / "licenses/frogify/LICENSE").unlink()
    assert inventory["release_ready"] is True
    with pytest.raises(SystemExit, match="Missing or empty evidence file"):
        NOTICES["check_release"](path)


@pytest.mark.parametrize("name", ["readline", "mutagen"])
def test_gpl_component_cannot_disable_combined_source_check(tmp_path, resolved, name):
    component = copy.deepcopy(resolved["components"][0])
    component.update(name=name, version="fixture", source_required=True)
    resolved["components"].append(component)
    blockers = HELPERS["finalize"](resolved, tmp_path)["blockers"]
    assert any("combined-source closure check" in b for b in blockers)
    resolved["combined_source_required"] = True
    blockers = HELPERS["finalize"](resolved, tmp_path)["blockers"]
    assert any(f"missing source for {name} fixture" in b for b in blockers)


def test_inventory_is_deterministic(tmp_path, resolved):
    first = copy.deepcopy(resolved)
    second = copy.deepcopy(resolved)
    first["pure_modules"] = ["z", "frogify", "a"]
    second["pure_modules"] = ["a", "z", "frogify"]
    second["components"].reverse()
    assert HELPERS["finalize"](first, tmp_path) == HELPERS["finalize"](second, tmp_path)
    serialized = json.dumps(first)
    assert str(tmp_path) not in serialized
    assert str(ROOT) not in serialized


@pytest.mark.parametrize(
    "filename", ["/tmp/LICENSE", "C:/runner/LICENSE", "C:\\runner\\LICENSE", "../LICENSE"]
)
def test_absolute_or_escaping_paths_are_rejected(tmp_path, resolved, filename):
    resolved["components"][0]["license_files"] = [filename]
    assert any(
        "absolute evidence path" in b for b in HELPERS["finalize"](resolved, tmp_path)["blockers"]
    )


@pytest.mark.parametrize("blocked", [False, True])
def test_checker_process_exit_status(tmp_path, resolved, blocked):
    if blocked:
        resolved["components"][0]["license_files"] = []
    path, _ = write_inventory(resolved, tmp_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "packaging/notices.py"), "--check-release", str(path)],
        capture_output=True,
        text=True,
    )
    assert (result.returncode != 0) == blocked


def test_source_checksum_is_verified_before_use(tmp_path):
    (tmp_path / "source.tar").write_bytes(b"altered source")
    with pytest.raises(ValueError, match="checksum mismatch"):
        HELPERS["fetch"](
            {"url": "https://example.invalid/source.tar", "sha256": "0" * 64}, tmp_path
        )


def test_source_evidence_must_identify_version_origin_and_hash(tmp_path, resolved):
    component = resolved["components"][1]
    HELPERS["save"](component, tmp_path, "sources/python.tar", b"fixture", "source_files")
    assert any(
        "Source archive lacks matching" in b
        for b in HELPERS["finalize"](resolved, tmp_path)["blockers"]
    )


def test_missing_vendor_materials_block(tmp_path, resolved):
    resolved["components"][0]["vendored_components"] = [
        dict(name="vendor", version="1", license="UNRESOLVED", source_verified=False)
    ]
    blockers = HELPERS["finalize"](resolved, tmp_path)["blockers"]
    assert any("vendor license" in b for b in blockers)
    assert any("vendor corresponding source" in b for b in blockers)


@pytest.mark.parametrize("stored", ["source.tar", "./source.tar"])
def test_rpm_member_names_with_or_without_dot_prefix(tmp_path, monkeypatch, stored):
    def check_output(command, **kwargs):
        if command[0] == "rpm2cpio":
            return b"payload"
        if "-t" in command:
            return (stored + "\n").encode()
        assert command[-1] == stored
        return b"license content"

    monkeypatch.setattr(subprocess, "check_output", check_output)
    assert HELPERS["archive_texts"](tmp_path / "source.rpm", {"members": ["source.tar"]}) == {
        "source.tar": b"license content"
    }


def test_actual_archive_evidence_matches_inventory():
    artifact_dir = os.environ.get("FROGIFY_TEST_ARTIFACT_DIR")
    if not artifact_dir:
        pytest.skip("requires the built standalone archive")
    archive = Path(artifact_dir) / "frogify-linux-x86_64.tar.gz"
    RELEASE["check"](Path(artifact_dir))
    with tarfile.open(archive) as bundle:
        names = set(bundle.getnames())
        # A Python package named "licenses" is code, not redistributable notice text.
        assert not any(name.startswith("licenses/") and name.endswith(".pyc") for name in names)
        assert {
            "frogify",
            "THIRD_PARTY_NOTICES.md",
            "inventory.json",
            "licenses",
        } <= names
        assert not any(name == "sources" or name.startswith("sources/") for name in names)
        stream = bundle.extractfile("inventory.json")
        assert stream is not None
        inventory = json.load(stream)
        assert inventory["release_ready"] == (not inventory["blockers"])
        for component in inventory["components"]:
            for name in component["license_files"]:
                expected = component["file_sha256"][name]
                stream = bundle.extractfile(name)
                assert stream is not None
                assert hashlib.sha256(stream.read()).hexdigest() == expected


@pytest.mark.parametrize("failure", [None, "source", "checksum", "corruption", "version"])
def test_complete_release_set_is_required(tmp_path, resolved, failure):
    resolved["source_distribution"] = {
        "url": "https://github.com/wittg3n/frogify-cli/releases/download/vfixture/"
        "frogify-linux-x86_64-sources.tar.gz"
    }
    (tmp_path / "frogify").write_bytes(b"synthetic executable")
    resolved["executable_sha256"] = HELPERS["digest"](tmp_path / "frogify")
    resolved["native_input_sha256"] = resolved["native_files"].copy()
    write_inventory(resolved, tmp_path)
    (tmp_path / "THIRD_PARTY_NOTICES.md").write_text("synthetic notices")
    output = tmp_path / "release"
    RELEASE["build"](tmp_path, output)
    source = output / RELEASE["SOURCES"]
    if failure == "source":
        source.unlink()
    elif failure == "checksum":
        (output / (source.name + ".sha256")).unlink()
    elif failure == "corruption":
        source.write_bytes(b"corrupt source")
    elif failure == "version":
        path = output / "release-set.json"
        manifest = json.loads(path.read_text())
        manifest["version"] = "different"
        path.write_text(json.dumps(manifest))
    if failure:
        with pytest.raises((OSError, ValueError)):
            RELEASE["check"](output)
    else:
        assert RELEASE["check"](output)["version"] == "fixture"


@pytest.mark.parametrize(
    "inventory",
    [{}, {"release_ready": False}, {"release_ready": True, "blockers": ["missing source"]}],
)
def test_unresolved_distribution_cannot_be_published(tmp_path, inventory):
    check = runpy.run_path(str(Path(__file__).parents[2] / "packaging/notices.py"))["check_release"]
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(SystemExit, match="publication blocked"):
        check(path)
