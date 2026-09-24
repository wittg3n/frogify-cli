<p align="center">
  <img src="https://raw.githubusercontent.com/wittg3n/frogify-cli/main/public/logo.png" alt="Frogify logo" width="560">
</p>

<h1 align="center">Frogify</h1>

<p align="center">
  <strong>Find the right track. Download it. Keep your library clean.</strong><br>
  Spotify &amp; YouTube Music Downloader CLI
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.12 or newer"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/Windows%20%7C%20macOS%20%7C%20Linux-374151?style=flat-square" alt="Windows, macOS, and Linux"></a>
  <a href="https://github.com/wittg3n/frogify-cli/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-2F6B45?style=flat-square" alt="MIT license"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/wittg3n/frogify-cli/main/public/demo.gif" alt="Terminal demo: frogify &quot;Massive Attack - Teardrop&quot; downloads a selected recording and prints the saved path." width="800">
</p>

## Quick start

Install from source on Windows, macOS, or Linux with **uv** and **Git**. uv manages Python
3.13 and an isolated environment for Frogify:

```shell
uv tool install --python 3.13 "git+https://github.com/wittg3n/frogify-cli.git"
uv tool update-shell
```

Open a new terminal, then run:

```shell
frogify --version
frogify --help
frogify doctor
frogify "Massive Attack - Teardrop"
```

