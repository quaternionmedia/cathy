"""`cathy convert` and `cathy fetch`, run against a site's `cathy.toml`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cathy import config, convert, fetch

COMMANDS = {
    "convert": "turn the export into Markdown pages and an image manifest; opens no network connection",
    "fetch": "download the images the manifest lists, from the hosts cathy.toml names",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cathy",
        description="Read a site's export into pages its owner keeps. cathy reads and never posts.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, summary in COMMANDS.items():
        command = commands.add_parser(name, help=summary, description=summary)
        command.add_argument("--config", type=Path, default=Path("cathy.toml"), help="default: ./cathy.toml")
    args = parser.parse_args(argv)

    try:
        site = config.load(args.config)
    except (OSError, ValueError) as error:
        print(f"cathy: {error}", file=sys.stderr)
        return 2

    if args.command == "convert":
        try:
            result = convert.convert(site)
        except (OSError, ValueError) as error:
            print(f"cathy: {error}", file=sys.stderr)
            return 2
        print(f"pages={len(result.pages)} images={len(result.images)} manifest={site.manifest}")
        return 0

    try:
        rows = fetch.read_manifest(site.manifest)
    except (OSError, ValueError) as error:
        print(f"cathy: {error}", file=sys.stderr)
        return 2
    result = fetch.fetch(rows, site.assets, hosts=site.image_hosts)
    for url, reason in result.failed:
        print(f"FAIL {url}: {reason}", file=sys.stderr)
    print(f"saved={len(result.saved)} present={len(result.present)} failed={len(result.failed)}")
    return 1 if result.failed else 0
