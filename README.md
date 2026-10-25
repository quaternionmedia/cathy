# cathy

cathy reads a site's export from the public internet into pages its owner
keeps. It reads and never posts: no command signs in anywhere, and every
request it makes is a GET to a host the site's configuration names.

Its first source is the WordPress-format export Squarespace writes. Two
commands run against a site's `cathy.toml`:

- `cathy convert` turns the export into Markdown pages with front matter, and
  lists the images those pages show in a manifest. It opens no network
  connection.
- `cathy fetch` downloads the images the manifest lists into the site's assets
  directory.

```sh
uv sync
uv run cathy convert --config path/to/cathy.toml
uv run cathy fetch --config path/to/cathy.toml
```

[`walkthrough/`](walkthrough/) shows both against a made-up site, and the test
suite runs every page of it. The project's decisions are its records, on the
`project/cathy` branch of the governance corpus vendored at `governance/qm`.

cathy is licensed AGPL-3.0-or-later, copyright Quaternion Media. `REUSE.toml`
names the files that carry another licence, and `LICENSES/` holds each text.
