from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ipaddress
import json
import os
import shutil
import socket
import sys
import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROXY_PATH = "/__proxy"
PROXY_TIMEOUT = 30  # segundos por operação de rede
PROXY_MAX_BYTES = 100 * 1024 * 1024  # 100 MB

SAVE_PATH = "/__save"
SAVE_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
UPLOAD_PATH = "/__upload"
REPO_FILE = PROJECT_ROOT / "repo.json"
IPA_DIRECTORY = PROJECT_ROOT / "ipas"
BACKUP_FILE = PROJECT_ROOT / ".vscode" / "repo.backup.json"
SAVE_LOCK = threading.Lock()


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


def write_repo_file(payload):
    """Grava repo.json de forma atómica, guardando antes uma cópia da versão anterior."""
    if not payload.endswith(b"\n"):
        payload += b"\n"
    temp = REPO_FILE.with_name(REPO_FILE.name + ".tmp")
    with SAVE_LOCK:
        try:
            if REPO_FILE.exists():
                BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_FILE, BACKUP_FILE)
            with open(temp, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, REPO_FILE)
        except OSError as error:
            try:
                temp.unlink()
            except OSError:
                pass
            raise ProxyError(500, f"Não foi possível gravar repo.json: {error}")
    return len(payload)


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

    def do_POST(self):
        parts = urlsplit(self.path)
        if parts.path == UPLOAD_PATH:
            self.handle_upload(parts)
            return
        if parts.path != SAVE_PATH:
            self.send_json(404, {"error": "Endpoint não encontrado."})
            return
        self.handle_save()

    def allowed_origins(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def check_local_request(self, require_origin=False):
        """Bloqueia outros sites (e DNS rebinding) de usarem este servidor a partir do browser."""
        allowed = self.allowed_origins()
        if self.headers.get("Host", "") not in allowed:
            raise ProxyError(403, "Pedido recusado: Host não permitido.")
        origin = self.headers.get("Origin")
        if origin is None:
            if require_origin:
                raise ProxyError(403, "Pedido recusado: falta a origem do pedido.")
        elif origin.replace("http://", "", 1) not in allowed:
            raise ProxyError(403, "Pedido recusado: origem não permitida.")

    def handle_proxy(self, parts):
        try:
            self.check_local_request()
            values = parse_qs(parts.query).get("url", [])
            if len(values) != 1 or not values[0].strip():
                raise ProxyError(400, "Falta o parâmetro url.")
            body = fetch_remote(values[0].strip())
        except ProxyError as error:
            self.send_json(error.status, {"error": error.message})
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

    def handle_save(self):
        try:
            # A gravação exige que o pedido venha desta própria página (Host e Origin).
            self.check_local_request(require_origin=True)
            content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                raise ProxyError(415, "O conteúdo tem de ser application/json.")
            length = self.headers.get("Content-Length", "")
            if not length.isdigit():
                raise ProxyError(411, "Falta o tamanho do conteúdo.")
            size = int(length)
            if size == 0 or size > SAVE_MAX_BYTES:
                raise ProxyError(413, "O conteúdo está vazio ou excede o limite de 200 MB.")
            payload = self.rfile.read(size)
            if len(payload) != size:
                raise ProxyError(400, "O pedido chegou incompleto.")
            try:
                data = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError):
                raise ProxyError(400, "O conteúdo não é JSON válido.")
            if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
                raise ProxyError(400, "O repo.json deve ser um objeto com a propriedade apps[].")
            written = write_repo_file(payload)
        except ProxyError as error:
            self.send_json(error.status, {"error": error.message})
            return
        self.send_json(200, {"ok": True, "apps": len(data["apps"]), "bytes": written})

    def handle_upload(self, parts):
        temporary = None
        try:
            self.check_local_request(require_origin=True)
            values = parse_qs(parts.query).get("filename", [])
            if len(values) != 1 or not values[0].strip():
                raise ProxyError(400, "Falta o nome do ficheiro.")
            filename = Path(values[0].strip()).name
            if filename != values[0].strip() or not filename.lower().endswith(".ipa"):
                raise ProxyError(400, "Escolhe um ficheiro com extensão .ipa.")
            length = self.headers.get("Content-Length", "")
            if not length.isdigit():
                raise ProxyError(411, "Falta o tamanho do ficheiro.")
            size = int(length)
            if size == 0:
                raise ProxyError(400, "O IPA está vazio.")
            IPA_DIRECTORY.mkdir(parents=True, exist_ok=True)
            target = IPA_DIRECTORY / filename
            temporary = target.with_name(f".{target.name}.uploading")
            with open(temporary, "wb") as handle:
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ProxyError(400, "O upload chegou incompleto.")
                    handle.write(chunk)
                    remaining -= len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except ProxyError as error:
            if temporary:
                try:
                    temporary.unlink()
                except OSError:
                    pass
            self.send_json(error.status, {"error": error.message})
            return
        except OSError as error:
            if temporary:
                try:
                    temporary.unlink()
                except OSError:
                    pass
            self.send_json(500, {"error": f"Não foi possível guardar o IPA: {error}"})
            return
        self.send_json(200, {"ok": True, "filename": filename, "bytes": size})

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
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