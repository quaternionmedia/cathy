import shutil
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "site"


@pytest.fixture
def site_dir(tmp_path: Path) -> Path:
    """A writable copy of the made-up site, so a conversion never writes into the fixture."""
    target = tmp_path / "site"
    shutil.copytree(FIXTURE, target)
    return target
