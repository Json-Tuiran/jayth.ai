"""Infraestructura del arnés del agente: contexto del proyecto, memoria, reparación de JSON, ajustes de muestreo por
familia de modelo, puntos de restauración (deshacer), procesos en segundo plano, lectura de documentos y cliente MCP."""
import os, re, json, time, uuid, shlex, shutil, zipfile, threading, subprocess, html
from . import paths, osys

NO_WINDOW = osys.NO_WINDOW
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".idea", ".vscode", "target", ".mypy_cache"}

# ---------------------------------------------------------------- contexto del proyecto
CONTEXT_FILES = ("AGENTS.md", "JAYTH.md", "CLAUDE.md", ".github/copilot-instructions.md", ".cursorrules")


def context_files(root, limit=6000):
    """Instrucciones que el proyecto deja para agentes (convenciones AGENTS.md / CLAUDE.md…)."""
    out, used = [], 0
    for name in CONTEXT_FILES:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                t = open(p, encoding="utf-8", errors="replace").read().strip()
            except OSError:
                continue
            t = t[: max(0, limit - used)]
            if t:
                out.append("### %s\n%s" % (name, t))
                used += len(t)
        if used >= limit:
            break
    return "\n\n".join(out)


def repo_map(root, max_entries=160, depth=3):
    """Arbol compacto de la carpeta (para que el modelo conozca la estructura sin gastar pasos)."""
    lines, count = [], [0]

    def walk(d, lvl):
        try:
            ents = sorted(os.scandir(d), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for e in ents:
            if count[0] >= max_entries:
                return
            if e.name in SKIP_DIRS or (e.name.startswith(".") and e.name not in (".github",)):
                continue
            count[0] += 1
            lines.append("  " * lvl + e.name + ("/" if e.is_dir() else ""))
            if e.is_dir() and lvl + 1 < depth:
                walk(e.path, lvl + 1)
    walk(root, 0)
    if count[0] >= max_entries:
        lines.append("… (más archivos; usa list_dir o search_files)")
    return "\n".join(lines)


# ---------------------------------------------------------------- memoria persistente
MEMORY = os.path.join(paths.DATA, "memory.md")


def memory_text(limit=4000):
    try:
        return open(MEMORY, encoding="utf-8").read().strip()[-limit:]
    except OSError:
        return ""


def remember(fact):
    os.makedirs(os.path.dirname(MEMORY), exist_ok=True)
    with open(MEMORY, "a", encoding="utf-8") as f:
        f.write("- %s (%s)\n" % (fact.strip().replace("\n", " "), time.strftime("%Y-%m-%d")))


# ---------------------------------------------------------------- JSON tolerante (modelos locales a veces se equivocan)
def repair_json(raw):
    """Intenta convertir argumentos casi-JSON en un dict: bloques ```json```, comas finales, saltos de linea sin escapar,
    comillas simples y llaves sin cerrar."""
    if isinstance(raw, dict):
        return raw
    s = str(raw or "").strip() or "{}"
    try:
        v = json.loads(s)
        if isinstance(v, dict):
            return v
    except ValueError:
        pass
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    s = re.sub(r",\s*([}\]])", r"\1", s)                       # comas finales
    out, in_str, esc, q = [], False, False, None                # escapar saltos de linea dentro de cadenas
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == q:
                in_str = False
            elif ch == "\n":
                out.append("\\n")
                continue
            elif ch == "\t":
                out.append("\\t")
                continue
        elif ch in "\"'":
            in_str, q = True, ch
        out.append(ch)
    s = "".join(out)
    for cand in (s, s + "}", s + '"}', s + "]}", s + '"]}'):   # llaves sin cerrar (respuesta cortada)
        try:
            v = json.loads(cand)
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    try:                                                       # comillas simples estilo Python
        import ast
        v = ast.literal_eval(s)
        if isinstance(v, dict):
            return v
    except Exception:
        pass
    raise ValueError("no es un objeto JSON válido")


# ---------------------------------------------------------------- muestreo recomendado por familia de modelo
PRESETS = [   # (patron, sin pensar, pensando) — valores publicados por cada laboratorio
    (r"qwen", dict(temperature=0.7, top_p=0.8, top_k=20, min_p=0.0), dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)),
    (r"deepseek", dict(temperature=0.6, top_p=0.95, top_k=40, min_p=0.0), dict(temperature=0.6, top_p=0.95, top_k=40, min_p=0.0)),
    (r"gemma", dict(temperature=1.0, top_p=0.95, top_k=64, min_p=0.0), dict(temperature=1.0, top_p=0.95, top_k=64, min_p=0.0)),
    (r"llama", dict(temperature=0.6, top_p=0.9, top_k=40, min_p=0.0), dict(temperature=0.6, top_p=0.9, top_k=40, min_p=0.0)),
    (r"mistral|devstral|magistral|ministral", dict(temperature=0.15, top_p=0.95, top_k=40, min_p=0.0), dict(temperature=0.7, top_p=0.95, top_k=40, min_p=0.0)),
    (r"gpt.?oss", dict(temperature=1.0, top_p=1.0, top_k=0, min_p=0.0), dict(temperature=1.0, top_p=1.0, top_k=0, min_p=0.0)),
    (r"phi", dict(temperature=0.7, top_p=0.95, top_k=40, min_p=0.0), dict(temperature=0.8, top_p=0.95, top_k=50, min_p=0.0)),
    (r"glm", dict(temperature=0.7, top_p=0.95, top_k=40, min_p=0.0), dict(temperature=0.6, top_p=0.95, top_k=40, min_p=0.0)),
]


