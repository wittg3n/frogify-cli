# Publishing Frogify

The package and CLI currently declare `0.2.0`. The workflows are prepared for the first
GitHub/PyPI release; adding these files does not itself publish a release. The Linux installer
requires a published release with the standalone assets. Keep the Python source installation
alternative until the PyPI distributions are available and verified.

This is an early public pre-1.0 candidate, not a published release. **Do not create
the tag or publish until the patch is reviewed and the standalone compliance blockers
in [the distribution notices](../packaging/THIRD_PARTY_NOTICES.md) are resolved.**
PyPI Trusted Publisher and GitHub environment configuration must be checked externally.

## One-time setup

1. Push the reviewed launch changes, including `public/demo.gif`, and wait for all CI jobs.
2. Create the GitHub environment **pypi** in this repository's settings. Configure a required
   reviewer if you want a manual publishing gate.
3. In your PyPI account, add a [pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
   for a new project, or a publisher under the existing project's Publishing settings if you
   already own the name. A missing project page does not guarantee that a name can be claimed.

   | PyPI field | Value |
   | --- | --- |
   | Project name | `frogify` |
   | Owner | `wittg3n` |
   | Repository name | `frogify-cli` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

No long-lived PyPI token is needed. The publish job requests a short-lived identity through
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Publish a version

1. Confirm the version matches in `pyproject.toml`, `frogify/__init__.py`, and `uv.lock`.
   For a new version, run `uv lock` after editing the version fields. Move the applicable
   `Unreleased` changelog entries under the release heading. The first public `0.2.0`
   entries are already consolidated, without an invented publication date.
2. Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md), then push the release commit
   and wait for CI. Inspect the downloadable `dist` and `linux-binary` artifacts if needed.
3. Create a GitHub release draft tagged **v0.2.0** at that exact commit, titled
   **Frogify v0.2.0**. Use the draft notes below and review them before publishing.
4. Publishing the GitHub release triggers `publish.yml`. It reruns the complete CI workflow,
   checks that the tag matches both package versions, builds and smoke-tests the wheel and
   source archive, and standalone executable, and attaches them to the GitHub release.
   The separate `pypi` job publishes only the wheel and sdist after any environment approval.
5. Check the GitHub release assets and PyPI project page. From an environment without the
   source checkout, verify the package and command:

   ```shell
   uvx --from frogify==0.2.0 frogify --version
   uvx --from frogify==0.2.0 frogify --help
   ```

6. Once verified, remove the preparation notes and document `pip install frogify` and
   `uv tool install --python 3.13 frogify` in the Python package section. Keep the standalone
   Linux quick start. Add badges only after their remote destinations work.

## Standalone Linux build

With Docker running, from the repository root:

```sh
docker build -f packaging/Dockerfile -t frogify-linux-builder .
docker run --rm -v "$PWD:/src" frogify-linux-builder
```

`packaging/Dockerfile` pins the official PyPA manylinux2014 x86_64 image (glibc 2.17).
That image's CPython is static: the build compiles the matching CPython 3.12.14 shared
embedding library from checksum-verified python.org sources, retaining the image's stdlib
and extensions. PyInstaller and its hooks are build-only dependencies locked in `uv.lock`.
`packaging/frogify.spec` follows static imports into both `frogify` and `mp3juice`; maintained
dependency hooks cover RapidFuzz's dynamic native backends and Requests' certificate data.
The launcher restores the original library search path for external FFmpeg/ffprobe/aria2.
No application commands or download behavior change.

The output in `dist/binary` is exactly:

- `frogify-linux-x86_64.tar.gz`, containing `frogify`, `THIRD_PARTY_NOTICES.md`,
  `inventory.json`, `licenses/`, and `sources/` at its root. These materials are also
  embedded in the executable so the installer's single-file copy retains them.
- `frogify-linux-x86_64.tar.gz.sha256`, using the standard SHA-256/filename format.

CI checks the archive, checksum, version, help and doctor in isolated CentOS 7 (glibc 2.17)
and Debian containers, with no checkout mounted and networking disabled. Debian has no
Python interpreter. CentOS 7 is an EOL compatibility test fixture, not an OS recommendation.
Doctor may report absent external tools/providers, but its imports, config and database
checks must succeed. CI also installs the actual archive through offline curl fixtures into
a temporary directory. A failed binary check blocks both release uploads and PyPI publishing.

The build collects actual bundled Python distributions and native-library metadata,
copies available license texts and includes checksum-verified Mutagen source. The stripped
manylinux image does not retain all RPM license files. The generated inventory names the
missing materials and `packaging/notices.py --check-release` currently fails deliberately.
Neither a successful build nor a successful runtime smoke test clears this publication gate.
The gate also blocks PyPI while the coordinated release remains incomplete.

For fresh local artifacts without touching older builds, set `FROGIFY_DIST_DIR` on the
build container, for example `-e FROGIFY_DIST_DIR=dist/candidate-0.2.0`. Build Python
artifacts with `uv build --no-sources --out-dir dist/candidate-0.2.0/python` and run
`uvx --from twine twine check --strict dist/candidate-0.2.0/python/*`.

The development constraint now requires pytest >=9.0.3 because
[CVE-2025-71176](https://github.com/advisories/GHSA-6w46-j5rx-g56g) affects all earlier
versions, including 8.x. The repository uses standard pytest fixtures and no third-party
pytest plugins. Validate the complete suite after updating the lockfile.

Update pinned container digests, CPython source version/checksum, and build dependencies
together when maintaining the runtime; rerun both compatibility checks. Builds have locked
inputs and normalized archive metadata, but are not promised to be byte-for-byte reproducible.

PyPI versions cannot be replaced with different artifacts. If a published package needs a fix,
bump the version and make a new release. If publishing fails before upload, correct the publisher
or environment configuration and rerun the failed job. Do not change a published release tag.

The workflow follows the [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/):
build/check jobs have read permissions, GitHub asset upload has contents-write permission, and
only the PyPI job can request a publishing identity.

## Draft release notes: Frogify v0.2.0

Frogify is a Spotify and YouTube Music downloader CLI with smart track matching, CSV metadata
tagging, and resumable batches. Find the right track. Download it. Keep your library clean.

- Rank YouTube and SoundCloud candidates, with recording-version checks and visible match scores.
- Import Spotify-export CSVs with artist and expected-duration matching.
- Validate downloaded audio and write CSV metadata through FFmpeg.
- Resume completed batches from SQLite and retry persisted failures.
- Use aria2 acceleration or the built-in Requests transfer engine.
- Run on Windows, macOS, and Linux with Python 3.12 or newer.
- Install the standalone Linux x86_64 executable without installing Python.

Install from this release's wheel, or use the README's verified installation method.
FFmpeg is required for CSV metadata; aria2 is optional. Spotify supplies the CSV metadata,
while audio search and resolution use MP3Juice and its supported providers.

See [installation](installation.md), [usage](usage.md), and the [changelog](../CHANGELOG.md).
