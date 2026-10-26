import shutil
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "site"


@pytest.fixture(autouse=True)
def _site(doctest_namespace, tmp_path):
    """Each page reads a fresh copy of the made-up site as `site_dir`."""
    target = tmp_path / "site"
    shutil.copytree(FIXTURE, target)
    doctest_namespace["site_dir"] = target
