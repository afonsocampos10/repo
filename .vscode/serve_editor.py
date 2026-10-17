from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ipaddress
import json
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROXY_PATH = "/__proxy"
PROXY_TIMEOUT = 30  # segundos por operação de rede
PROXY_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


class ProxyError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def validate_target(url):
    """Aceita só http(s) para hosts públicos, para o proxy não alcançar a rede local."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ProxyError(400, "Só são aceites URLs http:// ou https://.")
    if not parts.hostname:
        raise ProxyError(400, "URL inválido.")
    if parts.username or parts.password:
        raise ProxyError(400, "URLs com credenciais não são permitidos.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, ValueError):
        raise ProxyError(502, "Não foi possível resolver o endereço do servidor.")
    for info in addresses:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            raise ProxyError(403, "Endereço de destino inválido.")
        if not ip.is_global:
            raise ProxyError(403, "O proxy local não acede a endereços privados ou locais.")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Revalida cada redirecionamento, senão um site público podia apontar para a rede interna."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_remote(url):
    validate_target(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "repo-editor-local/1.0",
            "Accept": "application/json, */*",
        },
    )
    opener = urllib.request.build_opener(SafeRedirectHandler)
    try:
        with opener.open(request, timeout=PROXY_TIMEOUT) as upstream:
            declared = upstream.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > PROXY_MAX_BYTES:
                raise ProxyError(413, "O ficheiro excede o limite de 100 MB.")
            chunks = []
            total = 0
            while True:
                chunk = upstream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > PROXY_MAX_BYTES:
                    raise ProxyError(413, "O ficheiro excede o limite de 100 MB.")
                chunks.append(chunk)
            return b"".join(chunks)
    except ProxyError:
        raise
    except urllib.error.HTTPError as error:
        raise ProxyError(502, f"O servidor remoto respondeu com HTTP {error.code}.")
    except TimeoutError:
        raise ProxyError(504, "O servidor remoto demorou demasiado a responder.")
    except OSError as error:
        raise ProxyError(502, f"Falha ao contactar o servidor remoto: {error}")


class LocalEditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == PROXY_PATH:
            self.handle_proxy(parts)
            return
        if parts.path in ("", "/", "/index.html"):
            self.path = "/.vscode/repo-editor.html"
        super().do_GET()

    def allowed_origins(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def handle_proxy(self, parts):
        try:
            # Bloqueia outros sites (e DNS rebinding) de usarem este proxy a partir do browser.
            allowed = self.allowed_origins()
            if self.headers.get("Host", "") not in allowed:
                raise ProxyError(403, "Pedido recusado: Host não permitido.")
            origin = self.headers.get("Origin")
            if origin is not None and origin.replace("http://", "", 1) not in allowed:
                raise ProxyError(403, "Pedido recusado: origem não permitida.")
            values = parse_qs(parts.query).get("url", [])
            if len(values) != 1 or not values[0].strip():
                raise ProxyError(400, "Falta o parâmetro url.")
            body = fetch_remote(values[0].strip())
        except ProxyError as error:
            self.send_json_error(error.status, error.message)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json_error(self, status, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


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