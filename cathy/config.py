"""A site's `cathy.toml`: where its export is, what to keep, and where pages and images go.

Every path in the file is relative to the file itself.
"""

from __future__ import annotations

import posixpath
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FORMATS = ("squarespace-wxr",)


class ConfigError(ValueError):
    """A `cathy.toml` cathy cannot act on."""


@dataclass(frozen=True)
class Site:
    export: Path
    docs: Path
    assets: Path
    manifest: Path
    image_hosts: tuple[str, ...]
    include_drafts: bool = False
    posts_prefix: str = ""
    posts_dir: str = ""
    slugs: dict[str, str] = field(default_factory=dict)
    tags: dict[str, tuple[str, ...]] = field(default_factory=dict)
    pages: dict[str, str] = field(default_factory=dict)


def _relative(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where} must be a non-empty string")
    normal = posixpath.normpath(value.replace("\\", "/"))
    if normal.startswith(("/", "..")) or ":" in normal:
        raise ConfigError(f"{where} must be a relative path inside the site, not {value!r}")
    return normal


def load(path: Path) -> Site:
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    source = data.get("source", {})
    output = data.get("output", {})
    images = data.get("images", {})
    posts = data.get("posts", {})

    if source.get("format") not in FORMATS:
        raise ConfigError(f"[source] format must be one of {list(FORMATS)}")
    docs = root / _relative(output.get("docs", "docs"), "[output] docs")
    assets = root / _relative(output.get("assets", "docs/assets"), "[output] assets")
    if not assets.resolve().is_relative_to(docs.resolve()):
        raise ConfigError("[output] assets must be inside [output] docs, so a page can link to it")

    hosts = images.get("hosts", [])
    if not isinstance(hosts, list) or not all(isinstance(host, str) and host for host in hosts):
        raise ConfigError("[images] hosts must be a list of host names")

    pages = {}
    for name, target in data.get("pages", {}).items():
        target = _relative(target, f"[pages] {name}")
        if not target.endswith(".md"):
            raise ConfigError(f"[pages] {name} must name a .md file")
        pages[name] = target

    return Site(
        export=root / _relative(source.get("export"), "[source] export"),
        docs=docs,
        assets=assets,
        manifest=root / _relative(output.get("manifest", "image_urls.tsv"), "[output] manifest"),
        # Lower case, as `urlsplit` gives the host it is compared with.
        image_hosts=tuple(host.lower() for host in hosts),
        include_drafts=bool(source.get("include_drafts", False)),
        posts_prefix=posts.get("link_prefix", ""),
        posts_dir=_relative(posts["dir"], "[posts] dir") if "dir" in posts else "",
        slugs=dict(posts.get("slugs", {})),
        tags={slug: tuple(names) for slug, names in posts.get("tags", {}).items()},
        pages=pages,
    )
