import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cathy import cli, fetch, net

BODY = b"\x89PNG not really"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Recorded before the response, so a test reading it after the client returns sees it.
        self.server.seen.append((self.command, self.path, self.headers.get("Authorization"), self.headers.get("Cookie")))
        if self.path == "/ok.png":
            self._send(200, BODY)
        elif self.path == "/short.png":
            # Announces more than it sends, then closes: an interrupted transfer.
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"x" * 10)
        elif self.path == "/away.png":
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/ok.png")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/slow.png":
            time.sleep(1.5)
            self._send(200, BODY)
        else:
            self._send(404, b"missing")

    def do_POST(self):
        self.server.seen.append(("POST", self.path, None, None))
        self._send(405, b"")

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # A client that timed out has closed its end; anything else is a fault in the handler.
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


@pytest.fixture
def server():
    # Port 0: the operating system picks a free port, so no other program's server is measured.
    httpd = _Server(("127.0.0.1", 0), _Handler)
    httpd.daemon_threads = True
    httpd.seen = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _rows(server, *names):
    return [(f"http://127.0.0.1:{server.server_port}/{name}", name) for name in names]


def _fetch(server, rows, assets: Path, **kwargs):
    return fetch.fetch(rows, assets, hosts={"127.0.0.1"}, schemes=("http",), **kwargs)


def test_a_complete_download_is_saved(server, tmp_path):
    result = _fetch(server, _rows(server, "ok.png"), tmp_path)
    assert result.saved == ["ok.png"]
    assert (tmp_path / "ok.png").read_bytes() == BODY


def test_an_interrupted_download_leaves_no_file_and_is_retried(server, tmp_path):
    for _ in range(2):
        result = _fetch(server, _rows(server, "short.png"), tmp_path)
        assert [url for url, _ in result.failed] == [_rows(server, "short.png")[0][0]]
        assert "10 of 100" in result.failed[0][1]
        assert list(tmp_path.iterdir()) == []


def test_a_write_cut_short_leaves_no_file(server, tmp_path, monkeypatch):
    real = Path.write_bytes

    def half_then_full_disk(self, data):
        real(self, data[: len(data) // 2])
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", half_then_full_disk)
    result = _fetch(server, _rows(server, "ok.png"), tmp_path)
    monkeypatch.undo()
    assert result.failed and "No space left" in result.failed[0][1]
    assert list(tmp_path.iterdir()) == []


def test_a_file_already_present_is_not_requested_again(server, tmp_path):
    _fetch(server, _rows(server, "ok.png"), tmp_path)
    requests = len(server.seen)
    result = _fetch(server, _rows(server, "ok.png"), tmp_path)
    assert result.present == ["ok.png"]
    assert len(server.seen) == requests


def test_an_error_status_is_a_failure(server, tmp_path):
    result = _fetch(server, _rows(server, "gone.png"), tmp_path)
    assert result.failed and "404" in result.failed[0][1]
    assert not (tmp_path / "gone.png").exists()


def test_a_redirect_to_another_host_is_refused_before_it_is_followed(server, tmp_path):
    result = _fetch(server, _rows(server, "away.png"), tmp_path)
    assert result.failed and "'localhost'" in result.failed[0][1]
    assert [path for _, path, _, _ in server.seen] == ["/away.png"]


def test_a_stalled_server_times_out(server, tmp_path):
    result = _fetch(server, _rows(server, "slow.png"), tmp_path, timeout=0.3)
    assert result.failed
    assert not (tmp_path / "slow.png").exists()


def test_every_request_is_a_get_without_credentials(server, tmp_path):
    _fetch(server, _rows(server, "ok.png", "gone.png"), tmp_path)
    assert {(method, auth, cookie) for method, _, auth, cookie in server.seen} == {("GET", None, None)}


def test_a_host_the_site_does_not_name_is_never_contacted(tmp_path):
    with pytest.raises(net.Refused, match="host"):
        net.get("https://elsewhere.example/a.png", hosts={"images.example"})
    result = fetch.fetch([("https://elsewhere.example/a.png", "a.png")], tmp_path, hosts={"images.example"})
    assert result.failed and not (tmp_path / "a.png").exists()


@pytest.mark.parametrize(
    "url, reason",
    [
        ("http://images.example/a.png", "scheme"),
        ("file:///etc/passwd", "scheme"),
        ("https://user:secret@images.example/a.png", "credentials"),
    ],
)
def test_a_scheme_or_credentials_outside_the_rule_are_refused(url, reason):
    with pytest.raises(net.Refused, match=reason):
        net.check(url, hosts={"images.example"}, schemes=("https",))


@pytest.mark.parametrize("name", ["../escaped.png", "sub/dir.png", "..", "C:evil.png"])
def test_a_manifest_name_cannot_write_outside_the_assets_directory(tmp_path, name):
    assets = tmp_path / "assets"
    result = fetch.fetch([("https://images.example/x.png", name)], assets, hosts={"images.example"})
    assert result.failed and "plain file name" in result.failed[0][1]
    assert sorted(path.name for path in tmp_path.rglob("*")) == ["assets"]


def test_a_malformed_manifest_row_names_its_line(tmp_path):
    manifest = tmp_path / "image_urls.tsv"
    manifest.write_text("https://images.example/a.png\ta.png\nno tab here\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"image_urls\.tsv:2"):
        fetch.read_manifest(manifest)


def test_the_command_exits_non_zero_when_any_image_fails(site_dir, capsys):
    (site_dir / "image_urls.tsv").write_text("https://elsewhere.example/a.png\ta.png\n", encoding="utf-8")
    assert cli.main(["fetch", "--config", str(site_dir / "cathy.toml")]) == 1
    assert "failed=1" in capsys.readouterr().out