def sampling_for(title, thinking):
    t = (title or "").lower()
    for pat, normal, think in PRESETS:
        if re.search(pat, t):
            return dict(think if thinking else normal)
    return None


# ---------------------------------------------------------------- puntos de restauracion (deshacer cambios del agente)
CK_DIR = os.path.join(paths.DATA, "checkpoints")


def snapshot(sid, cid, files):
    """Guarda el estado previo de los archivos que una accion va a cambiar."""
    d = os.path.join(CK_DIR, sid, cid)
    os.makedirs(d, exist_ok=True)
    meta = []
    for i, p in enumerate(files):
        p = os.path.normpath(p)
        entry = {"path": p, "existed": os.path.exists(p), "dir": os.path.isdir(p)}
        if entry["existed"] and not entry["dir"] and os.path.getsize(p) <= 50_000_000:
            shutil.copy2(p, os.path.join(d, "%d.bak" % i))
            entry["copy"] = "%d.bak" % i
        meta.append(entry)
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"files": meta, "ts": time.time()}, f)


def undo(sid, cid):
    """Restaura los archivos al estado anterior a la accion. Devuelve la lista de rutas restauradas."""
    d = os.path.join(CK_DIR, sid, cid)
    try:
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    done = []
    for e in meta["files"]:
        p = e["path"]
        if e.get("copy"):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copy2(os.path.join(d, e["copy"]), p)
            done.append(p)
        elif not e["existed"] and os.path.exists(p):
            (shutil.rmtree if os.path.isdir(p) else os.remove)(p)    # lo creo el agente: se quita
            done.append(p)
    shutil.rmtree(d, ignore_errors=True)
    return done


def has_snapshot(sid, cid):
    return os.path.isfile(os.path.join(CK_DIR, sid, cid, "meta.json"))


# ---------------------------------------------------------------- procesos en segundo plano (servidores de desarrollo, etc.)
BG = {}


def bg_start(command, cwd):
    from .tools import cmd_env
    pid = "bg_" + uuid.uuid4().hex[:6]
    p = subprocess.Popen(osys.shell_argv(command), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env=cmd_env(), **osys.popen_kwargs())
    rec = {"proc": p, "cmd": command, "lines": [], "started": time.time()}

    def reader():
        for b in iter(p.stdout.readline, b""):
            rec["lines"].append(b.decode("utf-8", "replace").rstrip())
            del rec["lines"][:-2000]
    threading.Thread(target=reader, daemon=True).start()
    BG[pid] = rec
    return pid


def bg_output(pid, last=80):
    r = BG.get(pid)
    if not r:
        return None
    state = "en ejecución" if r["proc"].poll() is None else "terminado (código %s)" % r["proc"].poll()
    return "[%s · %s · %ds]\n%s" % (pid, state, time.time() - r["started"], "\n".join(r["lines"][-last:]) or "(sin salida todavía)")


def bg_stop(pid):
    r = BG.get(pid)
    if not r:
        return False
    if r["proc"].poll() is None:
        osys.kill_tree(r["proc"].pid)
    return True


def bg_stop_all():
    for pid in list(BG):
        bg_stop(pid)


# ---------------------------------------------------------------- documentos (Word, Excel, PowerPoint, PDF)
def _xml_text(data, para_tag):
    t = re.sub(r"</%s>" % para_tag, "\n", data)
    t = re.sub(r"<w:tab/>|<a:tab/>", "\t", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)


