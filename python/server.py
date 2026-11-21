import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# Keep the project directory clean when launched from Excel.
sys.dont_write_bytecode = True
if sys.version_info < (3, 10):
    raise SystemExit("LatticeLab needs Python 3.10 or later")

from jobs import POOL, enqueue, get_job


ROOT = Path(__file__).resolve().parents[1]


def engine_status() -> dict:
    """Only the engines actually available are announced"""
    try:
        from excel_bridge import status

        vba = status()
    except ImportError:
        vba = {"available": False, "reason": "Le pont Excel n’est pas encore installé"}
    return {"python": {"available": True}, "vba": vba}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        """Deactivate the query log to keep the terminal readable"""
        return

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        """Returns the bytes of the response with its type and HTTP headers"""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy", "default-src 'self'; style-src 'self'; object-src 'none'"
        )
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value: object, status: int = 200) -> None:
        """Encode the result in JSON by refusing non-finite numbers"""
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_bytes(data, "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        """The interface, the state of the engines or the monitoring of a calculation are used."""
        path = urlsplit(self.path).path
        if path == "/api/status":
            self.send_json(engine_status())
        elif path.startswith("/api/jobs/"):
            job = get_job(path.rsplit("/", 1)[-1])
            self.send_json(job or {"error": "Calculation not found"}, 200 if job else 404)
        else:
            self.serve_static(path)

    def serve_static(self, path: str) -> None:
        """Only supported interface files and empty icon"""
        name = "index.html" if path == "/" else path.lstrip("/")
        if name == "favicon.svg":
            self.send_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml")
            return
        allowed = {"index.html", "app.css", "app.js", "charts.js"}
        file = ROOT / "interface" / name
        if name not in allowed or not file.is_file():
            self.send_json({"error": "Page not found"}, 404)
            return
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_bytes(file.read_bytes(), content_type + "; charset=utf-8")

    def check_request(self) -> None:
        """Check that the JSON query comes from the local application"""
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if host not in allowed:
            raise ValueError("The server accepts local requests only")
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in allowed}:
            raise ValueError("Request origin is not allowed")
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Expected a JSON request")

    def do_POST(self) -> None:
        """Check the body received before adding a calculation to the line"""
        try:
            self.check_request()
            if self.path != "/api/jobs":
                self.send_json({"error": "Action not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 1000000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            self.send_json({"id": enqueue(payload)}, 202)
        except (ValueError, TypeError, KeyError) as error:
            self.send_json({"error": str(error)}, 400)


def serve(port: int = 8765, open_browser: bool = False) -> None:
    """Launch the local server and open the browser if requested"""
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        if port == 0:
            raise
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print("LatticeLab " + url, flush=True)
    if open_browser:
        # Open the browser after the server is started
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        POOL.shutdown(wait=True, cancel_futures=True)


def main() -> None:
    """Read the launch options and then start the server"""
    parser = argparse.ArgumentParser(description="Start the local LatticeLab server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()
    serve(options.port, not options.no_browser)


if __name__ == "__main__":
    main()
