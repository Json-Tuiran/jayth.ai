# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Infraestructura del arnés del agente: contexto del proyecto, memoria, reparación de JSON, ajustes de muestreo por
familia de modelo, puntos de restauración (deshacer), procesos en segundo plano, lectura de documentos y cliente MCP."""
import os, re, json, time, uuid, shlex, shutil, zipfile, threading, subprocess, html
from . import paths, osys
from .i18n import tr

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


def memory_items():
    """Recuerdos guardados, uno por línea: [(texto, fecha)]."""
    out = []
    for line in memory_text(200000).splitlines():
        t = line.strip().lstrip("-*• ").strip()
        if not t:
            continue
        m = re.match(r"^(.*?)\s*\((\d{4}-\d{2}-\d{2})\)$", t)
        out.append((m.group(1), m.group(2)) if m else (t, ""))
    return out


def memory_save(items):
    os.makedirs(os.path.dirname(MEMORY), exist_ok=True)
    with open(MEMORY, "w", encoding="utf-8") as f:
        for text, date in items:
            if text.strip():
                f.write("- %s%s\n" % (text.strip().replace("\n", " "), " (%s)" % date if date else ""))


def forget(query):
    """Borra los recuerdos que contengan el texto dado. Devuelve los borrados."""
    q = query.strip().lower()
    items = memory_items()
    gone = [t for t, _ in items if q and q in t.lower()]
    if gone:
        memory_save([(t, d) for t, d in items if not (q in t.lower())])
    return gone


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
    # gpt-oss: lo de OpenAI (1.0, 1.0, sin top-k) más min-p 0.05 (lo de llama.cpp por defecto). Sin ningún recorte, al
    # rehacer un token que no encaja con el JSON de una llamada elegía entre todos los permitidos y se desbocaba («?……»)
    (r"gpt.?oss", dict(temperature=1.0, top_p=1.0, top_k=0, min_p=0.05), dict(temperature=1.0, top_p=1.0, top_k=0, min_p=0.05)),
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


def undo_file(sid, cids, path):
    """Devuelve un solo archivo a su estado de antes de la primera de esas acciones (en orden); las demás dejan de poder
    deshacerlo. Devuelve (ruta restaurada o None, ids de las acciones que ya no tienen nada que deshacer)."""
    key = os.path.normcase(os.path.normpath(path))
    first, emptied, seen = None, [], False
    for cid in cids:
        d = os.path.join(CK_DIR, sid, cid)
        try:
            meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        mine = [e for e in meta["files"] if os.path.normcase(os.path.normpath(e["path"])) == key]
        if not mine:
            continue
        if not seen:                               # el estado más antiguo: el de antes de la respuesta
            seen = True
            e = mine[0]
            p = e["path"]
            if e.get("copy"):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                shutil.copy2(os.path.join(d, e["copy"]), p)
                first = p
            elif not e["existed"]:
                if os.path.exists(p):
                    (shutil.rmtree if os.path.isdir(p) else os.remove)(p)
                first = p
        rest = [e for e in meta["files"] if e not in mine]
        if rest:
            meta["files"] = rest
            with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
        else:
            shutil.rmtree(d, ignore_errors=True)
            emptied.append(cid)
    return first, emptied


def snapshot_files(sid, cid):
    """Archivos que guarda la copia de una acción ({path, existed, copy…}); [] si ya no hay copia."""
    try:
        return json.load(open(os.path.join(CK_DIR, sid, cid, "meta.json"), encoding="utf-8")).get("files") or []
    except (OSError, ValueError):
        return []


def has_snapshot(sid, cid):
    return os.path.isfile(os.path.join(CK_DIR, sid, cid, "meta.json"))


# ---------------------------------------------------------------- procesos en segundo plano (servidores de desarrollo, etc.)
BG = {}


def bg_start(command, cwd):
    from .tools import cmd_env
    pid = "bg_" + uuid.uuid4().hex[:6]
    if osys.WIN:               # «ignorar Ctrl+C» se hereda de quien lanzó Jayth: sin esto el proceso no podría cerrarse con orden
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
        except Exception:
            pass
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
    code = r["proc"].poll()
    state = "en ejecución" if code is None else ("detenido" if r.get("stopped") else "terminado (código %s)" % code)
    return "[%s · %s · %ds]\n%s" % (pid, state, time.time() - r["started"], "\n".join(r["lines"][-last:]) or "(sin salida todavía)")


def bg_stop(pid, gentle=True, wait=5.0):
    """Detiene un proceso en segundo plano. Primero se lo pide con orden (Ctrl+C: un servidor cierra sus archivos y
    conexiones) y espera unos segundos; si no termina, lo cierra a la fuerza con los procesos que abrió. Devuelve False
    si no existe, o cómo acabó: "ended" (ya había terminado), "clean" (cerró él) o "forced"."""
    r = BG.get(pid)
    if not r:
        return False
    p = r["proc"]
    if p.poll() is not None:
        return "ended"
    r["stopped"] = True
    how = "forced"
    if gentle and osys.interrupt_tree(p.pid):
        try:
            p.wait(timeout=wait)
            how = "clean"
        except Exception:
            pass
    osys.kill_tree(p.pid)          # también tras un cierre limpio: por si quedó algún proceso hijo
    try:                           # que al consultarlo justo después ya conste como detenido (antes seguía «en ejecución»)
        p.wait(timeout=4)
    except Exception:
        pass
    r["how"] = how
    return how


def bg_stop_all():
    for pid in list(BG):
        bg_stop(pid, gentle=False)         # al cerrar Jayth no se espera a nadie


# ---------------------------------------------------------------- documentos (Word, Excel, PowerPoint, PDF)
def _xml_text(data, para_tag):
    t = re.sub(r"</%s>" % para_tag, "\n", data)
    t = re.sub(r"<w:tab/>|<a:tab/>", "\t", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)


def _docx_tables(x):
    """Las tablas de un documento de Word como filas «| a | b |» (si no, cada celda saldría en su línea y no se vería
    qué va con qué)."""
    def table(m):
        rows = []
        for tr in re.findall(r"<w:tr\b.*?</w:tr>", m.group(0), re.S):
            cells = [" ".join(re.sub(r"<[^>]+>", " ", re.sub(r"</w:p>", " ", tc)).split()).replace("|", "/")
                     for tc in re.findall(r"<w:tc\b.*?</w:tc>", tr, re.S)]
            rows.append("| " + " | ".join(cells) + " |")
            if len(rows) == 1:
                rows.append("|" + " --- |" * len(cells))
        return "<w:p>" + "\n".join(rows) + "</w:p>"
    return re.sub(r"<w:tbl>.*?</w:tbl>", table, x, flags=re.S)


def read_document(path, limit=60000):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".docm"):
        with zipfile.ZipFile(path) as z:
            return _xml_text(_docx_tables(z.read("word/document.xml").decode("utf-8", "replace")), "w:p")[:limit]
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
MCP_PROTOCOL = "2025-06-18"


class MCPError(RuntimeError):
    pass


class MCPAuthNeeded(MCPError):
    """El conector pide iniciar sesión con la cuenta del usuario (OAuth)."""

    def __init__(self, msg, www_auth=""):
        super().__init__(msg)
        self.www_auth = www_auth


class MCPServer:
    """Cliente de MCP por stdio: arranca el programa del conector, lista sus herramientas y las llama (JSON-RPC por lineas).
    Si el conector se cae, se vuelve a arrancar una vez al llamarlo; sus mensajes de error (stderr) se guardan para
    explicar por que fallo."""

    def __init__(self, name, command, args=(), env=None):
        self.name, self.command, self.args, self.env = name, command, list(args or []), dict(env or {})
        self.proc, self.tools, self.error = None, [], ""
        self._id, self._waiting, self._lock = 0, {}, threading.Lock()
        self._stderr = []

    def key(self):
        return ("stdio", self.command, tuple(self.args), tuple(sorted(self.env.items())))

    def account(self):
        return False                                # programa de este equipo: no actúa con una cuenta en internet

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout=40):
        env = dict(os.environ, **self.env)
        cmd = [self.command] + self.args
        if osys.WIN and not os.path.splitext(self.command)[1]:
            cmd = ["cmd", "/c"] + cmd               # npx, uvx… son .cmd en Windows
        elif not osys.WIN and not shutil.which(self.command) and not os.path.isabs(self.command):
            cmd = osys.shell_argv(" ".join(shlex.quote(c) for c in cmd))   # npx/uvx instalados con nvm/brew: PATH de la shell de login
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, **osys.popen_kwargs())
        except OSError as e:
            raise MCPError(tr("No se pudo ejecutar «%s»: %s. ¿Está instalado?") % (self.command, e.strerror or e))
        self._stderr = []
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._err_reader, daemon=True).start()
        self.request("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {}, "clientInfo": {"name": "Jayth", "version": "0.3"}}, timeout)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = list_all_tools(self)
        return self.tools

    def _send(self, obj):
        try:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except (OSError, ValueError):
            raise MCPError(self._died())

    def _died(self):
        tail = " | ".join(l for l in self._stderr[-4:] if l)[:400]
        return tr("El conector %s se cerró%s%s") % (self.name, (tr(" (código %s)") % self.proc.returncode) if self.proc and self.proc.poll() is not None else "",
                                                 (": " + tail) if tail else ".")

    def _reader(self):
        proc = self.proc
        for line in iter(proc.stdout.readline, b""):
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            w = self._waiting.get(msg.get("id"))
            if w is not None:
                w["msg"] = msg
                w["ev"].set()
        for w in list(self._waiting.values()):     # el proceso termino: despierta a quien esperaba
            w["ev"].set()

    def _err_reader(self):
        proc = self.proc
        for line in iter(proc.stderr.readline, b""):
            self._stderr.append(line.decode("utf-8", "replace").strip())
            del self._stderr[:-30]

    def request(self, method, params, timeout=120):
        with self._lock:
            self._id += 1
            rid = self._id
        w = {"ev": threading.Event(), "msg": None}
        self._waiting[rid] = w
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            end = time.time() + timeout
            while not w["ev"].wait(0.25):
                if not self.alive():
                    raise MCPError(self._died())
                if time.time() > end:
                    raise MCPError(tr("El conector %s no respondió a %s en %d s.") % (self.name, method, timeout))
        finally:
            self._waiting.pop(rid, None)
        if w["msg"] is None:
            raise MCPError(self._died())
        if "error" in w["msg"]:
            raise MCPError(w["msg"]["error"].get("message", "error"))
        return w["msg"].get("result", {})

    def call(self, tool, arguments):
        if not self.alive():                       # se cayo: un reintento arrancandolo de nuevo
            self.stop()
            self.start()
        return tool_result(self.request("tools/call", {"name": tool, "arguments": arguments}, timeout=300))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            osys.kill_tree(self.proc.pid)


class MCPHttpServer:
    """Cliente de MCP remoto por HTTP («streamable HTTP»): POST con JSON-RPC; la respuesta llega como JSON o como
    flujo SSE. Admite cabeceras propias (p. ej. Authorization: Bearer …) y la sesion Mcp-Session-Id."""

    def __init__(self, name, url, headers=None, auth=None):
        self.name, self.url, self.headers, self.auth = name, url, dict(headers or {}), auth
        self.tools, self.error, self.session = [], "", None
        self._id, self._lock = 0, threading.Lock()

    def key(self):
        return ("http", self.url, tuple(sorted(self.headers.items())), self.auth)

    def alive(self):
        return True

    def account(self):
        """¿Actúa con la cuenta del usuario en ese servicio (sesión iniciada o clave propia)?"""
        return self.auth == "oauth" or any(k.lower() == "authorization" for k in self.headers)

    def _post(self, obj, timeout, retried=False):
        import urllib.request, urllib.error
        from . import oauth
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": MCP_PROTOCOL}
        h.update(self.headers)
        if self.auth == "oauth":
            tok = oauth.token(self.url, force_refresh=retried)
            if not tok:
                raise MCPAuthNeeded(tr("Hay que iniciar sesión en %s con tu cuenta (Ajustes › Herramientas › Conectores).") % self.name)
            h["Authorization"] = "Bearer " + tok
        if self.session:
            h["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(obj).encode("utf-8"), headers=h, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            body = e.read(500).decode("utf-8", "replace")
            if e.code == 401 and self.auth == "oauth" and not retried:      # caducó: se renueva y se reintenta una vez
                return self._post(obj, timeout, True)
            if e.code == 401 and (self.auth == "oauth" or not self.account()):
                raise MCPAuthNeeded(tr("%s pide iniciar sesión con tu cuenta.") % self.name, e.headers.get("WWW-Authenticate") or "")
            if e.code in (401, 403):
                raise MCPError(tr("El conector %s rechazó la conexión (HTTP %d): revisa la clave o el token en sus cabeceras.") % (self.name, e.code))
            raise MCPError(tr("El conector %s respondió HTTP %d: %s") % (self.name, e.code, body[:200]))
        except Exception as e:
            raise MCPError(tr("No se pudo conectar con %s (%s): %s") % (self.name, self.url, getattr(e, "reason", e)))
        self.session = r.headers.get("Mcp-Session-Id") or self.session
        if obj.get("id") is None:
            return None
        ctype = r.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:           # flujo SSE: se lee hasta el mensaje con nuestro id
            for line in r:
                line = line.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if msg.get("id") == obj["id"]:
                        return msg
            raise MCPError(tr("El conector %s cerró la respuesta sin contestar.") % self.name)
        raw = r.read()
        return json.loads(raw.decode("utf-8")) if raw.strip() else {}

    def request(self, method, params, timeout=120):
        with self._lock:
            self._id += 1
            rid = self._id
        msg = self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}, timeout)
        if "error" in (msg or {}):
            raise MCPError(msg["error"].get("message", "error"))
        return (msg or {}).get("result", {})

    def start(self, timeout=40):
        self.session = None
        self.request("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {}, "clientInfo": {"name": "Jayth", "version": "0.3"}}, timeout)
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout)
        self.tools = list_all_tools(self)
        return self.tools

    def call(self, tool, arguments):
        try:
            return tool_result(self.request("tools/call", {"name": tool, "arguments": arguments}, timeout=300))
        except MCPError as e:
            if "404" in str(e) and self.session:   # la sesion caduco en el servidor: se abre otra y se reintenta
                self.start()
                return tool_result(self.request("tools/call", {"name": tool, "arguments": arguments}, timeout=300))
            raise

    def stop(self):
        if self.session:
            try:
                import urllib.request
                h = dict(self.headers, **{"Mcp-Session-Id": self.session})
                if self.auth == "oauth":
                    from . import oauth
                    tok = oauth.token(self.url)
                    if tok:
                        h["Authorization"] = "Bearer " + tok
                urllib.request.urlopen(urllib.request.Request(self.url, headers=h, method="DELETE"), timeout=3)
            except Exception:
                pass
        self.session = None


def list_all_tools(srv, limit=500):
    """tools/list con paginacion (nextCursor)."""
    tools, cursor = [], None
    for _ in range(20):
        res = srv.request("tools/list", {"cursor": cursor} if cursor else {}, 40)
        tools += res.get("tools", [])
        cursor = res.get("nextCursor")
        if not cursor or len(tools) >= limit:
            break
    return tools


def tool_result(res):
    """Resultado de tools/call para el modelo: texto, y la primera imagen como imagen (si el modelo tiene vision la ve)."""
    import base64
    parts, image = [], None
    for c in res.get("content", []):
        t = c.get("type")
        if t == "text":
            parts.append(c.get("text", ""))
        elif t == "image" and c.get("data"):
            if image is None:
                try:
                    image = base64.b64decode(c["data"])
                except ValueError:
                    pass
            parts.append("[imagen %s]" % c.get("mimeType", ""))
        elif t == "resource":
            r = c.get("resource") or {}
            parts.append(r.get("text") or "[recurso %s]" % r.get("uri", ""))
        elif t == "resource_link":
            parts.append("[enlace a recurso: %s %s]" % (c.get("name", ""), c.get("uri", "")))
        else:
            parts.append("[%s]" % t)
    text = "\n".join(p for p in parts if p)
    if not text and res.get("structuredContent") is not None:
        text = json.dumps(res["structuredContent"], ensure_ascii=False)
    if res.get("isError"):
        raise MCPError(text or "El conector devolvió un error sin detalles.")
    if text.lstrip()[:1] in ("{", "["):
        try:
            j = json.loads(text)
        except ValueError:
            j = None
        # algunos conectores (p. ej. el de Blender) informan del fallo dentro de un JSON {"status": "error", "message": …}
        if isinstance(j, dict) and str(j.get("status", "")).lower() == "error":
            raise MCPError(str(j.get("message") or j.get("error") or text))
        if j is not None and len(text) > 300:
            # JSON compacto: mismo contenido sin sangrias ni saltos (ahorra mucho contexto a los modelos locales)
            text = json.dumps(j, ensure_ascii=False, separators=(",", ":"))
    if image is not None:
        return {"text": text or "(imagen)", "image": image}
    return text or "(sin contenido)"


def make_server(s):
    """Conector a partir de sus ajustes: local (command/args/env) o remoto (url/headers)."""
    if s.get("url"):
        return MCPHttpServer(s["name"], s["url"].strip(), s.get("headers"), s.get("auth"))
    return MCPServer(s["name"], s["command"], s.get("args"), s.get("env"))


MCP = {}            # nombre -> MCPServer en marcha
_MCP_LOCK = threading.Lock()


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s)[:28]


def mcp_sync(servers):
    """Arranca/para los conectores segun los ajustes. Devuelve {nombre: error o ''}."""
    want = {s["name"]: s for s in servers if s.get("enabled", True) and (s.get("command") or s.get("url"))}
    status = {}
    with _MCP_LOCK:
        for n in list(MCP):
            if n not in want:
                MCP.pop(n).stop()
        for n, s in want.items():
            cur = MCP.get(n)
            srv = make_server(s)
            if cur and cur.alive() and cur.key() == srv.key():
                status[n] = ""
                continue
            if cur:
                cur.stop()
                MCP.pop(n, None)
            try:
                srv.start()
                MCP[n] = srv
                status[n] = ""
            except Exception as e:
                srv.stop()
                status[n] = str(e) or type(e).__name__
    MCP_STATUS.clear()
    MCP_STATUS.update(status)
    return status


MCP_STATUS = {}     # nombre -> '' (conectado) o el error del ultimo intento


_NAMES = {}         # nombre para el modelo -> (nombre del conector, nombre real de la herramienta)


def _fn_names():
    """Nombres unicos 'mcp__conector__herramienta' de hasta 64 caracteres (limite de la API). Si al recortar dos
    herramientas quedaran iguales (p. ej. x_summary y x_summary_for_cli), se distinguen con un sufijo estable."""
    import hashlib
    out, used = {}, set()
    for n, srv in MCP.items():
        sv = re.sub(r"[^A-Za-z0-9_-]+", "_", n)[:16]
        room = 64 - len("mcp____") - len(sv)
        for t in srv.tools:
            tn = re.sub(r"[^A-Za-z0-9_-]+", "_", t["name"])
            fn = "mcp__%s__%s" % (sv, tn[:room])
            if fn in used:
                h = hashlib.sha1(t["name"].encode("utf-8")).hexdigest()[:6]
                fn = "mcp__%s__%s_%s" % (sv, tn[:room - 7], h)
            used.add(fn)
            out[fn] = (n, t)
    return out


def mcp_schemas():
    out = []
    _NAMES.clear()
    for fn, (n, t) in _fn_names().items():
        _NAMES[fn] = (n, t["name"])
        out.append({"type": "function", "function": {"name": fn, "description": ("[%s] " % n) + (t.get("description") or "")[:600],
                                                     "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}})
    return out


def mcp_resolve(fn_name):
    """'mcp__conector__herramienta' -> (servidor, nombre real de la herramienta)."""
    hit = _NAMES.get(fn_name)
    if hit is None:
        hit = next(((n, t["name"]) for fn, (n, t) in _fn_names().items() if fn == fn_name), None)
    if hit is None or hit[0] not in MCP:
        return None, None
    return MCP[hit[0]], hit[1]


def mcp_stop_all():
    with _MCP_LOCK:
        for n in list(MCP):
            MCP.pop(n).stop()
