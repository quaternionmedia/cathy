# An export becomes pages

A site's owner downloads the export its platform writes, and `cathy convert`
turns it into Markdown pages the owner keeps. This page runs against a made-up
site in `tests/fixtures/site/`: an export in the shape Squarespace writes, and
the `cathy.toml` that says what to keep from it.

The site keeps two collections of posts. Each is a `[[posts]]` table in
`cathy.toml`, naming the link prefix its posts share and the directory their
pages are written to:

>>> from cathy import config, convert
>>> site = config.load(site_dir / "cathy.toml")
>>> [(posts.link_prefix, posts.dir) for posts in site.posts]
[('/projects/', 'projects'), ('/calendar/', 'calendar')]

`cathy.toml` refuses two collections whose prefixes overlap, so that a post is
in one collection at most, and two whose directories are one directory. A site
with one collection may write it as a single `[posts]` table.
`tests/test_convert.py` runs each of those.

One conversion writes the pages of both collections and the pages `cathy.toml`
lists:

>>> result = convert.convert(site)
>>> result.pages
['about.md', 'calendar/spring-concert.md', 'projects/brass-and-bellows.md', 'projects/night-market.md']

The rest stays in the export: a draft, a private post, a placeholder under
`/press/`, which no collection's prefix matches, a page `cathy.toml` does not
list, and an image attachment. The export's author block is never read, so
nothing in it reaches a page.

A page carries its title, date and tags as front matter. Its HTML becomes
Markdown, a video becomes a player, and an image links into the assets
directory relative to the page that shows it:

>>> print((site.docs / "projects" / "brass-and-bellows.md").read_text(encoding="utf-8"), end="")
---
title: "Brass & Bellows"
date: 2021-10-02
tags:
  - "music"
---
<BLANKLINE>
## The band
<BLANKLINE>
Four players and a *tuba*.
<BLANKLINE>
![On stage](../assets/stage-5a61154a.jpg)
<BLANKLINE>
<div class="video"><iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" frameborder="0" allowfullscreen></iframe></div>
<BLANKLINE>
![Tour poster](../assets/poster-0d386dc5.jpg)

Media the page cannot play becomes a link to it, and a title is written as a
YAML string whatever quotes it holds:

>>> print((site.docs / "projects" / "night-market.md").read_text(encoding="utf-8"), end="")
---
title: "The \"Night\" Market's Lights"
date: 2022-06-18
tags:
  - "music"
  - "tech"
---
<BLANKLINE>
Lanterns, wired to the sound desk.
<BLANKLINE>
![The market stage](../assets/stage-7733e5d7.jpg)
<BLANKLINE>
<div class="video"><iframe src="https://player.vimeo.com/video/123456789" frameborder="0" allowfullscreen></iframe></div>
<BLANKLINE>
[Listen on SoundCloud](https://soundcloud.com/example-ensemble/night-market)

A calendar post is written to its own collection's directory, with the tags
that collection gives it:

>>> print((site.docs / "calendar" / "spring-concert.md").read_text(encoding="utf-8"), end="")
---
title: "Spring Concert"
date: 2024-04-12
tags:
  - "concert"
---
<BLANKLINE>
An evening at the park bandstand.
<BLANKLINE>
![Concert poster](../assets/poster-c991ea2d.jpg)

Two different images are both called `stage.jpg` in the export, and two more
are both called `poster.jpg`, one in a project post and one in a calendar post.
Every image is named in the one conversion, across both collections, and each
image of a pair takes a suffix from a hash of its own URL. No two images share
a name, and the same export always gives the same names, whichever image is
read first:

>>> for url, name in sorted(result.images.items(), key=lambda pair: pair[1]):
...     print(name, url)
Band_Photo.png https://images.squarespace-cdn.com/content/v1/aaa/3/Band%20Photo.png
poster-0d386dc5.jpg https://images.squarespace-cdn.com/content/v1/aaa/4/poster.jpg
poster-c991ea2d.jpg https://images.squarespace-cdn.com/content/v1/ccc/5/poster.jpg
stage-5a61154a.jpg https://images.squarespace-cdn.com/content/v1/aaa/1/stage.jpg
stage-7733e5d7.jpg https://images.squarespace-cdn.com/content/v1/bbb/2/stage.jpg

An image on a host `cathy.toml` does not name stays a link to that host, and
is not listed for download:

>>> "](https://example.org/elsewhere.png)" in (site.docs / "about.md").read_text(encoding="utf-8")
True

The manifest is what `cathy fetch` reads: one URL and one file name per line,
separated by a tab. Conversion wrote it without opening a network connection:

>>> for line in site.manifest.read_text(encoding="utf-8").splitlines():
...     print(line.split("\t"))
['https://images.squarespace-cdn.com/content/v1/aaa/1/stage.jpg', 'stage-5a61154a.jpg']
['https://images.squarespace-cdn.com/content/v1/aaa/3/Band%20Photo.png', 'Band_Photo.png']
['https://images.squarespace-cdn.com/content/v1/aaa/4/poster.jpg', 'poster-0d386dc5.jpg']
['https://images.squarespace-cdn.com/content/v1/bbb/2/stage.jpg', 'stage-7733e5d7.jpg']
['https://images.squarespace-cdn.com/content/v1/ccc/5/poster.jpg', 'poster-c991ea2d.jpg']
