import pytest

from mp3juice.utils import (
    available_audio_path,
    bytes_to_mb,
    legalize_filename,
    publish_audio,
    seconds_to_hms,
)


def test_legalize_filename():
    assert legalize_filename("A:B/C*D?") == "A_B_C_D_"


def test_seconds_to_hms():
    assert seconds_to_hms(65) == "1:05"
    assert seconds_to_hms(3661) == "1:01:01"
    assert seconds_to_hms(None) == "-:-:-"


def test_bytes_to_mb():
    assert bytes_to_mb(1024 * 1024) == "1.00 MB"


@pytest.mark.parametrize("stem", ["CON", "aux.mp3", "NUL", "COM1", "lpt9"])
def test_windows_reserved_filenames(stem):
    assert legalize_filename(stem).startswith("_")


def test_long_unicode_collisions_and_atomic_publication(tmp_path):
    stem = "آواز" * 100
    destination = available_audio_path(tmp_path, stem, "ogg")
    assert len(destination.name.encode("utf-8")) <= 200
    # Simulate another download publishing after the filename was chosen.
    destination.write_bytes(b"original")
    staged = tmp_path / "stage"
    staged.write_bytes(b"new")
    saved = publish_audio(staged, destination)
    assert destination.read_bytes() == b"original"
    assert saved != destination
    assert saved.suffix == ".ogg"
    assert saved.read_bytes() == b"new"
    assert not staged.exists()


def test_publish_rejects_unknown_extensions(tmp_path):
    with pytest.raises(ValueError, match="extension"):
        available_audio_path(tmp_path, "song", "exe")
