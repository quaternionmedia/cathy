"""The one module in cathy that opens a network connection.

Every request is a GET with no body, no cookies and no credentials, to a host
the caller names. A redirect to any other host is refused before it is
followed. `tests/test_network_boundary.py` refuses a change that opens a
connection anywhere else in the package.
"""

from __future__ import annotations

import http.client
import urllib.request
from collections.abc import Collection
from urllib.parse import urlsplit

from cathy import __version__

USER_AGENT = f"cathy/{__version__}"
TIMEOUT = 30.0
MAX_BYTES = 64 * 1024 * 1024


class Failed(Exception):
    """A request that did not return the whole of a successful response."""


class Refused(Failed):
    """A request cathy will not make: a scheme, a host or a URL the caller did not allow."""


class Incomplete(Failed):
    """A response that ended before the length it announced."""


def check(url: str, *, hosts: Collection[str], schemes: Collection[str]) -> None:
    """Raise `Refused` unless `url` is one cathy may request."""
    parts = urlsplit(url)
    if parts.scheme not in schemes:
        raise Refused(f"scheme {parts.scheme!r} is not one of {sorted(schemes)}")
    if parts.username is not None or parts.password is not None:
        raise Refused("the URL carries credentials")
    if (parts.hostname or "") not in hosts:
        raise Refused(f"host {parts.hostname!r} is not one of {sorted(hosts)}")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts: Collection[str], schemes: Collection[str]) -> None:
        self.hosts = hosts
        self.schemes = schemes

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check(newurl, hosts=self.hosts, schemes=self.schemes)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get(
    url: str,
    *,
    hosts: Collection[str],
    schemes: Collection[str] = ("https",),
    timeout: float = TIMEOUT,
    max_bytes: int = MAX_BYTES,
) -> bytes:
    """Return the body of a GET to `url`, or raise `Failed`."""
    check(url, hosts=hosts, schemes=schemes)
    opener = urllib.request.build_opener(_CheckedRedirects(hosts, schemes))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            announced = response.headers.get("Content-Length")
            body = response.read(max_bytes + 1)
    except Failed:
        raise
    except (OSError, http.client.HTTPException) as error:
        raise Failed(str(error) or type(error).__name__) from error
    if len(body) > max_bytes:
        raise Failed(f"the response is larger than {max_bytes} bytes")
    if announced is not None and announced.isdigit() and len(body) != int(announced):
        raise Incomplete(f"received {len(body)} of {announced} bytes")
    return body
