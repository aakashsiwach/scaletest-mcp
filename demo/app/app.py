import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        try:
            work_ms = max(0, min(250, int(query.get("work_ms", ["40"])[0])))
        except ValueError:
            work_ms = 40
        deadline = time.perf_counter() + work_ms / 1000
        value = 1
        while time.perf_counter() < deadline:
            value = (value * 33 + 7) % 1_000_003
        body = (
            "ScaleTest demo app OK; simulated_cpu_work_ms="
            + str(work_ms)
            + "; checksum="
            + str(value)
            + "\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        # Lightweight health check used by ScaleTest's inspect_target tool.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        return


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()