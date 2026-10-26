"""Turn a site's export into Markdown pages and a manifest of the images they show.

Conversion reads one local file and writes local files. It opens no network
connection; `cathy.fetch` is the step that downloads what the manifest lists.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit, urlunsplit

from markdownify import markdownify

from cathy import embeds, wxr
from cathy.config import Site

# Statuses a public page can come from. "private" and "trash" never do.
PUBLISHED = ("publish",)
DRAFTS = ("draft", "pending", "future")
_SAFE_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_HOLD = "CATHYEMBED{}X"


class ConvertError(ValueError):
    """An export cathy cannot turn into pages without losing or overwriting one."""


@dataclass(frozen=True)
class Converted:
    pages: list[str]
    images: dict[str, str]


def _yaml_string(text: str) -> str:
    # A JSON string is a YAML double-quoted scalar; the three characters YAML 1.1
    # reads as line breaks are escaped so a title round-trips through either.
    quoted = json.dumps(text, ensure_ascii=False)
    for char in ("\u0085", " ", " "):
        quoted = quoted.replace(char, f"\\u{ord(char):04x}")
    return quoted


def frontmatter(title: str, date: str = "", tags: Iterable[str] = ()) -> str:
    lines = ["---", f"title: {_yaml_string(title)}"]
    if re.match(r"\d{4}-\d{2}-\d{2}", date):
        lines.append(f"date: {date[:10]}")
    tags = list(tags)
    if tags:
        lines.append("tags:")
        lines += [f"  - {_yaml_string(tag)}" for tag in tags]
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def to_markdown(content: str) -> str:
    """Markdown for one item's HTML, image URLs left as they are in the export."""
    held: list[str] = []

    def hold(match: re.Match[str]) -> str:
        held.append(embeds.player(match.group(0)))
        return f"<p>{_HOLD.format(len(held) - 1)}</p>"

    content = re.sub(r"<(script|style)\b.*?</\1\s*>", "", content, flags=re.S | re.I)
    content = re.sub(r"<iframe\b.*?</iframe\s*>", hold, content, flags=re.S | re.I)
    content = re.sub(r"\[caption[^\]]*\]|\[/caption\]", "", content)
    body = markdownify(content, heading_style="ATX", bullets="-")
    body = re.sub(_HOLD.format(r"(\d+)"), lambda match: held[int(match.group(1))], body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _bare(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _file_name(url: str) -> str:
    name = unquote(posixpath.basename(urlsplit(url).path))
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    return name or "image"


def asset_names(urls: Iterable[str]) -> dict[str, str]:
    """A local file name for every image URL, the same for the same set of URLs.

    URLs differing only in their query are one image. Two images whose names
    match, ignoring case, both take a suffix from a hash of their URL, so
    neither keeps the plain name and no name depends on which was read first.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for bare in sorted({_bare(url) for url in urls}):
        groups[_file_name(bare).lower()].append(bare)
    names = {}
    for group in groups.values():
        for bare in group:
            name = _file_name(bare)
            if len(group) > 1:
                stem, ext = os.path.splitext(name)
                name = f"{stem}-{hashlib.sha256(bare.encode()).hexdigest()[:8]}{ext}"
            names[bare] = name
    return names


def _image_pattern(hosts: Iterable[str]) -> re.Pattern[str] | None:
    hosts = [re.escape(host) for host in hosts]
    if not hosts:
        return None
    return re.compile(rf"https?://(?:{'|'.join(hosts)})/[^\s\"'()<>\[\]]+")


def select(site: Site, item: wxr.Item) -> tuple[str, tuple[str, ...]] | None:
    """Where an item's page goes, relative to the docs directory, and its tags; None to leave it."""
    allowed = PUBLISHED + (DRAFTS if site.include_drafts else ())
    if item.status not in allowed:
        return None
    # `cathy.toml` refuses overlapping prefixes, so a post is in one collection at most.
    collection = next((posts for posts in site.posts if item.link.startswith(posts.link_prefix)), None)
    if item.kind == "post" and collection is not None:
        slug = collection.slugs.get(item.name, item.name)
        if not _SAFE_SLUG.fullmatch(slug):
            raise ConvertError(f"post {item.link!r} has slug {slug!r}, which is not a safe file name")
        return posixpath.join(collection.dir, f"{slug}.md"), collection.tags.get(slug, ())
    if item.kind == "page" and item.name in site.pages:
        return site.pages[item.name], ()
    return None


def convert(site: Site) -> Converted:
    planned: dict[str, tuple[str, str]] = {}
    for item in wxr.read(site.export):
        chosen = select(site, item)
        if chosen is None:
            continue
        page, tags = chosen
        # Compared without case: on a case-insensitive disk the second write replaces the first.
        if page.lower() in {other.lower() for other in planned}:
            raise ConvertError(f"two items in the export would both be written to {page}")
        planned[page] = (frontmatter(item.title, item.date, tags), to_markdown(item.html))

    pattern = _image_pattern(site.image_hosts)
    found = [url for _, body in planned.values() for url in (pattern.findall(body) if pattern else ())]
    # One call across every collection and page, so two images never share a name.
    names = asset_names(found)
    assets = site.assets.relative_to(site.docs).as_posix()

    for page, (head, body) in planned.items():
        here = posixpath.dirname(page) or "."
        if pattern:
            body = pattern.sub(
                lambda match: posixpath.relpath(f"{assets}/{names[_bare(match.group(0))]}", here), body
            )
        target = site.docs / page
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(head + body + "\n", encoding="utf-8", newline="\n")

    site.manifest.parent.mkdir(parents=True, exist_ok=True)
    site.manifest.write_text(
        "".join(f"{url}\t{name}\n" for url, name in sorted(names.items())), encoding="utf-8", newline="\n"
    )
    return Converted(pages=sorted(planned), images=names)
