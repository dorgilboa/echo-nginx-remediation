#!/usr/bin/env python3
"""Compatibility test: does our image behave like upstream nginx:1.25-bookworm?

How it works (differential testing): upstream is the oracle. For each scenario we start
upstream and our image as two separate containers, send the same raw HTTP bytes to both,
and compare the responses. Any mismatch is a failure; the script exits non-zero.

What "working correctly" means here:
  * Parity   - same status line, same body, same headers (except the volatile ones below),
               same image metadata (user, ports, entrypoint, ...), same config files.
  * Volatile - Date, ETag and Last-Modified legitimately differ between two correct servers.
               They are checked for presence on both sides and for sane values instead.
  * Fix      - checks on OUR image only, where behaviour is supposed to change
               (e.g. the bumped libssl3). Skipped when ours is upstream (self-test).

Run `make self-test` first: upstream against upstream must pass, otherwise the harness is broken.
Standard library only; needs a reachable `docker` CLI. Environment variables:
  ECHO_IMAGE (default echo-nginx:test), UPSTREAM_IMAGE (default nginx:1.25-bookworm), ECHO_HOST.
"""
from __future__ import annotations

import email.utils
import json
import os
import re
import shlex
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

UPSTREAM = os.environ.get("UPSTREAM_IMAGE", "nginx:1.25-bookworm")
OURS = os.environ.get("ECHO_IMAGE", "echo-nginx:test")
HOST = os.environ.get("ECHO_HOST", "127.0.0.1")
MIN_LIBSSL = "3.0.22-1~deb12u2"  # the bumped OpenSSL package version (see LOG / README)
CONF_DIR = Path(__file__).resolve().parent / "conf"
VOLATILE = ("date", "etag", "last-modified")
SELF_TEST = OURS == UPSTREAM
CLOCK_SLACK = timedelta(seconds=5)


# --------------------------------------------------------------------------- helpers

