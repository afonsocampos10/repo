from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LocalEditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path in ("", "/", "/index.html"):
            self.path = "/.vscode/repo-editor.html"
        super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), LocalEditorHandler)
    print(f"Editor local disponível em http://127.0.0.1:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor local parado.")
    finally:
        server.server_close()
