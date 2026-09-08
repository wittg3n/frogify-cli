# Launch copy

Drafts for use after the release is published and the installation commands are verified.
Recheck each community's current submission rules before posting.

## GitHub About

Suggested description:

> 🐸 Spotify & YouTube Music downloader CLI with smart matching, metadata tagging and resumable batch downloads.

Suggested topics:

```text
spotify-downloader youtube-music-downloader music-downloader spotify youtube-music
spotify-playlist-downloader playlist-downloader audio-downloader youtube cli
python terminal soundcloud ffmpeg aria2 metadata command-line cross-platform typer rich
```

These 20 topics describe the product category and its implementation. Spotify support imports
exported CSV metadata; audio is not downloaded from Spotify. YouTube Music discovery uses
YouTube search results, without an official YouTube Music API integration.

To apply this About text and these topics, install [GitHub CLI](https://cli.github.com/) if needed,
sign in, and run the following in PowerShell. The command adds the topics without removing
existing ones; the current six repository topics are all included in this set.

```powershell
gh auth login
gh repo edit wittg3n/frogify-cli --description '🐸 Spotify & YouTube Music downloader CLI with smart matching, metadata tagging and resumable batch downloads.' --add-topic 'spotify-downloader,youtube-music-downloader,music-downloader,spotify,youtube-music,spotify-playlist-downloader,playlist-downloader,audio-downloader,youtube,cli,python,terminal,soundcloud,ffmpeg,aria2,metadata,command-line,cross-platform,typer,rich'
```

See the [GitHub CLI command reference](https://cli.github.com/manual/gh_repo_edit).

## Demo status

The existing `public/demo.gif` is 800 × 325 pixels, 13.1 seconds, and loops continuously.
It shows one download command and its saved result. The existing recording was preserved;
no simulated output or audio was introduced in this correction pass.

Its last frame contains `/root/Downloads/music`, and it predates the selected-score summary.
There is no `.tape`, Dockerfile, or other recording source in this checkout. A future recording
can tidy the path and capture the current CLI, but should preserve real output or clearly label
an isolated deterministic fixture. Keep recordings free of personal paths and credentials.

## Ship the reviewed changes

From the repository in PowerShell, review and commit the existing launch work together with
this correction pass. The explicit paths include the demo and exclude personal data and builds:

```powershell
git diff --check
git diff
git switch -c codex/launch-positioning
git add README.md pyproject.toml frogify/cli/app.py tests/integration/test_frogify_cli.py CHANGELOG.md CONTRIBUTING.md docs .github public/demo.gif
git diff --cached --stat
git commit -m "Prepare Frogify launch and Spotify/YouTube Music positioning"
git push -u origin codex/launch-positioning
```

Open a pull request, wait for the six test combinations and package checks, then merge through
your normal review process. The new documentation and GIF links become available on `main`
after merging. Follow [Publishing Frogify](releasing.md) for PyPI setup and the release draft.

## r/commandline draft

**Title:** I built Frogify — a Spotify & YouTube Music downloader CLI with careful track matching 🐸

Frogify turns Spotify-exported playlists into local audio and downloads tracks found on YouTube
and SoundCloud. It ranks search candidates, checks recording versions, and rejects unsafe matches.
You can inspect the source, duration, and match score yourself before choosing a result.

It also processes Spotify-export CSVs with artist and duration matching, writes metadata,
and resumes interrupted batches from SQLite.

```shell
frogify "Massive Attack - Teardrop"
frogify search "Daft Punk - Something About Us"
frogify batch "spotify.csv"
```

It supports YouTube and SoundCloud discovery through MP3Juice, optional aria2 acceleration,
persistent retries, and Windows/macOS/Linux. It does not download audio from Spotify.

I'd appreciate feedback on matching accuracy and the CLI experience.

[Code, demo, and installation](https://github.com/wittg3n/frogify-cli)

## Python showcase draft

**What my project does:** Frogify is a Spotify and YouTube Music downloader CLI with CSV imports,
ranked candidate selection,
recording-version checks, metadata tagging for Spotify-export CSVs, and resumable batches.

**Target audience:** People managing permitted audio collections who want to inspect matches
and resume batch jobs from a CLI.

**How it works:** Python 3.12+, Typer/Rich output, RapidFuzz scoring, SQLite state, Mutagen/ffprobe
audio checks, FFmpeg metadata, and aria2 or Requests transfers. CSV matching combines title,
artist, duration, and version signals; source discovery and resolution use MP3Juice providers.

**Comparison:** The focus is careful matching and inspectable scores, with explicit manual
selection when needed. Scores are heuristics, and provider behavior can change independently.

**Installation:** See the verified commands in the
[README](https://github.com/wittg3n/frogify-cli#quick-start).

## Later channels

Suggested Show HN title: **Show HN: Frogify – a Spotify and YouTube Music downloader CLI**

For Dev.to or X, lead with the terminal demo and explain one real matching example, including a
version Frogify rejected. Link the release and verified install command. Publish the longer
technical post only when you have actual results and feedback to discuss.
