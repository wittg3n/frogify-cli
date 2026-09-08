from __future__ import annotations

import pytest

from mp3juice.exceptions import DownloadError, ResolveError
from mp3juice.models import SearchResult
from mp3juice.spotify_batch import (
    BatchCallbacks,
    SpotifyTrack,
    SpotifyTrackDownloader,
)


class FailingClient:
    def search(self, keyword, *, limit=10, source="all"):
        return [
            SearchResult(
                identifier="yt123",
                title="Artist - Exact Song",
                root_source="YouTube",
                duration_s=180.0,
                duration="3:00",
                raw_data={"artist": "Artist"},
            )
        ]

    def download(self, result, *, progress_callback=None):
        raise ResolveError(
            "Theta convert did not provide redirectURL after 5 attempt(s).",
            details={
                "stage": "convert",
                "video_id": result.identifier,
                "attempt_count": 5,
                "convert_responses": [
                    {
                        "attempt": 1,
                        "response": {
                            "status": "processing",
                            "progress": 25,
                        },
                    }
                ],
            },
        )


def test_batch_writes_download_diagnostics(tmp_path, monkeypatch):
    # Constructor only needs ffmpeg presence; avoid depending on host PATH.
    monkeypatch.setattr(
        "mp3juice.spotify_batch._ffmpeg_binary",
        lambda: "ffmpeg",
    )

    track = SpotifyTrack(
        row_number=2,
        uri="spotify:track:test",
        track_name="Exact Song",
        album_name="Album",
        artists_display="Artist",
        artists=["Artist"],
        release_date="2026",
        duration_s=180.0,
        popularity="",
        explicit="",
        genres="",
        record_label="",
    )

    runner = SpotifyTrackDownloader(
        FailingClient(),
        output_dir=tmp_path / "spotify",
        duration_tolerance_s=10.0,
        callbacks=BatchCallbacks(),
    )

    with pytest.raises(DownloadError) as caught:
        runner.download_track(track)
    diagnostics = caught.value.details["download_diagnostics"]
    assert diagnostics[0]["candidate_id"] == "yt123"
    assert diagnostics[0]["details"]["stage"] == "convert"
    assert diagnostics[0]["details"]["convert_responses"][0]["response"]["progress"] == 25
