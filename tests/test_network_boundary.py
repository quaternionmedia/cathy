"""cathy reads and never posts, and `cathy/net.py` is the one module that opens a connection.

The guard reads the package's source. It cannot see a dependency that opens a
connection of its own, an attribute reached by a name built at runtime
(`getattr(net, "url" + "lib")`), or code outside `cathy/`.

Mutations run against it, each seen to fail before it was restored:
- `import urllib.request` added to `cathy/convert.py`
- `from urllib import request` added to `cathy/fetch.py`
- `urllib.request.urlopen(url)` called from `cathy/fetch.py`, which imports only `urllib.parse`
- `net.urllib.request.build_opener().open(url)` called from `cathy/fetch.py`
- `from cathy.net import http` added to `cathy/convert.py`
- `importlib.import_module("socket")` added to `cathy/wxr.py`
- `method="POST"` written into the `Request` in `cathy/net.py`
- `data=b""` passed to the `Request` in `cathy/net.py`
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "cathy"
NET = PACKAGE / "net.py"

# Modules that can open a connection, start a process that might, or load one by name.
NETWORK = {
    "socket", "ssl", "http", "urllib.request", "urllib3", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "websocket", "websockets",
    "subprocess", "webbrowser", "ctypes", "multiprocessing", "asyncio", "importlib",
}
CALLS = {"urlopen", "urlretrieve", "create_connection", "HTTPConnection", "HTTPSConnection", "__import__", "system", "popen"}


def _banned(module: str) -> bool:
    return any(module == name or module.startswith(name + ".") for name in NETWORK)


def _reaches(dotted: str) -> bool:
    # Any tail of the chain counts, so `net.urllib.request.build_opener` is `urllib.request` reached through net.
    parts = dotted.split(".")
    return any(_banned(".".join(parts[start:])) for start in range(len(parts)))


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _violations(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [f"import {alias.name}" for alias in node.names if _banned(alias.name)]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found += [
                f"from {node.module} import {alias.name}"
                for alias in node.names
                if _banned(node.module) or _banned(f"{node.module}.{alias.name}") or _banned(alias.name)
            ]
        elif isinstance(node, ast.Attribute) and _reaches(_dotted(node)):
            found.append(_dotted(node))
        elif isinstance(node, ast.Call):
            name = _dotted(node.func).rsplit(".", 1)[-1]
            if name in CALLS:
                found.append(f"{name}()")
    return [f"{path.relative_to(PACKAGE.parent).as_posix()}: {item}" for item in found]


def test_no_module_but_net_can_open_a_connection():
    modules = sorted(path for path in PACKAGE.rglob("*.py") if path != NET)
    assert modules, "the guard found no modules to read"
    assert [v for path in modules for v in _violations(path)] == []


def test_every_request_net_builds_is_a_get_with_no_body():
    requests = [
        node
        for node in ast.walk(ast.parse(NET.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and _dotted(node.func).endswith("Request")
    ]
    assert requests, "the guard found no Request in net.py"
    for call in requests:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert "data" not in keywords and len(call.args) == 1
        method = keywords.get("method")
        assert isinstance(method, ast.Constant) and method.value == "GET"


def test_the_guard_sees_the_connection_net_opens():
    # Read against net.py, the guard has to report something, or it reports nothing anywhere.
    assert "cathy/net.py: import urllib.request" in _violations(NET)
