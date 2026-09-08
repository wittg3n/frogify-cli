# Publishing Frogify

The package and CLI currently declare `2.0.0`. The workflows are prepared for the first
GitHub/PyPI release; adding these files does not itself publish a release. Keep the README's
GitHub install commands until the PyPI distributions are available and verified.

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
   `Unreleased` changelog entries under the release heading. For the first public `2.0.0`
   release, combine them with the existing `2.0.0` entries.
2. Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md), then push the release commit
   and wait for CI. Inspect the downloadable `dist` artifact if needed.
3. Create a GitHub release draft tagged **v2.0.0** at that exact commit, titled
   **Frogify v2.0.0**. Use the draft notes below and review them before publishing.
4. Publishing the GitHub release triggers `publish.yml`. It reruns the complete CI workflow,
   checks that the tag matches both package versions, builds and smoke-tests the wheel and
   source archive, and attaches them to the GitHub release. The separate `pypi` job then
   publishes those same artifacts after any environment approval.
5. Check the GitHub release assets and PyPI project page. From an environment without the
   source checkout, verify the package and command:

   ```shell
   uvx --from frogify==2.0.0 frogify --version
   uvx --from frogify==2.0.0 frogify --help
   ```

6. Once verified, replace the GitHub URLs in the README's quick start and Installation section
   with `pipx install frogify` and `uv tool install --python 3.13 frogify`, remove the preparation
   note, and add a dynamic PyPI version badge linked to the project page. Add the CI status badge
   only after the workflow exists remotely and its status link works.

PyPI versions cannot be replaced with different artifacts. If a published package needs a fix,
bump the version and make a new release. If publishing fails before upload, correct the publisher
or environment configuration and rerun the failed job. Do not change a published release tag.

The workflow follows the [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/):
build/check jobs have read permissions, GitHub asset upload has contents-write permission, and
only the PyPI job can request a publishing identity.

## Draft release notes: Frogify v2.0.0

Frogify is a Spotify and YouTube Music downloader CLI with smart track matching, CSV metadata
tagging, and resumable batches. Find the right track. Download it. Keep your library clean.

- Rank YouTube and SoundCloud candidates, with recording-version checks and visible match scores.
- Import Spotify-export CSVs with artist and expected-duration matching.
- Validate downloaded audio and write CSV metadata through FFmpeg.
- Resume completed batches from SQLite and retry persisted failures.
- Use aria2 acceleration or the built-in Requests transfer engine.
- Run on Windows, macOS, and Linux with Python 3.12 or newer.

Install from this release's wheel, or use the README's verified installation method.
FFmpeg is required for CSV metadata; aria2 is optional. Spotify supplies the CSV metadata,
while audio search and resolution use MP3Juice and its supported providers.

See [installation](installation.md), [usage](usage.md), and the [changelog](../CHANGELOG.md).
