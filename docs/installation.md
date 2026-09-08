# Installation

[Back to Frogify](../README.md)

## Quick install from GitHub

With Python 3.12+, [pipx](https://pipx.pypa.io/latest/how-to/install-pipx.html), and Git installed:

```shell
pipx install "git+https://github.com/wittg3n/frogify-cli.git"
pipx ensurepath
```

Or use uv and Git; uv can install Python for you:

```shell
uv tool install --python 3.13 "git+https://github.com/wittg3n/frogify-cli.git"
uv tool update-shell
```

Open a new terminal, then run `frogify --help`. These are source installs while the first
PyPI release is being prepared. FFmpeg is a separate system dependency for CSV metadata;
aria2 is optional. Follow the platform setup below if you need those tools or a source ZIP.

## Platform setup

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

**Choose your platform below, then follow [Install Frogify](#install-frogify-from-a-checkout).**

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
Then continue to [Install Frogify](#install-frogify-from-a-checkout).

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
Continue to [Install Frogify](#install-frogify-from-a-checkout).

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

### Install Frogify from a checkout

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

## Updating and uninstalling

For the GitHub installs above, use the command matching your installer:

```shell
pipx upgrade frogify
```

```shell
uv tool upgrade frogify
```

For a local checkout, update and reinstall:

```shell
git pull --ff-only
uv tool install --reinstall --python 3.13 .
frogify --version
```

If you use a source ZIP, extract the newer source and run the same `uv tool install` command
from that directory. Virtual-environment users can run `python -m pip install --upgrade .`
inside their activated environment.

To remove the command, use the matching installer:

```shell
pipx uninstall frogify
```

```shell
uv tool uninstall frogify
```

Uninstalling the command leaves your downloaded audio, configuration, and download history in place.
