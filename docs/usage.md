# Usage and configuration

[Back to Frogify](../README.md)

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

Search and `--pick` show each candidate's match score out of 100. Single-track downloads also
print the selected title and score after saving. The score is a ranking heuristic, not a
calibrated confidence percentage.

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

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `frogify` is not found | Run `pipx ensurepath` or `uv tool update-shell` for your installer, then open a new terminal. For a venv install, activate that environment. |
| `uv` is not found | Reopen the terminal after installing uv; follow the installer's PATH instructions. |
| FFmpeg or ffprobe is missing | Follow the [installation guide](installation.md) and check `ffmpeg -version` / `ffprobe -version` in the same terminal. |
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
