from mp3juice.utils import parse_duration_seconds, seconds_to_hms


def test_duration_string():
    seconds = parse_duration_seconds({"duration": "6:07"})
    assert seconds == 367
    assert seconds_to_hms(seconds) == "6:07"


def test_duration_seconds():
    assert parse_duration_seconds({"duration_seconds": 367}) == 367


def test_duration_milliseconds():
    assert parse_duration_seconds({"duration_ms": 367000}) == 367
