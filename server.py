"""Interfaz web opcional de Jayth (la principal es la app de escritorio: app.py).
Solo escucha en 127.0.0.1 y exige un token distinto en cada arranque."""
import os, sys, re, json, uuid, base64, atexit, secrets, threading, argparse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jayth import paths, core, tools as T, agent as A

TOKEN = os.environ.get("JAYTH_TOKEN") or secrets.token_urlsafe(24)   # la variable es solo para pruebas
PORT = 8787
atexit.register(core.shutdown)


class H(BaseHTTPRequestHandler):
    server_version = "Jayth"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        return (self.headers.get("Host") or "").lower() in ("127.0.0.1:%d" % PORT, "localhost:%d" % PORT)

    def _origin_ok(self):
        o = self.headers.get("Origin")
        return o is None or o.lower() in ("http://127.0.0.1:%d" % PORT, "http://localhost:%d" % PORT)

    def _token_ok(self, q):
        t = self.headers.get("X-Token") or (q.get("t") or [""])[0]
        return secrets.compare_digest(t, TOKEN)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, bytes):
            body = (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 40_000_000:
            raise ValueError("cuerpo demasiado grande")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._host_ok():
            return self._send(403, {"error": "host no permitido"})
        p = u.path
        if p == "/":
            with open(os.path.join(paths.WEB_DIR, "index.html"), "r", encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", TOKEN)
            return self._send(200, html, "text/html; charset=utf-8", {"Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"})
        if not self._token_ok(q):
            return self._send(401, {"error": "token inválido"})
        if p == "/api/state":
            return self._send(200, {"settings": core.SET.snapshot(), "modes": A.MODES, "categories": T.CATEGORIES, "llm": core.LLM_MGR.status(),
                                    "sessions": [s.meta() for s in core.sorted_sessions()],
                                    "tools": [{"name": t["name"], "category": t["category"]} for t in T.TOOLS.values()]})
        if p == "/api/llm/log":
            return self._send(200, {"log": core.LLM_MGR.tail()})
        if p.startswith("/api/image/"):
            name = os.path.basename(p[len("/api/image/"):])
            fp = os.path.join(paths.IMG_DIR, name)
            if not re.fullmatch(r"[\w.-]+", name) or not os.path.isfile(fp):
                return self._send(404, {"error": "no existe"})
            ext = os.path.splitext(name)[1].lower()
            ct = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
            with open(fp, "rb") as f:
                return self._send(200, f.read(), ct)
        m = re.fullmatch(r"/api/events/(\w+)", p)
        if m:
            s = core.SESSIONS.get(m.group(1))
            if not s:
                return self._send(404, {"error": "sesión inexistente"})
            return self._sse(s, q)
        return self._send(404, {"error": "no encontrado"})

    def _sse(self, s, q):
        last = self.headers.get("Last-Event-ID")
        i = int(last) + 1 if last and last.isdigit() else int((q.get("after") or ["0"])[0])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                with s.cond:
                    if len(s.events) <= i:
                        s.cond.wait(15)
                    batch = s.events[i:i + 300]
                if batch:
                    out = "".join("id: %d\ndata: %s\n\n" % (e["i"], json.dumps(e, ensure_ascii=False)) for e in batch)
                    i += len(batch)
                else:
                    out = ": ka\n\n"
                self.wfile.write(out.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not (self._host_ok() and self._origin_ok()):
            return self._send(403, {"error": "origen no permitido"})
        if not self._token_ok(q):
            return self._send(401, {"error": "token inválido"})
        try:
            b = self._body()
        except Exception as e:
            return self._send(400, {"error": str(e)})
        p = u.path
        try:
            if p == "/api/settings":
                core.SET.update(b)
                return self._send(200, {"settings": core.SET.snapshot()})
            if p == "/api/session/new":
                return self._send(200, core.new_session().meta())
            if p == "/api/upload":
                ext = os.path.splitext(str(b.get("name", "")))[1].lower()
                ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") else ".png"
                name = uuid.uuid4().hex[:12] + ext
                with open(os.path.join(paths.IMG_DIR, name), "wb") as f:
                    f.write(base64.b64decode(b["data"]))
                return self._send(200, {"name": name})
            if p == "/api/llm/start":
                err = core.LLM_MGR.start()
                return self._send(200 if not err else 400, {"error": err} if err else {"ok": True})
            if p == "/api/llm/stop":
                core.LLM_MGR.stop()
                return self._send(200, {"ok": True})
            s = core.SESSIONS.get(str(b.get("sid", "")))
            if not s:
                return self._send(404, {"error": "sesión inexistente"})
            if p == "/api/send":
                text = str(b.get("text", "")).strip()
                imgs = [os.path.basename(str(n)) for n in b.get("images", [])]
                if not text and not imgs:
                    return self._send(400, {"error": "mensaje vacío"})
                err = s.send(text, imgs)
                return self._send(409 if err else 200, {"error": err} if err else {"ok": True})
            if p == "/api/stop":
                if s.run:
                    s.run.request_stop()
                return self._send(200, {"ok": True})
            if p == "/api/approve":
                ok = bool(s.run and s.run.resolve(str(b.get("id")), str(b.get("decision", "deny"))))
                return self._send(200, {"ok": ok})
            if p == "/api/session/delete":
                s.delete()
                return self._send(200, {"ok": True})
            if p == "/api/session/rename":
                s.title = str(b.get("title", ""))[:80] or s.title
                s.save()
                return self._send(200, s.meta())
        except Exception as e:
            return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})
        return self._send(404, {"error": "no encontrado"})


def main():
    global PORT
    ap = argparse.ArgumentParser(description="Interfaz web opcional de Jayth")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="abrir el navegador")
    ap.add_argument("--start-llm", action="store_true", help="encender el modelo al iniciar")
    args = ap.parse_args()
    PORT = args.port
    core.load_sessions()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    url = "http://127.0.0.1:%d/" % PORT
    print("Jayth (web) en", url, "- solo accesible desde este equipo")
    if args.start_llm:
        print("Modelo:", core.LLM_MGR.start() or "arrancando…")
    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
