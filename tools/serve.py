#!/usr/bin/env python3
"""Lokalny podglad aplikacji. Tylko biblioteka standardowa.

    python3 tools/serve.py            # -> http://localhost:8765
    python3 tools/serve.py 3000

Nie uzywa os.getcwd(), bo w sandboxie bywa zablokowane, i wylacza cache,
zeby zmiany w plikach byly widoczne od razu po odswiezeniu.
"""
import http.server
import os
import socketserver
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "docs")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


class Server(socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("127.0.0.1", PORT), Handler) as httpd:
        sys.stderr.write("Tortownik: http://localhost:%d  (katalog %s)\n" % (PORT, ROOT))
        sys.stderr.flush()
        httpd.serve_forever()
