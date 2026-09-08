<p align="center">
  <img src="public/logo.png" alt="Frogify" width="760">
</p>

<p align="center">
  <strong>Find the right recording. Keep your library organized.</strong><br>
  A music downloader for your terminal, with careful matching and resumable CSV batches.
</p>

<p align="center">
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/version-2.0.0-2F6B45?style=flat-square" alt="Version 2.0.0"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.12 or newer"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-374151?style=flat-square" alt="Windows, macOS, and Linux"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/install%20with-uv-DE5FE9?style=flat-square&amp;logo=uv&amp;logoColor=white" alt="Install with uv"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2F6B45?style=flat-square" alt="MIT license"></a>
</p>

<p align="center">
  <a href="#installation">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#download-location">Download location</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#troubleshooting">Troubleshooting</a> ·
  <a href="#development">Development</a>
</p>

---

Frogify searches MP3Juice, resolves audio through its supported providers, and saves verified
downloads to your system's **Downloads/music** folder. Download a single track by name, inspect
results before choosing, or work through a Spotify-export CSV with progress saved after each track.

```shell
frogify "Massive Attack Teardrop"
frogify search "Daft Punk Something About Us"
frogify batch "path/to/playlist.csv"
```

## Features

- **Careful matching** — ranks results by relevance and checks recording versions; CSV matching
  also compares artist and duration. Use `--pick` when you want to choose a result yourself.
- **Resumable batches** — records completed tracks in SQLite, skips files that still exist, and
  downloads missing files again.
- **Safe file handling** — stages replacements before publishing, handles filename collisions,
  and preserves the original if a forced replacement fails.
- **Useful metadata** — writes Spotify-export tags with FFmpeg, without re-encoding MP3 input.
- **Flexible transfers** — uses aria2 when available, with a Requests fallback in automatic mode.
- **Visible progress** — displays track counts, transfer progress, status, and retryable failures.

## Installation

