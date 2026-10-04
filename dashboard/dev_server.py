"""
dashboard/dev_server.py — Serveur local du dashboard (équivalent de vercel.json pour tester sans Vercel).

Sert les fichiers de dashboard/ et relaie /nhl/... vers https://api-web.nhle.com/v1/... (l'API NHL
n'autorise pas les appels directs depuis un navigateur).

Usage:
    python dashboard/dev_server.py [port]      # http://localhost:8000
"""
import http.server
import logging
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
NHL_API = "https://api-web.nhle.com/v1/"
logger = logging.getLogger("Dashboard.Dev")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 (API de http.server)
        if not self.path.startswith("/nhl/"):
            return super().do_GET()
        url = NHL_API + self.path[len("/nhl/"):]
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "BetEngine-dashboard"}), timeout=20) as r:
                body, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, status = e.read(), e.code
        except urllib.error.URLError as e:
            logger.error(f"API NHL injoignable ({url}) : {e}")
            body, status = b'{"error": "API NHL injoignable"}', 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Dashboard : http://localhost:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