def docker(*args: str, check: bool = True, timeout: int = 180) -> subprocess.CompletedProcess:
    """Run a docker CLI command and return the result (raises with stderr if it fails)."""
    p = subprocess.run(["docker", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"`docker {' '.join(args)}` failed (exit {p.returncode}): {p.stderr.strip()}")
    return p


@dataclass
class Response:
    status: str
    headers: list[tuple[str, str]]
    body: bytes

    def header(self, name: str) -> str | None:
        return next((v for k, v in self.headers if k == name), None)


def parse_response(raw: bytes) -> Response:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = []
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers.append((name.strip().lower(), value.strip()))
    return Response(lines[0], headers, body)


def build_request(method: str, target: str, body: bytes = b"", extra: str = "") -> bytes:
    """Hand-built HTTP/1.1 request. Connection: close makes the server end the exchange for us."""
    head = f"{method} {target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n{extra}"
    if body or method == "POST":
        head += f"Content-Length: {len(body)}\r\n"
    return head.encode() + b"\r\n" + body


def exchange(port: int, payload: bytes, ctx: ssl.SSLContext | None = None, timeout: int = 10) -> bytes:
    """Send raw bytes, return everything the server sends back until it closes the connection."""
    chunks = []
    with socket.create_connection((HOST, port), timeout) as raw:
        raw.settimeout(timeout)
        s = ctx.wrap_socket(raw, server_hostname="localhost") if ctx else raw
        try:
            try:
                s.sendall(payload)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass  # e.g. server answered 413 and closed before we finished sending a big body
            try:
                while True:
                    data = s.recv(65536)
                    if not data:
                        break
                    chunks.append(data)
            except (ConnectionResetError, socket.timeout, ssl.SSLError):
                pass
        finally:
            s.close()
    return b"".join(chunks)


def tls_context(version: ssl.TLSVersion | None = None, alpn: list[str] | None = None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False          # the test certificate is self-signed
    ctx.verify_mode = ssl.CERT_NONE
    if version:
        ctx.minimum_version = ctx.maximum_version = version
    if alpn:
        ctx.set_alpn_protocols(alpn)
    return ctx


class Server:
    """A throwaway container for one image, with its ports published on 127.0.0.1."""

    def __init__(self, image: str, ports: tuple[int, ...] = (80,), binds: tuple[tuple[str, str], ...] = ()):
        self.image, self.ports, self.binds = image, ports, binds
        self.id: str | None = None
        self.host_port: dict[int, int] = {}

    def start(self) -> None:
        cmd = ["run", "-d"]
        for p in self.ports:
            cmd += ["-p", f"127.0.0.1::{p}"]
        for src, dst in self.binds:
            cmd += ["--mount", f"type=bind,source={src},target={dst},readonly"]
        self.id = docker(*cmd, self.image).stdout.strip()
        self._wait_ready()

    def _running(self) -> bool:
        return docker("inspect", "-f", "{{.State.Running}}", self.id).stdout.strip() == "true"

    def _wait_ready(self, timeout: float = 30) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._running():
                logs = docker("logs", self.id, check=False)
                code = docker("inspect", "-f", "{{.State.ExitCode}}", self.id, check=False).stdout.strip()
                raise RuntimeError(f"container from {self.image} exited early (exit code {code}); "
                                   f"it never served HTTP. Logs: {(logs.stdout + logs.stderr).strip() or '(none)'}")
            try:
                for p in self.ports:
                    self.host_port[p] = int(docker("port", self.id, f"{p}/tcp").stdout.split()[0].rsplit(":", 1)[1])
                if all(self._open(hp) for hp in self.host_port.values()):
                    return
            except (RuntimeError, IndexError):
                pass
            time.sleep(0.4)
        raise RuntimeError(f"{self.image} did not start listening within {timeout}s")

    @staticmethod
    def _open(port: int) -> bool:
        """Docker's port proxy accepts connections before nginx is up, then closes them.
        So 'ready' means: the connection stays open while we wait for the server to speak first."""
        try:
            with socket.create_connection((HOST, port), 1) as s:
                s.settimeout(0.5)
                try:
                    return s.recv(1) != b""
                except socket.timeout:
                    return True
                except ConnectionResetError:
                    return False
        except OSError:
            return False

    def stop(self) -> None:
        if self.id:
            docker("rm", "-f", self.id, check=False)
            self.id = None


# ----------------------------------------------------------------- shared assertions

class ParityCase(unittest.TestCase):
    """Starts upstream and ours with the same config; tests send identical bytes to both."""
    ports: tuple[int, ...] = (80,)
    binds: tuple[tuple[str, str], ...] = ()

    @classmethod
    def setUpClass(cls) -> None:
        cls.up = Server(UPSTREAM, cls.ports, cls.binds)
        cls.ours = Server(OURS, cls.ports, cls.binds)
        cls.addClassCleanup(cls.up.stop)
        cls.addClassCleanup(cls.ours.stop)
        cls.up.start()
        cls.ours.start()

    def both(self, payload: bytes, port: int = 80, ctx_factory=None) -> tuple[Response, Response]:
        raw_up = exchange(self.up.host_port[port], payload, ctx_factory() if ctx_factory else None)
        raw_ours = exchange(self.ours.host_port[port], payload, ctx_factory() if ctx_factory else None)
        self.assertTrue(raw_up, "upstream sent no response at all (test is broken, not the image)")
        return parse_response(raw_up), parse_response(raw_ours)

    def assertSame(self, up: Response, ours: Response, what: str) -> None:
        self.assertEqual(up.status, ours.status, f"{what}: status line")
        self.assertEqual(up.body, ours.body, f"{what}: body")
        stable = lambda r: sorted(h for h in r.headers if h[0] not in VOLATILE)  # noqa: E731
        self.assertEqual(stable(up), stable(ours), f"{what}: headers (volatile ones excluded)")
        self.check_volatile(up, ours, what)

    def check_volatile(self, up: Response, ours: Response, what: str) -> None:
        now = datetime.now(timezone.utc)
        for name in VOLATILE:
            u, o = up.header(name), ours.header(name)
            self.assertEqual(u is None, o is None, f"{what}: header {name!r} present on only one side")
            if o is None:
                continue
            if name == "etag":
                for v in (u, o):
                    self.assertRegex(v, r'^(W/)?"[0-9a-f]+(-[0-9a-f]+)?"$', f"{what}: odd ETag format")
                continue
            du, do = (email.utils.parsedate_to_datetime(v) for v in (u, o))
            self.assertLessEqual(do, now + CLOCK_SLACK, f"{what}: {name} is in the future")
            if name == "date":
                self.assertLessEqual(abs(now - do), timedelta(seconds=60), f"{what}: Date far from now")
                self.assertLessEqual(abs(du - do), CLOCK_SLACK, f"{what}: Date differs between servers")


# ------------------------------------------------------------------ parity scenarios

class DefaultConfigParity(ParityCase):
    """Out-of-the-box behaviour with the image's own default config."""

    def test_get_root(self):
        self.assertSame(*self.both(build_request("GET", "/")), "GET /")

    def test_head_root(self):
        self.assertSame(*self.both(build_request("HEAD", "/")), "HEAD /")

    def test_not_found(self):
        self.assertSame(*self.both(build_request("GET", "/does-not-exist")), "GET /does-not-exist")

    def test_post_to_static_file(self):
        self.assertSame(*self.both(build_request("POST", "/", b"hello")), "POST / (small body)")

    def test_large_body_rejected(self):
        # Default client_max_body_size is 1m, so 2 MiB must give 413 on both.
        up, ours = self.both(build_request("POST", "/", b"x" * (2 * 1024 * 1024)))
        self.assertIn("413", up.status, "sanity: upstream should reject the large body")
        self.assertSame(up, ours, "POST / (2 MiB body)")

    def test_malformed_request_line(self):
        self.assertSame(*self.both(b"THIS IS NOT HTTP\r\n\r\n"), "malformed request line")

    def test_unsupported_http_version(self):
        self.assertSame(*self.both(b"GET / HTTP/9.9\r\nHost: localhost\r\nConnection: close\r\n\r\n"), "HTTP/9.9")

    def test_uri_too_long(self):
        self.assertSame(*self.both(build_request("GET", "/" + "a" * 9000)), "GET with 9000-char path")


class CustomConfigParity(ParityCase):
    """A user-supplied config mounted over the default server block."""
    binds = ((str(CONF_DIR / "custom.conf"), "/etc/nginx/conf.d/default.conf"),)

    def test_custom_location(self):
        up, ours = self.both(build_request("GET", "/"))
        self.assertEqual(ours.header("x-echo-test"), "custom", "custom header missing: config not applied?")
        self.assertSame(up, ours, "GET / (custom config)")

    def test_raised_body_limit_accepts_5mib(self):
        up, ours = self.both(build_request("POST", "/upload", b"x" * (5 * 1024 * 1024)))
        self.assertIn("200", up.status)
        self.assertSame(up, ours, "POST /upload (5 MiB)")

    def test_tiny_body_limit_rejects_2kib(self):
        up, ours = self.both(build_request("POST", "/limited", b"x" * 2048))
        self.assertIn("413", up.status)
        self.assertSame(up, ours, "POST /limited (2 KiB)")


class TlsParity(ParityCase):
    """HTTPS: shows the OpenSSL in our image still terminates TLS like upstream's."""
    ports = (443,)

    @classmethod
    def setUpClass(cls) -> None:
        cls.certs = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.certs.cleanup)
        # Generate the throwaway certificate with the upstream image's openssl (same tool both sides).
        docker("run", "--rm", "--entrypoint", "openssl",
               "--mount", f"type=bind,source={cls.certs.name},target=/certs", UPSTREAM,
               "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
               "-keyout", "/certs/key.pem", "-out", "/certs/cert.pem")
        cls.binds = ((str(CONF_DIR / "tls.conf"), "/etc/nginx/conf.d/default.conf"),
                     (cls.certs.name, "/certs"))
        super().setUpClass()

    def test_https_get_per_tls_version(self):
        for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
            with self.subTest(version=version.name):
                up, ours = self.both(build_request("GET", "/"), 443,
                                     lambda v=version: tls_context(v, ["http/1.1"]))
                self.assertSame(up, ours, f"HTTPS GET / over {version.name}")

    def test_negotiated_protocol_and_alpn(self):
        def handshake(server: Server):
            with socket.create_connection((HOST, server.host_port[443]), 10) as raw:
                with tls_context(alpn=["h2", "http/1.1"]).wrap_socket(raw, server_hostname="localhost") as s:
                    return s.version(), s.selected_alpn_protocol()
        self.assertEqual(handshake(self.up), handshake(self.ours), "TLS version / ALPN choice differ")


# --------------------------------------------------- image-level parity (no server needed)

class ImageParity(unittest.TestCase):
    """Drop-in means the image's metadata and key files match upstream's, not only its HTTP answers."""

    def config(self, image: str) -> dict:
        c = json.loads(docker("image", "inspect", "-f", "{{json .Config}}", image).stdout)
        # Env is deliberately not compared yet: upstream sets NGINX_VERSION, NJS_VERSION, PKG_RELEASE.
        return {k: c.get(k) for k in ("User", "WorkingDir", "ExposedPorts", "Entrypoint", "Cmd", "StopSignal")}

    def test_image_metadata(self):
        self.assertEqual(self.config(UPSTREAM), self.config(OURS))

    @staticmethod
    def configure_args(image: str) -> list[str]:
        p = docker("run", "--rm", "--entrypoint", "nginx", image, "-V", check=False)
        text = p.stderr + p.stdout
        m = re.search(r"configure arguments: (.*)", text)
        if p.returncode != 0 or not m:
            raise AssertionError(f"`nginx -V` failed in {image}: {text.strip()[:300]}")
        # cc-opt / ld-opt values embed build paths and differ per builder; compare their presence only.
        return sorted(a.split("=", 1)[0] if a.startswith(("--with-cc-opt", "--with-ld-opt")) else a
                      for a in shlex.split(m.group(1)))

    def test_nginx_configure_arguments(self):
        # Known deliberate deviation: upstream's 4 dynamic-module packages are not built. They are
        # separate packages, so core configure arguments should still match.
        self.assertEqual(self.configure_args(UPSTREAM), self.configure_args(OURS))

    def test_config_files_and_entrypoint_scripts(self):
        cmd = ("cd / && sha256sum etc/nginx/nginx.conf etc/nginx/conf.d/default.conf etc/nginx/mime.types "
               "docker-entrypoint.sh docker-entrypoint.d/* 2>&1")
        run = lambda img: docker("run", "--rm", "--entrypoint", "sh", img, "-c", cmd, check=False).stdout  # noqa: E731
        self.assertEqual(run(UPSTREAM), run(OURS))


# --------------------------------------------------- fixes: only meaningful for our image

@unittest.skipIf(SELF_TEST, "ours is upstream: fix checks only make sense for our own image")
class FixVerification(unittest.TestCase):
    def test_libssl3_is_bumped(self):
        version = docker("run", "--rm", "--entrypoint", "dpkg-query", OURS,
                         "-W", "-f=${Version}", "libssl3").stdout.strip()
        ok = docker("run", "--rm", "--entrypoint", "dpkg", OURS,
                    "--compare-versions", version, "ge", MIN_LIBSSL, check=False).returncode == 0
        self.assertTrue(ok, f"libssl3 is {version!r}, need >= {MIN_LIBSSL}")

    def test_nginx_links_libssl3(self):
        out = docker("run", "--rm", "--entrypoint", "ldd", OURS, "/usr/sbin/nginx").stdout
        self.assertIn("libssl.so.3", out)

    # TODO (next step): CVE-2024-7347 - request a crafted mp4 (unordered stsc table) with ?start=
    # and assert our image rejects it cleanly and logs "unordered mp4 stsc chunks".


# --------------------------------------------------------------------------- main

def setUpModule() -> None:
    try:
        docker("version", "--format", "{{.Server.Version}}")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"docker is not reachable: {e}") from e
    for image in dict.fromkeys((UPSTREAM, OURS)):
        if docker("image", "inspect", image, check=False).returncode != 0:
            hint = f"docker pull {image}" if image == UPSTREAM else "make image"
            raise RuntimeError(f"image {image!r} not found locally - run: {hint}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
