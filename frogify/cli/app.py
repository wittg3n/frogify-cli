from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from typer.core import TyperGroup

from frogify import __version__
from frogify.config import ConfigManager
from frogify.core.exceptions import FrogifyError
from frogify.core.models import FreeTextRequest, RankedCandidate
from frogify.core.service import FrogifyService
from frogify.diagnostics import run_doctor
from frogify.logging import configure_logging
from frogify.storage import Database
from mp3juice.spotify_batch import BatchCallbacks, SpotifyTrack

console = Console()
KNOWN_COMMANDS = {"search", "batch", "retry", "config", "doctor", "_download"}
DEBUG = False


class RootQueryGroup(TyperGroup):
    """Route an unknown first positional token to the hidden download command."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        for index, value in enumerate(args):
            if value.startswith("-"):
                continue
            if value not in KNOWN_COMMANDS:
                args.insert(index, "_download")
            break
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=RootQueryGroup,
    name="frogify",
    help="Professional MP3Juice/Theta music downloader.",
    no_args_is_help=True,
    add_completion=False,
)
config_app = typer.Typer(
    name="config",
    help="Inspect or update Frogify configuration.",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(config_app, name="config")


def _version(value: bool) -> None:
    if value:
        console.print(f"frogify {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    debug: bool = typer.Option(False, "--debug", help="Show tracebacks and debug logging."),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version,
        is_eager=True,
        help="Show the Frogify version.",
    ),
) -> None:
    """Download with `frogify "artist track"` or use a named command."""
    del version
    global DEBUG
    DEBUG = debug


def _service() -> FrogifyService:
    config = ConfigManager()
    return FrogifyService(config, logger=configure_logging(config, debug=DEBUG))


def _safe_text(value: object) -> str:
    encoding = console.encoding or "utf-8"
    return str(value).encode(encoding, errors="replace").decode(encoding)


@contextmanager
def _progress() -> Iterator[BatchCallbacks]:
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        disable=not console.is_terminal,
    ) as progress:
        task = progress.add_task("Preparing", total=None)

        def status(text: str) -> None:
            progress.update(task, description=escape(_safe_text(text)))
            if not console.is_terminal:
                console.print(_safe_text(text), markup=False)

        def start(index: int, total: int, track: SpotifyTrack) -> None:
            progress.reset(task, total=None)
            console.print(f"[{index}/{total}] {_safe_text(track.track_name)}", markup=False)

        def update(done: int, total: int | None) -> None:
            progress.update(task, completed=done, total=total)

        yield BatchCallbacks(
            on_track_start=start,
            on_status=status,
            on_download_progress=update,
            on_track_success=lambda track, path, candidate: status(f"Saved {path.name}"),
            on_track_failure=lambda track, reason: status(f"Failed {track.track_name}: {reason}"),
        )


def _abort(exc: Exception) -> None:
    if DEBUG:
        console.print_exception()
    else:
        console.print(f"[red bold]Error:[/] {escape(_safe_text(exc))}")
    raise typer.Exit(1)


def _print_candidates(query: str, ranked: list[RankedCandidate]) -> None:
    mascot = "🐸 " if "utf" in console.encoding.casefold() else ""
    console.print(f"[bold green]{mascot}Frogify[/]")
    console.print(f"Search: [bold]{escape(_safe_text(query))}[/]\n")
    table = Table()
    table.add_column("#", justify="right")
    table.add_column("Result")
    table.add_column("Source")
    table.add_column("Duration", justify="right")
    table.add_column("Score", justify="right")
    for index, candidate in enumerate(ranked, 1):
        result = candidate.result
        table.add_row(
            str(index),
            escape(_safe_text(result.title)),
            _safe_text(result.source_label),
            result.duration,
            f"{candidate.score:.1f}",
        )
    console.print(table)


@app.command("_download", hidden=True)
def download_query(
    query: str = typer.Argument(..., help="Artist and track search query."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Destination directory."),
    candidate_attempts: int | None = typer.Option(None, min=1, help="Safe candidates to try."),
    pick: bool = typer.Option(False, help="Select a ranked result interactively."),
    source: str = typer.Option("all", help="all, youtube, or soundcloud."),
) -> None:
    try:
        service = _service()
        selected: RankedCandidate | None = None
        if pick:
            ranked = service.search(FreeTextRequest(query), source=source)
            _print_candidates(query, ranked)
            if not ranked:
                raise ValueError("No results are available to select")
            pick_index = typer.prompt("Choose result", type=int)
            if not 1 <= pick_index <= len(ranked):
                raise ValueError(f"Choose a result between 1 and {len(ranked)}")
            selected = ranked[pick_index - 1]
        mascot = "🐸 " if "utf" in console.encoding.casefold() else ""
        console.print(f"[bold green]{mascot}Frogify[/]")
        with _progress() as callbacks:
            result = service.download(
                FreeTextRequest(query),
                output=output,
                candidate_attempts=candidate_attempts,
                selected=selected,
                source=source,
                progress_callback=callbacks.on_download_progress,
                status_callback=callbacks.on_status,
            )
        saved = "✓ Saved" if "utf" in console.encoding.casefold() else "Saved"
        console.print(f"\n[green]{saved}[/]\n{_safe_text(result.path)}")
    except (FrogifyError, ValueError, OSError, sqlite3.Error) as exc:
        _abort(exc)


@app.command()
def search(
    query: str = typer.Argument(..., help="Artist and track search query."),
    limit: int = typer.Option(10, min=1, max=50),
    source: str = typer.Option("all", help="all, youtube, or soundcloud."),
) -> None:
    """Show ranked candidates without resolving or downloading them."""
    try:
        _print_candidates(
            query, _service().search(FreeTextRequest(query), limit=limit, source=source)
        )
    except (FrogifyError, ValueError, OSError, sqlite3.Error) as exc:
        _abort(exc)


@app.command()
def batch(
    csv_file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
    force: bool = typer.Option(False, help="Reprocess successful tracks."),
    max_tracks: int | None = typer.Option(None, min=1),
) -> None:
    """Download a Spotify export CSV, resuming from SQLite state."""
    try:
        with _progress() as callbacks:
            result = _service().batch(
                csv_file, output=output, force=force, max_tracks=max_tracks, callbacks=callbacks
            )
        console.print(
            f"Downloaded [green]{result.downloaded}[/] · "
            f"Skipped {result.skipped} · Failed [red]{result.failed}[/]"
        )
        if result.failed:
            raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("[yellow]Batch interrupted.\nProgress has been saved.[/]")
        raise typer.Exit(130) from None
    except typer.Exit:
        raise
    except (FrogifyError, ValueError, OSError, sqlite3.Error) as exc:
        _abort(exc)


@app.command()
def retry(
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Retry persisted retryable failures."""
    try:
        with _progress() as callbacks:
            result = _service().retry(output=output, callbacks=callbacks)
        console.print(
            f"Retried {result.total} · Saved {result.downloaded} · Failed {result.failed}"
        )
        if result.failed:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except (FrogifyError, ValueError, OSError, sqlite3.Error) as exc:
        _abort(exc)


