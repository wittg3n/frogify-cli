import json
import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "inventory",
    [{}, {"release_ready": False}, {"release_ready": True, "blockers": ["missing source"]}],
)
def test_unresolved_distribution_cannot_be_published(tmp_path, inventory):
    check = runpy.run_path(str(Path(__file__).parents[2] / "packaging/notices.py"))["check_release"]
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(SystemExit, match="publication blocked"):
        check(path)
