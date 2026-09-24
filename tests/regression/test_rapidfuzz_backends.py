"""The supported Python backend must preserve the scores Frogify consumes."""

import itertools
import math

import pytest
from rapidfuzz import fuzz_cpp, fuzz_py

TITLES = (
    "Adele Hello",
    "Lionel Richie - Hello",
    "Adele - Hello (Official Video)",
    "Adele Hello live remix",
    "Beyoncé Halo",
    "Beyonce Halo acoustic",
    "Daft Punk Get Lucky feat Pharrell Williams",
    "Get Lucky Daft Punk radio edit",
    "東京 夜 音楽",
    "سلام موسیقی",
    "",
    "a a a b",
    "b a",
)
FUNCTIONS = ("ratio", "partial_ratio", "token_set_ratio", "token_sort_ratio", "WRatio")


@pytest.mark.parametrize("name", FUNCTIONS)
def test_matching_score_parity(name):
    native, python = getattr(fuzz_cpp, name), getattr(fuzz_py, name)
    for left, right in itertools.product(TITLES, repeat=2):
        a, b = native(left, right), python(left, right)
        assert math.isclose(a, b, rel_tol=0, abs_tol=1e-10), (name, left, right, a, b)
        for threshold in (55, 70, 80, 85, 90, 95):
            assert (a >= threshold) == (b >= threshold), (name, left, right, threshold)
