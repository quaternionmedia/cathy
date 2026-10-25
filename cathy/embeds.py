"""Turn an exported `<iframe>` into a player the page keeps, or a link to the media."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlsplit

_ID = re.compile(r"[\w-]{11}")
_GENERIC_TITLES = {"", "youtube embed", "embedded content"}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _on(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def youtube_id(url: str) -> str | None:
    """The video id of a YouTube URL, or None for a playlist, a channel or another host."""
    parts = urlsplit(url)
    host = _host(url)
    segments = [segment for segment in parts.path.split("/") if segment]
    if _on(host, "youtu.be"):
        candidate = segments[0] if segments else ""
    elif _on(host, "youtube.com") or _on(host, "youtube-nocookie.com"):
        if segments[:1] == ["watch"]:
            candidate = parse_qs(parts.query).get("v", [""])[0]
        elif len(segments) >= 2 and segments[0] in ("embed", "shorts", "live", "v"):
            candidate = segments[1]
        else:
            return None
    else:
        return None
    # `videoseries` is eleven word characters, and is a playlist rather than a video.
    if candidate == "videoseries" or not _ID.fullmatch(candidate):
        return None
    return candidate


def vimeo_id(url: str) -> str | None:
    host = _host(url)
    if not _on(host, "vimeo.com"):
        return None
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    if host == "player.vimeo.com":
        segments = segments[1:] if segments[:1] == ["video"] else []
    return segments[0] if segments and segments[0].isdigit() else None


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf"""\b{name}\s*=\s*(["'])(.*?)\1""", tag, flags=re.S | re.I)
    return html.unescape(match.group(2)) if match else ""


def _link_target(url: str) -> str:
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def _link_text(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


def player(iframe: str) -> str:
    """Markdown for one `<iframe>`: a player for YouTube and Vimeo, a link for anything else."""
    src = _attribute(iframe, "src")
    if not src:
        return ""
    if src.startswith("//"):
        src = "https:" + src
    if _on(_host(src), "embedly.com"):
        params = parse_qs(urlsplit(src).query)
        src = params.get("url", params.get("src", [src]))[0]

    video = youtube_id(src)
    if video:
        return (
            f'<div class="video"><iframe src="https://www.youtube.com/embed/{video}"'
            ' frameborder="0" allowfullscreen></iframe></div>'
        )
    video = vimeo_id(src)
    if video:
        return (
            f'<div class="video"><iframe src="https://player.vimeo.com/video/{video}"'
            ' frameborder="0" allowfullscreen></iframe></div>'
        )

    title = _attribute(iframe, "title").strip()
    host = _host(src)
    if title.lower() not in _GENERIC_TITLES:
        label = title
    elif _on(host, "youtube.com") or _on(host, "youtu.be"):
        label = "Watch on YouTube"
    elif _on(host, "soundcloud.com"):
        label = "Listen on SoundCloud"
    else:
        label = "Open media"
    return f"[{_link_text(label)}]({_link_target(src)})"
