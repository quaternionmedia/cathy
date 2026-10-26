"""Download the images a conversion listed into the site's assets directory.

An image already on disk is complete: a download is written beside its target
and renamed into place only once the whole body has arrived.
"""

from __future__ import annotations

import os
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from cathy import net


@dataclass
class Fetched:
    saved: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def read_manifest(path: Path) -> list[tuple[str, str]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        url, tab, name = line.partition("\t")
        if not tab or not url or not name:
            raise ValueError(f"{path}:{number}: expected <url><TAB><file name>")
        rows.append((url, name))
    return rows


def _plain(name: str) -> bool:
    return name not in ("", ".", "..") and "/" not in name and "\\" not in name and ":" not in name


def fetch(
    rows: list[tuple[str, str]],
    assets: Path,
    *,
    hosts: Collection[str],
    schemes: Collection[str] = ("https",),
    timeout: float = net.TIMEOUT,
) -> Fetched:
    result = Fetched()
    assets.mkdir(parents=True, exist_ok=True)
    for url, name in rows:
        if not _plain(name):
            result.failed.append((url, f"{name!r} is not a plain file name"))
            continue
        target = assets / name
        if target.exists():
            result.present.append(name)
            continue
        partial = target.with_name(target.name + ".part")
        try:
            body = net.get(url, hosts=hosts, schemes=schemes, timeout=timeout)
            partial.write_bytes(body)
            os.replace(partial, target)
        except (net.Failed, OSError) as error:
            partial.unlink(missing_ok=True)
            result.failed.append((url, str(error) or type(error).__name__))
            continue
        result.saved.append(name)
    return result
