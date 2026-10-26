"""Read a WordPress-format export (WXR), the file Squarespace's export writes.

Only the fields a page is made from are read. The export's author block, its
comments and its attachment metadata are never parsed, so nothing personal in
them can reach a page.
"""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


@dataclass(frozen=True)
class Item:
    kind: str
    name: str
    link: str
    title: str
    date: str
    status: str
    html: str


def read(path: Path) -> list[Item]:
    root = ET.parse(path).getroot()
    return [
        Item(
            kind=item.findtext("wp:post_type", "", NS),
            name=item.findtext("wp:post_name", "", NS),
            link=item.findtext("link", "") or "",
            title=html.unescape(item.findtext("title", "") or "").strip(),
            date=item.findtext("wp:post_date", "", NS) or "",
            status=item.findtext("wp:status", "", NS),
            html=item.findtext("content:encoded", "", NS) or "",
        )
        for item in root.iter("item")
    ]
