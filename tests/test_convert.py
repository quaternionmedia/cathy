import datetime
import os
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from cathy import config, convert, fetch, net, wxr

MARKET_STAGE = "https://images.squarespace-cdn.com/content/v1/bbb/2/stage.jpg"


def _converted(site_dir: Path, **changes) -> tuple[config.Site, convert.Converted]:
    site = replace(config.load(site_dir / "cathy.toml"), **changes)
    return site, convert.convert(site)


def _rewrite(path: Path, old: str, new: str) -> None:
    # Bytes in and out, so the file keeps its line endings; a replacement that finds nothing fails here.
    before = path.read_bytes()
    assert old.encode() in before
    path.write_bytes(before.replace(old.encode(), new.encode()))


def _front(page: Path) -> dict:
    head = page.read_text(encoding="utf-8").split("---\n")[1]
    return yaml.safe_load(head)


def test_keeps_published_posts_under_the_prefix_and_the_listed_pages(site_dir):
    _, result = _converted(site_dir)
    assert result.pages == ["about.md", "projects/brass-and-bellows.md", "projects/night-market.md"]


def test_drafts_are_kept_only_when_asked_and_private_posts_never(site_dir):
    _, result = _converted(site_dir, include_drafts=True)
    assert "projects/unfinished.md" in result.pages
    assert "projects/members-only.md" not in result.pages


def test_nothing_from_the_author_block_reaches_a_page(site_dir):
    site, _ = _converted(site_dir)
    written = b"".join(path.read_bytes() for path in site.docs.rglob("*.md"))
    assert b"owner@example.com" not in written
    assert b"Site Owner" not in written


def test_front_matter_is_yaml_that_round_trips_the_title(site_dir):
    site, _ = _converted(site_dir)
    front = _front(site.docs / "projects" / "night-market.md")
    assert front == {"title": "The \"Night\" Market's Lights", "date": datetime.date(2022, 6, 18), "tags": ["music", "tech"]}


@pytest.mark.parametrize(
    "title",
    ["It's \"both\"", "back\\slash", "colon: and # hash", "Café — 東京", "line separator", "tab\there"],
)
def test_front_matter_round_trips_awkward_titles(title):
    head = convert.frontmatter(title).split("---\n")[1]
    assert yaml.safe_load(head)["title"] == title


def test_images_link_relative_to_the_page_that_shows_them(site_dir):
    site, result = _converted(site_dir)
    about = (site.docs / "about.md").read_text(encoding="utf-8")
    post = (site.docs / "projects" / "brass-and-bellows.md").read_text(encoding="utf-8")
    assert "](assets/Band_Photo.png)" in about
    assert f"](../assets/{result.images['https://images.squarespace-cdn.com/content/v1/aaa/1/stage.jpg']})" in post


def test_an_image_on_another_host_stays_a_link_and_is_not_listed(site_dir):
    site, result = _converted(site_dir)
    assert "](https://example.org/elsewhere.png)" in (site.docs / "about.md").read_text(encoding="utf-8")
    assert not any("example.org" in url for url in result.images)


def test_an_http_image_on_a_named_host_is_listed_by_the_https_url_fetch_requests(site_dir):
    _rewrite(site_dir / "export.xml", MARKET_STAGE, MARKET_STAGE.replace("https://", "http://"))
    site, result = _converted(site_dir)
    post = (site.docs / "projects" / "night-market.md").read_text(encoding="utf-8")
    assert f"](../assets/{result.images[MARKET_STAGE]})" in post
    for url, _ in fetch.read_manifest(site.manifest):
        net.check(url, hosts=site.image_hosts, schemes=("https",))


def test_an_image_whose_host_the_export_writes_in_capitals_is_linked_locally(site_dir):
    _rewrite(site_dir / "export.xml", MARKET_STAGE, MARKET_STAGE.replace("images.squarespace-cdn.com", "Images.Squarespace-CDN.com"))
    site, result = _converted(site_dir)
    post = (site.docs / "projects" / "night-market.md").read_text(encoding="utf-8")
    assert f"](../assets/{result.images[MARKET_STAGE]})" in post


