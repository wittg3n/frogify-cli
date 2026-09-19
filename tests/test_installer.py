"""Exercise the real POSIX installer with offline GitHub release fixtures."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux installer")
INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"
ARCHIVE = "frogify-linux-x86_64.tar.gz"


@pytest.fixture
def release(tmp_path):
    bin_dir = tmp_path / "tools"
    bin_dir.mkdir()
    for name in ("cp", "tar", "gzip", "mkdir", "mktemp", "chmod", "mv", "rm", "sha256sum"):
        (bin_dir / name).symlink_to(shutil.which(name))
    for name, script in {
        "uname": """case "$1" in
    -s) echo "${TEST_OS:-Linux}" ;;
    -m) echo "${TEST_ARCH:-x86_64}" ;;
esac""",
        "curl": """
echo "$*" >> "$FIXTURE/urls"
output=
url=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --output) output=$2; shift ;;
        https://*) url=$1 ;;
    esac
    shift
done
case "$url" in
    */releases/latest)
        default=https://github.com/wittg3n/frogify-cli/releases/tag/v0.2.0
        printf '%s' "${TEST_LATEST:-$default}" ;;
    */frogify-linux-x86_64.tar.gz.sha256) cp "$FIXTURE/checksum" "$output" ;;
    */frogify-linux-x86_64.tar.gz)
        [ "${TEST_DOWNLOAD_FAIL:-0}" = 0 ] || exit 22
        cp "$FIXTURE/frogify-linux-x86_64.tar.gz" "$output" ;;
    *) exit 22 ;;
