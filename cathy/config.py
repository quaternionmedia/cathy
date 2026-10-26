"""A site's `cathy.toml`: where its export is, what to keep, and where pages and images go.

Every path in the file is relative to the file itself.
"""

from __future__ import annotations

import itertools
import posixpath
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FORMATS = ("squarespace-wxr",)


class ConfigError(ValueError):
    """A `cathy.toml` cathy cannot act on."""


@dataclass(frozen=True)
class Collection:
    """The posts whose link starts with `link_prefix`, written to `dir` inside the docs directory."""

    link_prefix: str
    dir: str = ""
    slugs: dict[str, str] = field(default_factory=dict)
    tags: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Site:
    export: Path
    docs: Path
    assets: Path
    manifest: Path
    image_hosts: tuple[str, ...]
    include_drafts: bool = False
    posts: tuple[Collection, ...] = ()
    pages: dict[str, str] = field(default_factory=dict)


def _relative(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where} must be a non-empty string")
    normal = posixpath.normpath(value.replace("\\", "/"))
    if normal.startswith(("/", "..")) or ":" in normal:
        raise ConfigError(f"{where} must be a relative path inside the site, not {value!r}")
    return normal


def _collections(posts: object) -> tuple[Collection, ...]:
    # A single `[posts]` table is one collection; `[[posts]]` may be repeated.
    if isinstance(posts, dict):
        tables = [("[posts]", posts)]
    elif isinstance(posts, list):
        tables = [(f"[[posts]] {number}", table) for number, table in enumerate(posts, 1)]
    else:
        raise ConfigError("[posts] must be a table, or an array of tables written [[posts]]")

    collections = []
    for where, table in tables:
        if not isinstance(table, dict):
            raise ConfigError(f"{where} must be a table")
        prefix = table.get("link_prefix")
        if not isinstance(prefix, str) or not prefix:
            raise ConfigError(f"{where} link_prefix must be a non-empty string")
        collections.append(
            Collection(
                link_prefix=prefix,
                dir=_relative(table["dir"], f"{where} dir") if "dir" in table else "",
                slugs=dict(table.get("slugs", {})),
                tags={slug: tuple(names) for slug, names in table.get("tags", {}).items()},
            )
        )

    for one, other in itertools.combinations(collections, 2):
        if one.link_prefix.startswith(other.link_prefix) or other.link_prefix.startswith(one.link_prefix):
            raise ConfigError(
                f"[[posts]] link_prefix {one.link_prefix!r} and {other.link_prefix!r} overlap, so one post could be in both"
            )
        # Compared without case: on a case-insensitive disk the two are one directory.
        if (one.dir or ".").lower() == (other.dir or ".").lower():
            raise ConfigError(f"[[posts]] dir {one.dir or '.'!r} and {other.dir or '.'!r} are one directory")
    return tuple(collections)


def load(path: Path) -> Site:
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    source = data.get("source", {})
    output = data.get("output", {})
    images = data.get("images", {})

    if source.get("format") not in FORMATS:
        raise ConfigError(f"[source] format must be one of {list(FORMATS)}")
    docs = root / _relative(output.get("docs", "docs"), "[output] docs")
    assets = root / _relative(output.get("assets", "docs/assets"), "[output] assets")
    if not assets.resolve().is_relative_to(docs.resolve()):
        raise ConfigError("[output] assets must be inside [output] docs, so a page can link to it")

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
        image_hosts=tuple(images.get("hosts", ())),
        include_drafts=bool(source.get("include_drafts", False)),
        posts=_collections(data.get("posts", [])),
        pages=pages,
    )