Frogify requires **Python 3.12 or newer**. The recommended installation uses
[uv](https://docs.astral.sh/uv/getting-started/installation/) to manage Python and give Frogify
its own environment. You do not need to activate a virtual environment for everyday use.

| Component | When you need it |
| --- | --- |
| Python 3.12+ | Required; uv can install it for supported platforms. |
| Git | Needed to clone this repository; downloading and extracting its source ZIP also works. |
| FFmpeg | Required for batch metadata, enabled by default. |
| ffprobe | Fallback audio-duration validation; normally included with FFmpeg. |
| aria2 | Optional acceleration for final audio transfers. Its command is `aria2c`. |

**Choose your platform below, then follow [Install Frogify](#install-frogify).**

### Windows

Run these commands in PowerShell with
[WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/):

```powershell
winget install --exact --id astral-sh.uv
winget install --exact --id Git.Git
winget install --exact --id Gyan.FFmpeg
winget install --exact --id aria2.aria2
```

Close and reopen PowerShell after installation so the new commands are on `PATH`.
Then continue to [Install Frogify](#install-frogify).

<details>
<summary><strong>Windows without WinGet</strong></summary>

Install uv using its [official PowerShell installer](https://docs.astral.sh/uv/getting-started/installation/):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install [Git for Windows](https://git-scm.com/downloads/win), obtain FFmpeg from the
[builds linked by FFmpeg](https://www.ffmpeg.org/download.html), and optionally install
[aria2](https://aria2.github.io/). Add the directories containing `ffmpeg.exe`, `ffprobe.exe`,
and `aria2c.exe` to your user `PATH`, then reopen PowerShell.

</details>

### macOS

Install [Homebrew](https://brew.sh/) if needed and follow its shell setup instructions.
Then install the tools:

```bash
brew install uv git ffmpeg aria2
```

The same commands apply to Apple Silicon and Intel Macs supported by Homebrew.
See the official [FFmpeg](https://formulae.brew.sh/formula/ffmpeg) and
[aria2](https://formulae.brew.sh/formula/aria2) formula pages for current availability.
Continue to [Install Frogify](#install-frogify).

### Linux

Install the system tools for your distribution. Commands using `sudo` require administrator
access; on a root shell, omit `sudo`.

<details open>
<summary><strong>Ubuntu · Debian · Linux Mint · Pop!_OS · Kali · Raspberry Pi OS</strong></summary>

```bash
sudo apt update
sudo apt install git curl ffmpeg aria2
```

Ubuntu's [FFmpeg package](https://packages.ubuntu.com/noble/ffmpeg) is in the Universe
repository. If it is unavailable on an Ubuntu installation, enable Universe first:

```bash
sudo add-apt-repository universe
sudo apt update
sudo apt install ffmpeg
```

</details>

<details>
<summary><strong>Fedora</strong></summary>

```bash
sudo dnf install git curl ffmpeg-free aria2
```

Fedora provides [ffmpeg-free](https://packages.fedoraproject.org/pkgs/ffmpeg/) and
[aria2](https://packages.fedoraproject.org/pkgs/aria2/aria2/).
If your FFmpeg build lacks an audio codec you need, use a build with that codec enabled.
See [FFmpeg's package links](https://www.ffmpeg.org/download.html) for alternatives.

</details>

<details>
<summary><strong>RHEL · Rocky Linux · AlmaLinux · CentOS Stream</strong></summary>

Install the base tools:

```bash
sudo dnf install git curl
```

Enable the repositories appropriate to your distribution and release using the
[EPEL setup guide](https://docs.fedoraproject.org/en-US/epel/getting-started/).
On releases providing these packages:

```bash
sudo dnf install ffmpeg-free aria2
```

Package availability differs between enterprise releases. If FFmpeg is unavailable, use
one of the [FFmpeg project-linked builds or repositories](https://www.ffmpeg.org/download.html).

</details>

<details>
<summary><strong>Arch Linux · EndeavourOS · Manjaro</strong></summary>

```bash
sudo pacman -Syu git curl ffmpeg aria2
```

This refreshes and upgrades the system before installing packages, following Arch's rolling
release model. [FFmpeg is available in Extra](https://archlinux.org/packages/extra/x86_64/ffmpeg/).

</details>

<details>
<summary><strong>openSUSE Tumbleweed · Leap</strong></summary>

```bash
sudo zypper refresh
sudo zypper install git curl aria2
zypper search -s ffmpeg
```

Install the FFmpeg package offered for your release; openSUSE uses versioned package names.
Follow the distribution's [multimedia setup guidance](https://en.opensuse.org/SDB:Installing_codecs_from_Packman_repositories)
if additional codec support is needed. Check that `ffmpeg` and `ffprobe` are available afterward.

</details>

<details>
<summary><strong>Alpine Linux</strong></summary>

Run as root, or use your configured privilege tool:

```sh
apk add git curl ffmpeg aria2
```

Enable the Community repository for your installed Alpine release if needed;
[Alpine's package index](https://pkgs.alpinelinux.org/packages?name=ffmpeg) lists availability.

</details>

<details>
<summary><strong>Gentoo · Void Linux</strong></summary>

Gentoo:

```bash
sudo emerge --ask dev-vcs/git net-misc/curl media-video/ffmpeg net-misc/aria2
```

For non-MP3 input converted to MP3, enable FFmpeg's MP3 encoder support.
See [Gentoo's FFmpeg guide](https://wiki.gentoo.org/wiki/FFmpeg).

Void Linux:

```bash
sudo xbps-install -S git curl ffmpeg aria2
```

See the [Void package-manager handbook](https://docs.voidlinux.org/xbps/index.html)
for repository setup.

</details>

After installing the system tools, install uv with its
[official Linux installer](https://docs.astral.sh/uv/getting-started/installation/):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal, then continue below. The installer handles supported Linux architectures;
see [uv platform support](https://docs.astral.sh/uv/reference/policies/platforms/) for compatibility.
For NixOS, BSD, or a platform without a suitable managed Python, use the alternatives below.

### Install Frogify

Run these commands on Windows, macOS, or Linux after completing the platform setup:

```shell
git clone https://github.com/wittg3n/frogify-cli.git
cd frogify-cli
uv python install 3.13
uv tool install --python 3.13 .
uv tool update-shell
```

If you downloaded the source ZIP instead, open a terminal in the extracted directory containing
`pyproject.toml` and start with `uv python install 3.13`.

Open a new terminal and verify the installation:

```shell
frogify --version
frogify --help
ffmpeg -version
ffprobe -version
aria2c --version
frogify doctor
```

You can now run `frogify` from any directory. The
[uv tool guide](https://docs.astral.sh/uv/guides/tools/) explains how the command is installed
and added to `PATH`. `doctor` checks local tools and provider reachability; it does not
perform a conversion or prove that a download will succeed.

### Other platforms and installation methods

<details>
<summary><strong>Existing Python · standard virtual environment · BSD</strong></summary>

Use a Python 3.12+ interpreter supplied by your OS or [Python.org](https://www.python.org/downloads/).
For example, on FreeBSD, install the tools as root:

```sh
pkg install git python313 ffmpeg aria2
```

Clone this repository, then create an isolated environment. Replace `python3.13` with the
name of your installed Python 3.12+ interpreter:

```sh
git clone https://github.com/wittg3n/frogify-cli.git
cd frogify-cli
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
frogify --help
```

On Windows, create and activate the environment with:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
frogify --help
```

Activate this environment in each new terminal, or run its `frogify` executable by full path.
If your OS splits out Python's `venv` or `pip` support, install those packages first.
Platforms without prebuilt dependency wheels may also require a compiler and Python headers.

This is a portable installation route, not a claim that every OS and architecture has been tested.

</details>

<details>
<summary><strong>NixOS / Nix: run from a packaged Python environment</strong></summary>

Use Nix-provided Python dependencies so native libraries come from Nixpkgs. In a checkout of
this repository, enter a shell:

```sh
nix-shell -p git ffmpeg aria2 \
  'python313.withPackages (p: with p; [ click mutagen platformdirs rapidfuzz requests rich typer ])'
```

Inside that shell, run Frogify from the repository directory:

```sh
python -m frogify --help
python -m frogify "Artist Track"
```

This recipe uses [Nixpkgs Python environments](https://nixos.org/manual/nixpkgs/stable/#python).
It is a source-run environment, not a global installation or a maintained Nix package.
Use a Nixpkgs revision providing Python 3.12+ and the listed dependencies.

</details>

## Usage

### Download a track

```shell
frogify "Adele Hello"
frogify "Adele Hello" --pick
frogify "Adele Hello" --source youtube
frogify "Adele Hello" --candidate-attempts 5
frogify "Adele Hello" --output "./my-music"
```

Automatic selection tries up to three safe candidates by default. If no result passes the
confidence and version checks, Frogify stops and records the failure. `--pick` displays the
ranked results and downloads the exact item you select, even if automatic matching would reject it.

### Search without downloading

```shell
frogify search "Massive Attack Teardrop"
frogify search "Massive Attack Teardrop" --limit 20 --source youtube
```

Available sources are `all`, `youtube`, and `soundcloud`. Search lists candidates without
resolving or downloading audio.

### Download a Spotify-export CSV

```shell
frogify batch "path/to/playlist.csv"
frogify batch "path/to/playlist.csv" --max-tracks 10
frogify batch "path/to/playlist.csv" --output "./my-music"
frogify batch "path/to/playlist.csv" --force
```

Frogify uses the CSV as track metadata for matching; it does not download audio from Spotify.
The file must be UTF-8, with these exact column names:

| Required column | Expected value |
| --- | --- |
| `Track URI` | A nonempty track identity, normally a Spotify track URI. |
| `Track Name` | Track title, including a requested version such as Live or Remix. |
| `Artist Name(s)` | Artist names; separate multiple artists with semicolons. |
| `Duration (ms)` | A positive, finite duration in milliseconds. |

Optional columns include `Album Name`, `Release Date`, `Genres`, `Record Label`,
`Popularity`, and `Explicit`. Album, release date, genre, and label fields contribute to
metadata; not every imported field is written as an audio tag.

Repeated track URIs are processed once per batch. Successful tracks are committed after each
download. Running the batch again skips existing recorded files; moved or deleted files are
downloaded again. `--force` reprocesses successful tracks, preserving the original until a
replacement is ready.

### Retry failures

```shell
frogify retry
frogify retry --output "./retry-music"
```

Retries retain the saved destination and free-text selection options unless you override the
destination. Older imported failures without enough metadata are explained and removed from the
retry queue; import the original CSV to reconstruct those tracks.

## Download location

The default is a lowercase `music` subfolder inside your system Downloads directory:

| Platform | Typical default |
| --- | --- |
| Windows | `C:\Users\<user>\Downloads\music` |
| macOS | `/Users/<user>/Downloads/music` |
| Linux | `/home/<user>/Downloads/music` |

System folder redirection and Linux XDG download-directory settings are respected.
An existing `Music` folder may retain its capitalization on a case-insensitive filesystem.
Frogify creates the destination when saving audio.

**Destination precedence:** `--output` → `download.directory` → system `Downloads/music`.

Batch resume checks the recorded file's location. Changing the destination does not copy or
move previously completed tracks. Saved retries also retain their original destination.

## Configuration

Inspect the current settings or find the configuration file:

```shell
frogify config
frogify config path
frogify config get network.retry_profile
```

Change settings without editing TOML manually:

```shell
frogify config set network.retry_profile fast
frogify config set download.aria2_connections 10
frogify config set matching.candidate_attempts 5
frogify config set download.directory "~/Downloads/music"
frogify config set metadata.enabled false
```

| Setting | Default | Values / meaning |
| --- | --- | --- |
| `download.engine` | `auto` | `auto`, `aria2`, or `requests`. |
| `download.aria2_connections` | `8` | An integer from 1 to 16. |
| `download.directory` | `""` | Empty uses the system Downloads/music folder. |
| `matching.duration_tolerance` | `10.0` | Maximum structured duration difference, in seconds. |
| `matching.candidate_attempts` | `3` | Maximum accepted candidates to try per track. |
| `network.retry_profile` | `balanced` | `fast`, `balanced`, or `patient`. |
| `network.timeout` | `30.0` | Positive request timeout, in seconds. |
| `metadata.enabled` | `true` | Whether batches write Spotify metadata and produce MP3 files. |

To restore automatic download-folder selection, set `directory = ""` in the `[download]`
section of the file shown by `frogify config path`.

With metadata disabled, batches preserve the source audio format and extension. With metadata
enabled, MP3 audio is copied while tags are written; other formats are converted using FFmpeg's
`libmp3lame` encoder.

### State and retry behavior

Configuration, SQLite state, rotating logs, and temporary files use OS-specific user directories.
Run `frogify doctor` to see the configuration and database paths. Logs are under `logs/` beside
`frogify.db`.

SQLite is the live source of resume state. Legacy `downloaded_tracks.csv` and `failed_tracks.csv`
files are imported once from the current directory, its `spotify` subdirectory, and the batch
output directory. They are left untouched; Frogify does not generate new CSV reports.

The `fast` profile uses shorter waits, `balanced` is the default, and `patient` allows more
time for rate-limited providers. Requests, conversion polling, candidate attempts, aria2 transfers,
and audio subprocesses have separate bounds. There is no single overall track deadline, so a
track can still take several minutes. Audio is currently buffered in memory during transfer.

## Updating and uninstalling

For the recommended installation, update from your local checkout:

```shell
git pull --ff-only
uv tool install --reinstall --python 3.13 .
frogify --version
```

If you use a source ZIP, extract the newer source and run the same `uv tool install` command
from that directory. Virtual-environment users can run `python -m pip install --upgrade .`
inside their activated environment.

To remove the uv-installed command:

```shell
uv tool uninstall frogify
```

Uninstalling the command leaves your downloaded audio, configuration, and download history in place.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `frogify` is not found | Run `uv tool update-shell`, then open a new terminal. For a venv install, activate that environment. |
| `uv` is not found | Reopen the terminal after installing uv; follow the installer's PATH instructions. |
| FFmpeg or ffprobe is missing | Install the system package above and check `ffmpeg -version` / `ffprobe -version` in the same terminal. |
| aria2 is missing or fails | Use `frogify config set download.engine requests`, or leave the engine on `auto` for fallback. |
| `Unknown encoder 'libmp3lame'` | Install an FFmpeg build with MP3 encoding, or disable metadata to preserve the source format. |
| No safe match is found | Refine the artist/title, inspect `frogify search`, or choose a result using `--pick`. |
| A provider times out or rate-limits requests | Check `frogify doctor`, retry later, and consider the `patient` profile. |
| A CSV row is rejected | Check the exact headers, nonempty required fields, and duration in milliseconds. |
| The destination is unexpected | Check `download.directory`, command overrides, and the destination saved in retry state. |
| A dependency cannot be built | Use supported Python and OS versions; uncommon architectures may need native build tools. |

For a traceback and debug logging:

```shell
frogify --debug search "Artist Track"
```

Provider availability can change independently of Frogify. A successful reachability check is
not a guarantee that a specific recording can be resolved.

## Development

Clone the repository and install the locked development environment:

```shell
uv sync --locked --python 3.13
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
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
A passing local test suite does not certify live provider availability or every operating system.
Release builds include source, tests, documentation, and the logo; personal exports, downloads,
local state, and generated artifacts are excluded.

Contributions are welcome. Include a clear reproduction for bug reports and explain how changes
were verified. See the [changelog](CHANGELOG.md) for project changes.

## License and responsible use

Frogify is released under the [MIT License](LICENSE).

Use it only for audio you are permitted to access and in accordance with the relevant service
terms. Frogify is an independent project and is not affiliated with Spotify, YouTube, SoundCloud,
MP3Juice, or Theta.