esac
""",
    }.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\nset -eu\n" + script + "\n")
        path.chmod(0o755)
    content = b"#!/bin/sh\necho fixture-frogify\n"
    with tarfile.open(tmp_path / ARCHIVE, "w:gz") as archive:
        member = tarfile.TarInfo("frogify")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
        notice = b"fixture license notice"
        member = tarfile.TarInfo("licenses/fixture/LICENSE")
        member.size = len(notice)
        archive.addfile(member, io.BytesIO(notice))
    digest = hashlib.sha256((tmp_path / ARCHIVE).read_bytes()).hexdigest()
    (tmp_path / "checksum").write_text(f"{digest}  {ARCHIVE}\n")
    (tmp_path / "temporary").mkdir()
    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "temporary"),
        "FROGIFY_INSTALL_DIR": str(tmp_path / "installed bin"),
        "FIXTURE": str(tmp_path),
    }
    return tmp_path, env, content


def install(release, **overrides):
    root, env, _ = release
    result = subprocess.run(
        ["/bin/sh", str(INSTALLER)],
        env=env | overrides,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert not list((root / "temporary").iterdir())
    assert not list(root.glob("installed bin/.frogify-install.*"))
    return result


def test_shell_syntax():
    subprocess.run(["/bin/sh", "-n", str(INSTALLER)], check=True)


@pytest.mark.parametrize("arch", ["x86_64", "amd64"])
@pytest.mark.parametrize("version", ["", "0.2.0", "v0.2.0"])
def test_install_and_reinstall(release, arch, version):
    root, env, content = release
    result = install(release, TEST_ARCH=arch, FROGIFY_VERSION=version)
    assert result.returncode == 0, result.stderr
    binary = Path(env["FROGIFY_INSTALL_DIR"]) / "frogify"
    assert binary.read_bytes() == content
    assert os.access(binary, os.X_OK)
    assert "Checksum verified." in result.stdout
    assert "Add this directory to your PATH:" in result.stdout
    urls = (root / "urls").read_text()
    assert f"/releases/download/v0.2.0/{ARCHIVE}" in urls
    assert ("/releases/latest" in urls) == (not version)
    binary.write_text("old binary")
    assert install(release, FROGIFY_VERSION="v0.2.0").returncode == 0
    assert binary.read_bytes() == content


def test_default_directory(release):
    root, env, content = release
    del env["FROGIFY_INSTALL_DIR"]
    assert install(release).returncode == 0
    assert (root / "home/.local/bin/frogify").read_bytes() == content


@pytest.mark.parametrize("arch", ["aarch64", "arm64", "armv7l", "i686"])
def test_unsupported_architecture(release, arch):
    result = install(release, TEST_ARCH=arch)
    assert result.returncode != 0
    assert f"Detected architecture: {arch}" in result.stderr
    assert not (release[0] / "urls").exists()


def test_unsupported_os(release):
    result = install(release, TEST_OS="Darwin")
    assert result.returncode != 0
    assert "Unsupported operating system: Darwin" in result.stderr


@pytest.mark.parametrize("failure", ["download", "checksum", "extract", "members"])
def test_failure_preserves_existing_binary(release, failure):
    root, env, _ = release
    binary = Path(env["FROGIFY_INSTALL_DIR"]) / "frogify"
    binary.parent.mkdir()
    binary.write_text("keep me")
    overrides = {}
    if failure == "download":
        overrides["TEST_DOWNLOAD_FAIL"] = "1"
    elif failure in ("checksum", "extract"):
        (root / ARCHIVE).write_bytes(b"corrupt")
        if failure == "extract":
            digest = hashlib.sha256(b"corrupt").hexdigest()
            (root / "checksum").write_text(f"{digest}  {ARCHIVE}\n")
    else:
        with tarfile.open(root / ARCHIVE, "w:gz") as archive:
            archive.addfile(tarfile.TarInfo("../outside"))
        digest = hashlib.sha256((root / ARCHIVE).read_bytes()).hexdigest()
        (root / "checksum").write_text(f"{digest}  {ARCHIVE}\n")
    result = install(release, **overrides)
    assert result.returncode != 0
    assert binary.read_text() == "keep me"
    if failure == "checksum":
        assert "Checksum verification failed." in result.stderr
    assert not (root / "outside").exists()


def test_missing_checksum_tools(release):
    (release[0] / "tools/sha256sum").unlink()
    result = install(release)
    assert result.returncode != 0
    assert "No SHA-256 verification tool was found" in result.stderr


@pytest.mark.parametrize("member", ["licenses/../../outside", "/outside", "frogify"])
def test_rejects_unsafe_or_duplicate_members(release, member):
    root, _, content = release
    with tarfile.open(root / ARCHIVE, "w:gz") as archive:
        for name in ("frogify", member):
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    digest = hashlib.sha256((root / ARCHIVE).read_bytes()).hexdigest()
    (root / "checksum").write_text(f"{digest}  {ARCHIVE}\n")
    assert install(release).returncode != 0
    assert not (root / "outside").exists()


def test_shasum_fallback(release):
    root, _, _ = release
    (root / "tools/sha256sum").unlink()
    shasum = shutil.which("shasum")
    assert shasum, "CI must provide shasum to exercise the fallback"
    (root / "tools/shasum").symlink_to(shasum)
    assert install(release).returncode == 0


@pytest.mark.parametrize("suffix,present", [("", True), ("-other", False)])
def test_path_membership(release, suffix, present):
    _, env, _ = release
    result = install(release, PATH=env["PATH"] + ":" + env["FROGIFY_INSTALL_DIR"] + suffix)
    assert result.returncode == 0
    assert ("Run:" in result.stdout) == present
    assert ("Add this directory to your PATH:" in result.stdout) != present


@pytest.mark.parametrize("version", ["../evil", "v", "0.2.0/evil", "0.2.0;echo bad"])
def test_invalid_version(release, version):
    result = install(release, FROGIFY_VERSION=version)
    assert result.returncode != 0
    assert "Invalid Frogify version" in result.stderr


def test_unexpected_latest_redirect(release):
    result = install(release, TEST_LATEST="https://example.com/v0.2.0")
    assert result.returncode != 0
    assert "Unexpected latest release URL" in result.stderr


@pytest.mark.skipif(
    not os.environ.get("FROGIFY_TEST_ARTIFACT_DIR"), reason="No built release supplied"
)
def test_installs_built_release(release):
    root, env, _ = release
    artifacts = Path(os.environ["FROGIFY_TEST_ARTIFACT_DIR"])
    shutil.copyfile(artifacts / ARCHIVE, root / ARCHIVE)
    shutil.copyfile(artifacts / f"{ARCHIVE}.sha256", root / "checksum")
    result = install(release)
    assert result.returncode == 0, result.stderr
    binary = Path(env["FROGIFY_INSTALL_DIR"]) / "frogify"
    assert binary.read_bytes().startswith(b"\x7fELF")
    for option in ("--version", "--help"):
        subprocess.run([str(binary), option], env=env, cwd=root, check=True, timeout=30)
