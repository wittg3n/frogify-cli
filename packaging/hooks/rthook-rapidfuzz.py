"""Use RapidFuzz's supported Python implementation in the standalone build."""

import os

os.environ["RAPIDFUZZ_IMPLEMENTATION"] = "python"
