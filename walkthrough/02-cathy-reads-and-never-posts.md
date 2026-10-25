# cathy reads and never posts

`cathy fetch` downloads the images a manifest lists, through `cathy.net`, the
one module in cathy that opens a connection. Each request is a GET over HTTPS
to a host the site's `cathy.toml` names, and carries no credentials. Anything
else is refused before a connection is opened.

>>> from cathy import config, fetch, net
>>> site = config.load(site_dir / "cathy.toml")
>>> site.image_hosts
('images.squarespace-cdn.com',)
>>> net.check("https://images.squarespace-cdn.com/content/v1/aaa/1/stage.jpg", hosts=site.image_hosts, schemes=("https",))
>>> net.check("https://example.org/elsewhere.png", hosts=site.image_hosts, schemes=("https",))
Traceback (most recent call last):
...
cathy.net.Refused: host 'example.org' is not one of ['images.squarespace-cdn.com']
>>> net.check("http://images.squarespace-cdn.com/a.jpg", hosts=site.image_hosts, schemes=("https",))
Traceback (most recent call last):
...
cathy.net.Refused: scheme 'http' is not one of ['https']

A refused row is reported as a failure, and nothing is written for it:

>>> result = fetch.fetch([("https://example.org/elsewhere.png", "elsewhere.png")], site.assets, hosts=site.image_hosts)
>>> result.failed
[('https://example.org/elsewhere.png', "host 'example.org' is not one of ['images.squarespace-cdn.com']")]
>>> list(site.assets.iterdir())
[]

A redirect is checked by the same rule before it is followed. A download is
written beside its target and renamed into place only once the whole body has
arrived, so an image already on disk is a complete one, and `cathy fetch`
exits non-zero when any row fails. `tests/test_fetch.py` runs each of those
against a server on the loopback interface.

Nothing in cathy signs in, posts or publishes. `tests/test_network_boundary.py`
refuses a change that opens a connection anywhere but `cathy/net.py`, or makes
a request there that is not a GET.