def test_a_host_cathy_toml_names_in_capitals_is_matched_and_may_be_requested(site_dir):
    _rewrite(site_dir / "cathy.toml", '"images.squarespace-cdn.com"', '"Images.Squarespace-CDN.com"')
    site, result = _converted(site_dir)
    assert MARKET_STAGE in result.images
    net.check(MARKET_STAGE, hosts=site.image_hosts, schemes=("https",))


def test_a_query_string_does_not_make_a_second_image():
    names = convert.asset_names(["https://h/a/stage.jpg?format=1500w", "https://h/a/stage.jpg"])
    assert names == {"https://h/a/stage.jpg": "stage.jpg"}


def test_colliding_names_both_take_a_suffix_whatever_order_they_are_read_in():
    urls = ["https://h/a/stage.jpg", "https://h/b/stage.jpg", "https://h/c/Stage.JPG"]
    names = convert.asset_names(urls)
    assert names == convert.asset_names(reversed(urls))
    assert len({name.lower() for name in names.values()}) == 3
    assert "stage.jpg" not in {name.lower() for name in names.values()}


def test_output_is_identical_under_any_hash_seed(site_dir, tmp_path):
    outputs = []
    for seed in ("1", "2"):
        copy = tmp_path / f"seed-{seed}"
        copy.mkdir()
        for name in ("cathy.toml", "export.xml"):
            (copy / name).write_bytes((site_dir / name).read_bytes())
        env = {**os.environ, "PYTHONHASHSEED": seed}
        subprocess.run([sys.executable, "-m", "cathy", "convert", "--config", str(copy / "cathy.toml")], env=env, check=True, capture_output=True)
        outputs.append({path.relative_to(copy).as_posix(): path.read_bytes() for path in sorted(copy.rglob("*")) if path.is_file()})
    assert outputs[0] and outputs[0] == outputs[1]


def test_pages_and_manifest_are_written_with_lf_line_endings(site_dir):
    site, _ = _converted(site_dir)
    for path in [site.manifest, *site.docs.rglob("*.md")]:
        assert b"\r\n" not in path.read_bytes(), path


def test_conversion_opens_no_network_connection(site_dir, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("conversion opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    _, result = _converted(site_dir)
    assert result.pages


def test_two_items_bound_for_one_page_stop_the_conversion(site_dir):
    with pytest.raises(convert.ConvertError, match="both be written"):
        _converted(site_dir, slugs={"x9k2q7w4m1zp8v3d6b0n5c": "Brass-And-Bellows"})


def test_a_slug_that_leaves_the_directory_stops_the_conversion(site_dir):
    with pytest.raises(convert.ConvertError, match="not a safe file name"):
        _converted(site_dir, slugs={"x9k2q7w4m1zp8v3d6b0n5c": "../escaped"})


def test_scripts_and_styles_leave_no_text_behind():
    assert convert.to_markdown("<p>kept</p><style>.a { color: red }</style><script>alert(1)</script>") == "kept"


def test_the_reader_exposes_no_author_field():
    assert "author" not in " ".join(wxr.Item.__dataclass_fields__)


def test_config_refuses_assets_outside_docs(site_dir):
    path = site_dir / "cathy.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('assets = "docs/assets"', 'assets = "assets"'), encoding="utf-8")
    with pytest.raises(config.ConfigError, match="inside"):
        config.load(path)


def test_config_refuses_a_path_outside_the_site(site_dir):
    path = site_dir / "cathy.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('export = "export.xml"', 'export = "../export.xml"'), encoding="utf-8")
    with pytest.raises(config.ConfigError, match="relative path inside the site"):
        config.load(path)


@pytest.mark.parametrize("hosts", ['"images.squarespace-cdn.com"', "[1]", '[""]'])
def test_config_refuses_hosts_that_are_not_a_list_of_names(site_dir, hosts):
    _rewrite(site_dir / "cathy.toml", '["images.squarespace-cdn.com"]', hosts)
    with pytest.raises(config.ConfigError, match=r"\[images\] hosts"):
        config.load(site_dir / "cathy.toml")
