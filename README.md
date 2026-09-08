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

With **Python 3.12+**, [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html), and Git:

```shell
pipx install "git+https://github.com/wittg3n/frogify-cli.git"
```
then:

```shell
frogify "Massive Attack - Teardrop"
```

*Temporary GitHub install: the first PyPI release is not published yet.*
Prefer uv? See [Installation](#installation).

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

# Search before downloading; add --pick to a download to choose manually
frogify search "Daft Punk - Something About Us"

# Download a Spotify-exported library, resuming completed tracks
frogify batch spotify.csv

# Retry failures or check your environment
frogify retry
frogify doctor
```

Downloads go to **Downloads/music**. Use `--output "./my-music"` to choose another folder.
See the [CSV format](https://github.com/wittg3n/frogify-cli/blob/main/docs/usage.md#download-a-spotify-export-csv)
for required export columns.

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
candidates; `--pick` lets you choose explicitly.

The Spotify downloader workflow uses CSV metadata. The YouTube Music downloader workflow searches
YouTube recordings through MP3Juice and its resolution providers, alongside SoundCloud; there is
no official YouTube Music API integration. Free-text downloads preserve the source audio format.
CSV metadata tagging uses FFmpeg, copying MP3 input without re-encoding and converting other formats.

## Installation

Use the pipx command in [Quick start](#quick-start), or let **uv** manage Python:

```shell
uv tool install --python 3.13 "git+https://github.com/wittg3n/frogify-cli.git"
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

[MIT](https://github.com/wittg3n/frogify-cli/blob/main/LICENSE). Use Frogify only for audio you are
permitted to access and in accordance with the relevant service terms. Frogify is not affiliated
with Spotify, YouTube, YouTube Music, SoundCloud, MP3Juice, or Theta.
