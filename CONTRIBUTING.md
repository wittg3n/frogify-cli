# Contributing to Frogify

Clone the repository and install the locked development environment:

```shell
uv sync --locked --python 3.13
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv build --no-sources
```

To expose your working checkout as a command:

```shell
uv tool install --reinstall --editable --python 3.13 .
```

| Location | Responsibility |
| --- | --- |
| `frogify/cli/` | Typer commands and Rich output. |
| `frogify/core/` | Download orchestration and request/result models. |
| `frogify/config.py` | Validated TOML settings and platform paths. |
| `frogify/storage.py` | SQLite state and legacy CSV import. |
| `mp3juice/` | Search, resolution, transfer, matching, and metadata. |
| `tests/` | Unit, integration, and protocol regression checks. |

Tests use controlled providers; the FFmpeg and aria2 integration checks require those executables.
Install FFmpeg (including ffprobe) and aria2 using the [installation guide](docs/installation.md).
CI requires both integration checks to run on Python 3.12 and 3.13 on Ubuntu, Windows, and macOS.
A passing local test suite does not certify live provider availability or every operating system.
Release builds include source, tests, documentation, and the logo; personal exports, downloads,
local state, and generated artifacts are excluded.

Contributions are welcome. Include a clear reproduction for bug reports and explain how changes
were verified. See the [changelog](CHANGELOG.md) for project changes.

Keep changes focused. Add a regression check for changed behavior, use controlled providers in
tests, and avoid committing local configuration, audio downloads, or personal CSV exports.
Sanitize cookies, signed URLs, and private paths from shared diagnostics.

Maintainers can follow the [release guide](docs/releasing.md) to publish the built distributions.