For uv, Git, and audio tools, follow the [platform setup guide](docs/installation.md#system-dependencies).
**FFmpeg is required for CSV metadata tagging**, which is enabled by default; aria2 is optional.
`doctor` checks local tools and provider reachability, so it may report missing tools or
unavailable providers before your first download.

The project version is **0.2.0**, an early pre-1.0 candidate. The
[standalone Linux installer](#standalone-linux) requires published GitHub Release assets.

## Why Frogify?

Finding a result is easy. Frogify tries to find the **right recording**.

- ✓ **Smart track matching** — title scoring and recording-version checks.
- ✓ **YouTube + SoundCloud search** — inspect candidates before choosing.
- ✓ **Spotify CSV importing** — turn exported playlists into local audio.
- ✓ **Duration verification** — compare batch downloads with the CSV's expected duration.
- ✓ **Metadata tagging** — write artist, album, and other available CSV tags.
- ✓ **Resumable batches** — skip completed tracks whose files still exist.
- ✓ **Retry queue** — return to failed downloads later.
- ✓ **aria2 acceleration** — optional, with a Requests fallback in automatic mode.
- ✓ **Windows / Linux / macOS** — one CLI and platform-aware storage paths.

As a Spotify playlist downloader, Frogify starts from an **exported CSV**. It finds audio
through supported search sources; it does not download Spotify streams or accept playlist URLs.

## Examples

```shell
# Download a track
frogify "Massive Attack - Teardrop"

# Search without downloading
frogify search "Daft Punk - Something About Us"

# Choose a recording interactively
frogify "Massive Attack - Teardrop" --pick

# Download a Spotify-exported library, resuming completed tracks
frogify batch spotify.csv

# Retry failures or check your environment
frogify retry
frogify doctor
```

By default, downloads go to a **music** subfolder in your system **Downloads** directory.
Use `--output "./my-music"` for one command, or set `download.directory` for future downloads.
Batch resume skips completed files that still exist; missing files are downloaded again.
Retries use each failure's saved destination unless you pass `--output`.
See the [CSV format](https://github.com/wittg3n/frogify-cli/blob/main/docs/usage.md#download-a-spotify-export-csv)
for required export columns.

## Configuration

Inspect settings, choose a default destination, or allow more time for provider retries:

```shell
frogify config
frogify config path
frogify config set download.directory "~/Downloads/music"
frogify config set network.retry_profile patient
```

To preserve the source audio format in CSV batches, disable metadata tagging with
`frogify config set metadata.enabled false`. See [all settings](docs/usage.md#configuration)
for download engines, matching limits, and retry profiles.

## How matching works

Frogify does not simply take the first search result.

```text
Query or Spotify CSV track
          ↓
Discover candidates
          ↓
Score titles + check recording versions
(CSV: also compare artists + expected duration)
          ↓
Rank candidates → reject unsafe automatic matches
          ↓
Download → validate audio
(CSV: verify downloaded duration)
          ↓
Save audio · CSV batches also write metadata
```

`search` and `--pick` show the source, duration, and **match score out of 100**. These scores
are ranking heuristics, not accuracy percentages. Automatic downloads try up to three accepted
candidates by default. Set `matching.candidate_attempts` to change the limit, or use
`--candidate-attempts` for a single-track download. `--pick` lets you choose explicitly.

The Spotify downloader workflow uses CSV metadata. The YouTube Music downloader workflow searches
YouTube recordings through MP3Juice and its resolution providers, alongside SoundCloud; there is
no official YouTube Music API integration. Free-text downloads preserve the source audio format.
CSV metadata tagging uses FFmpeg, copying MP3 input without re-encoding and converting other
formats to MP3 when tagging is enabled.

## Installation

### Standalone Linux

Once a [GitHub release](https://github.com/wittg3n/frogify-cli/releases) provides the standalone
assets, install without Python, pip, uv, or Git:

```sh
curl -fsSL https://raw.githubusercontent.com/wittg3n/frogify-cli/main/install.sh | sh
```

The binary targets **x86_64 / amd64 glibc-based Linux with glibc 2.17 or newer**.
ARM64, Alpine/musl, Windows, and macOS need the Python/source route.
FFmpeg, ffprobe, and optional aria2 remain external tools.

The installer verifies SHA-256 checksums and installs to `$HOME/.local/bin/frogify`.
Follow its PATH guidance if needed. Rerun it to update; download or validation failures
preserve the previous executable. Notices, the component inventory, and license texts are
saved under `${XDG_DATA_HOME:-$HOME/.local/share}/frogify/<version>/`.

Each standalone release pairs the binary with `frogify-linux-x86_64-sources.tar.gz` and
their checksums. The release workflow validates both assets before publishing; installation
downloads only the binary archive and its checksum. See the
[distribution notices](packaging/THIRD_PARTY_NOTICES.md) and
[source/build instructions](packaging/SOURCE_BUILD.md) for details.

### Python package installation

Use the source command in [Quick start](#quick-start), or install from a local checkout
with uv:

```shell
git clone https://github.com/wittg3n/frogify-cli.git
cd frogify-cli
uv tool install --python 3.13 .
uv tool update-shell
```

With an existing Python 3.12+ virtual environment, use `python -m pip install .` from the
checkout instead. Once the PyPI release is available, you can install by package name:

```shell
pip install frogify
```

**FFmpeg** is required for CSV metadata tagging; **aria2** is optional. Follow the
[installation guide](https://github.com/wittg3n/frogify-cli/blob/main/docs/installation.md) for
[Windows](https://github.com/wittg3n/frogify-cli/blob/main/docs/installation.md#windows),
[macOS](https://github.com/wittg3n/frogify-cli/blob/main/docs/installation.md#macos),
[Linux](https://github.com/wittg3n/frogify-cli/blob/main/docs/installation.md#linux),
[source/ZIP installation](https://github.com/wittg3n/frogify-cli/blob/main/docs/installation.md#install-frogify-from-a-checkout),
and PATH setup.

## Documentation

- [Installation and updates](https://github.com/wittg3n/frogify-cli/blob/main/docs/installation.md)
- [Commands and configuration](https://github.com/wittg3n/frogify-cli/blob/main/docs/usage.md#configuration)
- [Troubleshooting](https://github.com/wittg3n/frogify-cli/blob/main/docs/usage.md#troubleshooting)
- [Development and code layout](https://github.com/wittg3n/frogify-cli/blob/main/CONTRIBUTING.md)
- [Release process](https://github.com/wittg3n/frogify-cli/blob/main/docs/releasing.md)
- [Changelog](https://github.com/wittg3n/frogify-cli/blob/main/CHANGELOG.md)

## Contributing

Contributions and feedback on matching accuracy are welcome. See
[CONTRIBUTING.md](https://github.com/wittg3n/frogify-cli/blob/main/CONTRIBUTING.md)
for development setup, tests, and pull-request guidelines.

## License

Frogify's own source is [MIT licensed](LICENSE). The standalone executable includes third-party
components with separate terms; see the [distribution notices](packaging/THIRD_PARTY_NOTICES.md)
for licenses and corresponding source.

Use Frogify only for audio you are permitted to access and in accordance with the relevant
service terms. Frogify is not affiliated with Spotify, YouTube, YouTube Music, SoundCloud,
MP3Juice, or Theta.