@app.command()
def doctor() -> None:
    """Check configuration, state, tools, imports, and provider reachability."""
    try:
        config = ConfigManager()
        checks = run_doctor(config, Database(config.database_path))
        table = Table(title="Frogify doctor")
        table.add_column("Component")
        table.add_column("Status")
        table.add_column("Details")
        failed = False
        for check in checks:
            if not check.ok and check.required:
                failed = True
            status = (
                "[green]OK[/]"
                if check.ok
                else "[yellow]OPTIONAL/MISSING[/]"
                if not check.required
                else "[red]FAILED[/]"
            )
            table.add_row(check.name, status, check.detail)
        console.print(table)
        if failed:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except (FrogifyError, ValueError, OSError, sqlite3.Error) as exc:
        _abort(exc)


@config_app.callback()
def config_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    manager = ConfigManager()
    try:
        values = manager.load()
        table = Table(title=f"Frogify config · {manager.path}")
        table.add_column("Key")
        table.add_column("Value")
        for section, options in values.items():
            for key, value in options.items():
                table.add_row(f"{section}.{key}", str(value))
        console.print(table)
    except (FrogifyError, OSError) as exc:
        _abort(exc)


@config_app.command("path")
def config_path() -> None:
    console.print(_safe_text(ConfigManager().path))


@config_app.command("get")
def config_get(key: str) -> None:
    try:
        console.print(_safe_text(ConfigManager().get(key)))
    except (FrogifyError, OSError) as exc:
        _abort(exc)


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    try:
        saved: Any = ConfigManager().set(key, value)
        console.print(f"{key} = {saved}")
    except (FrogifyError, OSError) as exc:
        _abort(exc)


def main() -> None:
    app(prog_name="frogify")


if __name__ == "__main__":
    main()