def read_document(path, limit=60000):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".docm"):
        with zipfile.ZipFile(path) as z:
            return _xml_text(z.read("word/document.xml").decode("utf-8", "replace"), "w:p")[:limit]
    if ext in (".pptx",):
        with zipfile.ZipFile(path) as z:
            slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
            return "\n\n".join("--- Diapositiva %d ---\n%s" % (i + 1, _xml_text(z.read(n).decode("utf-8", "replace"), "a:p").strip())
                               for i, n in enumerate(slides))[:limit]
    if ext in (".xlsx", ".xlsm"):
        with zipfile.ZipFile(path) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                shared = [html.unescape(re.sub(r"<[^>]+>", "", si)) for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S)]
            out = []
            for n in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
                out.append("--- Hoja %s ---" % re.findall(r"\d+", n)[-1])
                for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(n).decode("utf-8", "replace"), re.S):
                    cells = []
                    for attrs, val in re.findall(r"<c([^>]*)>(?:.*?<v>(.*?)</v>)?.*?</c>", row, re.S):
                        if 't="s"' in attrs and val.isdigit() and int(val) < len(shared):
                            val = shared[int(val)]
                        cells.append(html.unescape(val or ""))
                    out.append("\t".join(cells))
                    if sum(len(x) for x in out) > limit:
                        return "\n".join(out)[:limit]
            return "\n".join(out)[:limit]
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("Para leer PDF hace falta el paquete pypdf (pip install pypdf).")
        r = PdfReader(path)
        return "\n\n".join("--- Página %d ---\n%s" % (i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(r.pages))[:limit]
    raise RuntimeError("Formato no soportado: %s (usa read_file para texto plano)" % ext)


# ---------------------------------------------------------------- conectores MCP (Model Context Protocol, transporte stdio)
class MCPServer:
    """Cliente minimo de MCP: arranca el servidor, lista sus herramientas y las llama (JSON-RPC por stdin/stdout)."""

    def __init__(self, name, command, args=(), env=None):
        self.name, self.command, self.args, self.env = name, command, list(args or []), dict(env or {})
        self.proc, self.tools, self.error = None, [], ""
        self._id, self._waiting, self._lock = 0, {}, threading.Lock()

    def start(self, timeout=25):
        env = dict(os.environ, **self.env)
        cmd = [self.command] + self.args
        if osys.WIN and not os.path.splitext(self.command)[1]:
            cmd = ["cmd", "/c"] + cmd               # npx, uvx… son .cmd en Windows
        elif not osys.WIN and not shutil.which(self.command) and not os.path.isabs(self.command):
            cmd = osys.shell_argv(" ".join(shlex.quote(c) for c in cmd))   # npx/uvx instalados con nvm/brew: PATH de la shell de login
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, **osys.popen_kwargs())
        threading.Thread(target=self._reader, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Jayth", "version": "0.1"}}, timeout)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = self.request("tools/list", {}, timeout).get("tools", [])
        return self.tools

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _reader(self):
        for line in iter(self.proc.stdout.readline, b""):
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            w = self._waiting.get(msg.get("id"))
            if w is not None:
                w["msg"] = msg
                w["ev"].set()

    def request(self, method, params, timeout=120):
        with self._lock:
            self._id += 1
            rid = self._id
        w = {"ev": threading.Event(), "msg": None}
        self._waiting[rid] = w
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        if not w["ev"].wait(timeout):
            self._waiting.pop(rid, None)
            raise TimeoutError("El conector %s no respondió a %s" % (self.name, method))
        self._waiting.pop(rid, None)
        if "error" in w["msg"]:
            raise RuntimeError(w["msg"]["error"].get("message", "error"))
        return w["msg"].get("result", {})

    def call(self, tool, arguments):
        res = self.request("tools/call", {"name": tool, "arguments": arguments})
        parts = []
        for c in res.get("content", []):
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            else:
                parts.append("[%s]" % c.get("type"))
        text = "\n".join(parts) or json.dumps(res.get("structuredContent", {}), ensure_ascii=False)
        if res.get("isError"):
            raise RuntimeError(text)
        return text

    def stop(self):
        if self.proc and self.proc.poll() is None:
            osys.kill_tree(self.proc.pid)


MCP = {}            # nombre -> MCPServer en marcha
_MCP_LOCK = threading.Lock()


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:28]


def mcp_sync(servers):
    """Arranca/para los conectores segun los ajustes. Devuelve {nombre: error o ''}."""
    want = {s["name"]: s for s in servers if s.get("enabled", True) and s.get("command")}
    status = {}
    with _MCP_LOCK:
        for n in list(MCP):
            if n not in want:
                MCP.pop(n).stop()
        for n, s in want.items():
            cur = MCP.get(n)
            if cur and cur.proc and cur.proc.poll() is None and (cur.command, cur.args) == (s["command"], list(s.get("args") or [])):
                status[n] = ""
                continue
            if cur:
                cur.stop()
            srv = MCPServer(n, s["command"], s.get("args"), s.get("env"))
            try:
                srv.start()
                MCP[n] = srv
                status[n] = ""
            except Exception as e:
                srv.stop()
                status[n] = str(e) or type(e).__name__
    return status


def mcp_schemas():
    out = []
    for n, srv in MCP.items():
        for t in srv.tools:
            out.append({"type": "function", "function": {"name": "mcp__%s__%s" % (_safe(n), _safe(t["name"])),
                                                         "description": ("[%s] " % n) + (t.get("description") or "")[:400],
                                                         "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}})
    return out


def mcp_resolve(fn_name):
    """'mcp__servidor__herramienta' -> (MCPServer, nombre real de la herramienta)."""
    m = re.match(r"mcp__(.+?)__(.+)$", fn_name)
    if not m:
        return None, None
    for n, srv in MCP.items():
        if _safe(n) == m.group(1):
            for t in srv.tools:
                if _safe(t["name"]) == m.group(2):
                    return srv, t["name"]
    return None, None


def mcp_stop_all():
    with _MCP_LOCK:
        for n in list(MCP):
            MCP.pop(n).stop()
