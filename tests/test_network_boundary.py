"""cathy reads and never posts, and `cathy/net.py` is the one module that opens a connection.

The guard reads the package's source. `ROUTES` and `NOT_A_GET` are changes it
refuses, and each is run against it with the rest of the suite. It cannot see a
dependency that opens a connection of its own, an attribute reached by a name
built at runtime (`getattr(net, "url" + "lib")`), or code outside `cathy/`.
What `cathy/net.py` sends is seen at run time by `tests/test_fetch.py`.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "cathy"
NET = PACKAGE / "net.py"

# Modules that can open a connection, start a process that might, or load or run code by name or from data.
NETWORK = {
    "socket", "ssl", "http", "urllib.request", "urllib3", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "websocket", "websockets",
    "subprocess", "webbrowser", "ctypes", "multiprocessing", "asyncio", "importlib",
    "xml.sax", "pty", "builtins", "sys.modules", "pkgutil", "runpy", "code", "codeop", "zipimport",
    "pickle", "marshal", "shelve",
}
CALLS = {
    "urlopen", "urlretrieve", "create_connection", "HTTPConnection", "HTTPSConnection", "__import__", "system", "popen",
    "startfile", "posix_spawn", "posix_spawnp", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
    "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
}
# Builtins that run code or load a module from a string, refused wherever they are named,
# so binding one to another name does not hide it.
DYNAMIC = {"exec", "eval", "compile", "__import__", "__builtins__"}
# A string naming any of the above is refused too, so `getattr(os, "system")` is seen as `os.system`.

# Each opens a connection, or could, from a module other than net.py.
ROUTES = [
    "import urllib.request",
    "from urllib import request",
    "import urllib.parse\nurllib.request.urlopen(url)",
    "net.urllib.request.build_opener().open(url)",
    "from cathy.net import http",
    'importlib.import_module("socket")',
    "import xml.sax\nxml.sax.parse(url, handler)",
    "os.startfile(url)",
    'os.execvp("curl", ["curl", url])',
    'os.spawnlp(os.P_WAIT, "curl", "curl", url)',
    'exec("import socket")',
    'run = exec\nrun("import socket")',
    'eval("__imp" + "ort__")("socket")',
    'sys.modules["urllib.request"].build_opener().open(url)',
    'import builtins\nbuiltins.exec("import socket")',
    "from os import startfile as go\ngo(url)",
    'getattr(os, "startfile")(url)',
    'vars(os)["system"]("curl")',
    'import pkgutil\npkgutil.resolve_name("socket")',
    'import runpy\nrunpy.run_module("http.server")',
    'import code\ncode.InteractiveInterpreter().runsource("import socket")',
    "import pickle\npickle.loads(blob)",
]

# Each, written into net.py, could send a body or a method other than GET.
NOT_A_GET = [
    'urllib.request.Request(url, method="POST")',
    'urllib.request.Request(url, data=b"", method="GET")',
    'urllib.request.Request(url, b"", method="GET")',
    'urllib.request.Request(url, method="GET", **options)',
    'opener.open(request, b"x", timeout=timeout)',
    'opener.open(request, data=b"x", timeout=timeout)',
    'request.method = "POST"',
    'request.data = b"x"',
    'setattr(request, "method", "POST")',
]


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


def _violations_in(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [f"import {alias.name}" for alias in node.names if _banned(alias.name)]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found += [
                f"from {node.module} import {alias.name}"
                for alias in node.names
                if _banned(node.module) or _banned(f"{node.module}.{alias.name}") or _banned(alias.name)
                or alias.name in CALLS | DYNAMIC
            ]
        elif isinstance(node, ast.Attribute) and _reaches(_dotted(node)):
            found.append(_dotted(node))
        elif isinstance(node, ast.Call):
            name = _dotted(node.func).rsplit(".", 1)[-1]
            if name in CALLS:
                found.append(f"{name}()")
        elif isinstance(node, ast.Name) and node.id in DYNAMIC:
            found.append(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in CALLS | DYNAMIC or _banned(node.value):
                found.append(repr(node.value))
    return found


def _violations(path: Path) -> list[str]:
    where = path.relative_to(PACKAGE.parent).as_posix()
    return [f"{where}: {item}" for item in _violations_in(path.read_text(encoding="utf-8"))]


def _not_a_get(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = _dotted(node.func).rsplit(".", 1)[-1]
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            # A body can arrive as `data`, a second positional, or inside `*args` or `**options`.
            body = "data" in keywords or None in keywords or len(node.args) != 1 or any(
                isinstance(arg, ast.Starred) for arg in node.args
            )
            method = keywords.get("method")
            if name == "Request" and (body or not (isinstance(method, ast.Constant) and method.value == "GET")):
                found.append(f"line {node.lineno}: a Request that is not a GET with no body")
            elif name in ("open", "urlopen") and body:
                found.append(f"line {node.lineno}: {name}() given a body")
            elif name == "setattr":
                found.append(f"line {node.lineno}: setattr()")
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found += [
                f"line {node.lineno}: .{target.attr} assigned"
                for target in targets
                if isinstance(target, ast.Attribute) and target.attr in ("data", "method")
            ]
    return found


def test_no_module_but_net_can_open_a_connection():
    modules = sorted(path for path in PACKAGE.rglob("*.py") if path != NET)
    assert modules, "the guard found no modules to read"
    assert [v for path in modules for v in _violations(path)] == []


@pytest.mark.parametrize("source", ROUTES)
def test_the_guard_refuses_each_route_to_a_connection(source):
    assert _violations_in(source)


def test_every_request_net_builds_is_a_get_with_no_body():
    source = NET.read_text(encoding="utf-8")
    calls = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)]
    assert any(_dotted(call.func).endswith("Request") for call in calls), "the guard found no Request in net.py"
    assert _not_a_get(source) == []


@pytest.mark.parametrize("source", NOT_A_GET)
def test_the_guard_refuses_each_request_that_is_not_a_get(source):
    assert _not_a_get(source)


def test_the_guard_sees_the_connection_net_opens():
    # Read against net.py, the guard has to report something, or it reports nothing anywhere.
    assert "cathy/net.py: import urllib.request" in _violations(NET)
