# Changelog

## Unreleased

- Clarify Spotify/YouTube Music downloader positioning, explain CSV-based Spotify support,
  and tighten the README's product-first layout and installation hierarchy.
- Prepare the first public release with a shorter README, terminal demo, installation and usage
  guides, contribution templates, and complete package discovery metadata.
- Add Python 3.12/3.13 CI on Ubuntu, Windows, and macOS, distribution smoke checks, and a
  release-triggered PyPI Trusted Publishing workflow.
- Label search scores out of 100 and show the selected title and score after a download.
- Default downloads to the current user's system Downloads/music folder on Windows, macOS,
  Linux, and other supported platforms, while retaining explicit directory overrides.
- Preserve existing audio on failed forced replacement; publish completed files without
  overwriting concurrent downloads and handle Windows reserved names and long filenames.
- Make SQLite the sole live resume state, commit each completed track, and redownload missing
  files. Keep one-time legacy CSV imports while retiring duplicate CSV report writes.
- Reject unsafe automatic free-text matches and download the exact displayed `--pick` result.
- Persist early search failures, retry destinations and selection options, and redacted batch
  diagnostics. Explain unreconstructable legacy failures instead of silently ignoring them.
- Validate configuration types and finite durations; save TOML atomically with escaped strings.
- Preserve source extensions when metadata is disabled and defer FFmpeg checks until needed.
- Add progress reporting, independent doctor checks, subprocess timeouts, scoped aria2 cookies,
  and cancellation of abandoned aria2 transfers. Close SQLite connections after each operation.
- Remove the duplicate legacy CLI, unused provider wrappers, duplicate requirements files,
  unused settings/state writes, and an unreferenced image. Preserve existing user data.
- Restrict source packaging to application files, tests, and release metadata. Expand lint and
  type checks to both packages and add service, file-safety, configuration, and transfer tests.

## 2.0.0

- Renamed the product and global command to Frogify.
- Added root-query, search, batch, retry, config, and doctor commands.
- Added platform-specific TOML configuration and canonical SQLite state.
- Added idempotent import of legacy success and failure CSV files.
- Preserved the proven MP3Juice, Theta/ThetaCloud, aria2, requests, matching,
  validation, metadata, and bounded retry behavior behind typed boundaries.
