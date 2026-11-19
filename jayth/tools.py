"""Herramientas que el agente puede usar. Solo biblioteca estandar de Python (Windows)."""
import os, re, sys, json, time, html, struct, zlib, ctypes, subprocess, threading, fnmatch, base64
import urllib.request, urllib.parse
from ctypes import wintypes


class ToolError(Exception):
    """Error 'normal' de una herramienta: se le devuelve al modelo como texto."""


class Abort(Exception):
    """Aborta toda la ejecucion del agente (failsafe del raton)."""


MAX_OUT = 10000
TOOLS = {}
CATEGORIES = {"read": "Lectura", "write": "Escritura", "exec": "Ejecución", "net": "Red", "control": "Control del PC",
              "agent": "Agente", "mcp": "Conector"}
WRITE_TOOLS = {"write_file", "edit_file", "multi_edit", "move_path", "delete_path"}   # crean punto de restauracion


def clip(s, n=MAX_OUT):
    if len(s) <= n:
        return s
    h = n * 2 // 3
    t = n - h
    return s[:h] + "\n...[recortado %d caracteres]...\n" % (len(s) - n) + s[-t:]


class Ctx:
    def __init__(self, workspace, stop_event, images_dir, max_out=MAX_OUT, extras=None):
        self.extras = extras or {}
        self.workspace = workspace
        self.stop = stop_event
        self.images_dir = images_dir
        self.max_out = max_out
        self.scale = None  # factor captura -> pantalla real
        self.img_w = None

    def path(self, p):
        p = os.path.expandvars(os.path.expanduser(str(p)))
        if not os.path.isabs(p):
            p = os.path.join(self.workspace, p)
        return os.path.normpath(p)


def S(desc):
    return {"type": "string", "description": desc}


def I(desc):
    return {"type": "integer", "description": desc}


def B(desc):
    return {"type": "boolean", "description": desc}


def tool(name, category, desc, params, required=()):
    def deco(fn):
        TOOLS[name] = dict(name=name, category=category, description=desc,
                           parameters={"type": "object", "properties": params, "required": list(required)}, fn=fn)
        return fn
    return deco


def schemas(allowed_categories=None):
    out = []
    for t in TOOLS.values():
        if allowed_categories is not None and t["category"] not in allowed_categories:
            continue
        out.append({"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}})
    return out


# ---------------------------------------------------------------- seguridad
DANGEROUS_CMD = [r"\bRemove-Item\b", r"(^|[\s;|&(])(del|erase|rmdir|rd|rm|ri)\s", r"\bformat(-volume)?\b", r"\bdiskpart\b",
                 r"\bshutdown\b", r"\b(Stop|Restart)-Computer\b", r"\breg(\.exe)?\s+(delete|add|import)\b",
                 r"\bSet-ItemProperty\b.*HK(LM|CU)", r"\bnet\s+user\b", r"\bInvoke-Expression\b|(^|[\s;|&(])iex(\s|$)",
                 r"\bbcdedit\b", r"\bcipher\b.*/w", r"\b(takeown|icacls)\b", r"\bSet-ExecutionPolicy\b",
                 r"-Verb\s+RunAs", r"\bpip3?\s+uninstall\b", r"\bSet-MpPreference\b|\bDisable-\w+", r"\bschtasks\b.*/create",
                 r"\bsc(\.exe)?\s+(delete|config|create|stop)\b", r"\btaskkill\b", r"\bStop-Process\b", r"\bClear-Content\b",
                 r"\bmove-item\b.*\\windows", r"\bwinget\s+(uninstall|install)\b", r"\bchoco\s+(uninstall|install)\b"]
PROTECTED_PATHS = ["c:\\windows", "c:\\program files", "c:\\program files (x86)", "c:\\programdata",
                   os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu").lower()]


def is_dangerous(name, args, ctx):
    """Acciones que siempre piden confirmacion, incluso en modo automatico."""
    try:
        if name == "run_command":
            cmd = str(args.get("command", ""))
            return any(re.search(p, cmd, re.I) for p in DANGEROUS_CMD)
        if name == "delete_path":
            return True                         # borrar siempre se confirma
        if name in ("write_file", "edit_file", "multi_edit", "download_file", "move_path"):
            ps = [args.get("path") or args.get("dest") or args.get("source") or "x"] + ([args["dest"]] if args.get("dest") else [])
            return any(ctx.path(p).lower().startswith(x) for p in ps for x in PROTECTED_PATHS)
        if name == "open_target":
            return bool(args.get("args"))
    except Exception:
        return True
    return False


# ---------------------------------------------------------------- archivos
@tool("read_file", "read", "Lee un archivo de texto y devuelve las líneas numeradas.",
      {"path": S("Ruta del archivo"), "offset": I("Línea inicial (por defecto 1)"), "limit": I("Máximo de líneas (por defecto 400)")}, ["path"])
def read_file(a, ctx):
    p = ctx.path(a["path"])
    if not os.path.isfile(p):
        raise ToolError("No existe el archivo: " + p)
    with open(p, "rb") as f:
        raw = f.read(5_000_000)
    if b"\0" in raw[:4096]:
        raise ToolError("Parece un archivo binario (%d bytes)." % os.path.getsize(p))
    lines = raw.decode("utf-8", errors="replace").splitlines()
    off = max(1, int(a.get("offset") or 1))
    lim = max(1, int(a.get("limit") or 400))
    seg = lines[off - 1: off - 1 + lim]
    out = "\n".join("%d\t%s" % (off + i, l) for i, l in enumerate(seg))
    rest = len(lines) - (off - 1 + lim)
    if rest > 0:
        out += "\n...[%d líneas más; usa offset=%d]" % (rest, off + lim)
    return out or "(archivo vacío)"


@tool("write_file", "write", "Crea o sobrescribe un archivo de texto (crea las carpetas necesarias).",
      {"path": S("Ruta del archivo"), "content": S("Contenido completo")}, ["path", "content"])
def write_file(a, ctx):
    p = ctx.path(a["path"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = str(a.get("content", ""))
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    return "Escrito %s (%d bytes)" % (p, len(data.encode("utf-8")))


def _apply_edit(text, old, new, replace_all=False):
    """Reemplazo exacto; si falla, tolera diferencias de espacios al final de linea y saltos CRLF (frecuentes en modelos locales)."""
    n = text.count(old)
    if n == 0:
        norm = lambda s: "\n".join(l.rstrip() for l in s.replace("\r\n", "\n").split("\n"))
        nt, no = norm(text), norm(old)
        k = nt.count(no) if no.strip() else 0
        if k == 1 or (k > 1 and replace_all):
            crlf = "\r\n" in text
            out = nt.replace(no, new.replace("\r\n", "\n")) if replace_all else nt.replace(no, new.replace("\r\n", "\n"), 1)
            return (out.replace("\n", "\r\n") if crlf else out), k
        import difflib
        first = old.strip().splitlines()[0] if old.strip() else ""
        near = difflib.get_close_matches(first.strip(), [l.strip() for l in text.splitlines()], n=2, cutoff=0.6)
        hint = (" Líneas parecidas en el archivo: %s" % " | ".join(near)) if near else ""
        raise ToolError("No se encontró el texto 'old'. Vuelve a leer el archivo (read_file) y copia el fragmento exacto." + hint)
    if n > 1 and not replace_all:
        raise ToolError("'old' aparece %d veces; añade líneas de contexto para que sea único, o usa replace_all." % n)
    return (text.replace(old, new) if replace_all else text.replace(old, new, 1)), (n if replace_all else 1)


def _read_text(p):
    if not os.path.isfile(p):
        raise ToolError("No existe el archivo: " + p)
    with open(p, "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _write_text(p, text):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


@tool("edit_file", "write", "Reemplaza un fragmento de un archivo. 'old' debe aparecer una vez (añade contexto) salvo replace_all.",
      {"path": S("Ruta del archivo"), "old": S("Texto a reemplazar (cópialo del archivo)"), "new": S("Texto nuevo"), "replace_all": B("Reemplazar todas las apariciones")},
      ["path", "old", "new"])
def edit_file(a, ctx):
    p = ctx.path(a["path"])
    text, n = _apply_edit(_read_text(p), str(a["old"]), str(a["new"]), bool(a.get("replace_all")))
    _write_text(p, text)
    return "Editado %s (%d reemplazo%s)" % (p, n, "s" if n > 1 else "")


@tool("multi_edit", "write", "Varios reemplazos en un mismo archivo de una vez (todos o ninguno). Más eficiente que varios edit_file.",
      {"path": S("Ruta del archivo"), "edits": {"type": "array", "description": "Lista de {old, new, replace_all}",
                                               "items": {"type": "object", "properties": {"old": S("Texto a reemplazar"), "new": S("Texto nuevo"),
                                                                                          "replace_all": B("Todas las apariciones")}, "required": ["old", "new"]}}},
      ["path", "edits"])
def multi_edit(a, ctx):
    p = ctx.path(a["path"])
    text = _read_text(p)
    edits = a.get("edits") or []
    if isinstance(edits, str):
        edits = json.loads(edits)
    total = 0
    for i, e in enumerate(edits, 1):
        try:
            text, n = _apply_edit(text, str(e["old"]), str(e["new"]), bool(e.get("replace_all")))
        except ToolError as err:
            raise ToolError("Edición %d de %d: %s (no se aplicó ningún cambio)" % (i, len(edits), err))
        total += n
    _write_text(p, text)
    return "Editado %s (%d ediciones, %d reemplazos)" % (p, len(edits), total)


@tool("move_path", "write", "Mueve o renombra un archivo o carpeta.", {"source": S("Ruta actual"), "dest": S("Ruta nueva")}, ["source", "dest"])
def move_path(a, ctx):
    src, dst = ctx.path(a["source"]), ctx.path(a["dest"])
    if not os.path.exists(src):
        raise ToolError("No existe: " + src)
    if os.path.exists(dst):
        raise ToolError("Ya existe el destino: " + dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    import shutil
    shutil.move(src, dst)
    return "Movido %s -> %s" % (src, dst)


@tool("delete_path", "write", "Envía un archivo o carpeta a la papelera de reciclaje (se puede recuperar).", {"path": S("Ruta a borrar")}, ["path"])
def delete_path(a, ctx):
    p = ctx.path(a["path"])
    if not os.path.exists(p):
        raise ToolError("No existe: " + p)
    ps = "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::%s('%s','OnlyErrorDialogs','SendToRecycleBin')" % (
        "DeleteDirectory" if os.path.isdir(p) else "DeleteFile", p.replace("'", "''"))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=0x08000000)
    if os.path.exists(p):
        raise ToolError("No se pudo enviar a la papelera: " + p)
    return "Enviado a la papelera: " + p


@tool("list_dir", "read", "Lista el contenido de una carpeta.",
      {"path": S("Carpeta (por defecto la de trabajo)"), "depth": I("Profundidad 1-4 (por defecto 1)")})
def list_dir(a, ctx):
    p = ctx.path(a.get("path") or ".")
    if not os.path.isdir(p):
        raise ToolError("No existe la carpeta: " + p)
    depth = min(max(int(a.get("depth") or 1), 1), 4)
    out, cnt = [p], [0]

    def walk(d, lvl):
        try:
            ents = sorted(os.scandir(d), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception as e:
            out.append("  " * lvl + "[sin acceso: %s]" % e)
            return
        for e in ents:
            if cnt[0] >= 300:
                return
            cnt[0] += 1
            if e.is_dir():
                out.append("  " * lvl + e.name + "\\")
                if lvl < depth:
                    walk(e.path, lvl + 1)
            else:
                try:
                    sz = e.stat().st_size
                except Exception:
                    sz = 0
                out.append("  " * lvl + "%s  (%s)" % (e.name, _human(sz)))
    walk(p, 1)
    if cnt[0] >= 300:
        out.append("...[lista truncada a 300 entradas]")
    return "\n".join(out)


def _human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%d %s" % (n, u) if u == "B" else "%.1f %s" % (n, u)
        n /= 1024


@tool("search_files", "read", "Busca texto (regex) dentro de archivos, o lista archivos por patrón glob si no das 'pattern'.",
      {"pattern": S("Expresión regular a buscar (opcional)"), "path": S("Carpeta base"), "glob": S("Filtro de nombre, ej. *.py"), "max_results": I("Máximo de resultados (50)")})
def search_files(a, ctx):
    base = ctx.path(a.get("path") or ".")
    pat = re.compile(a["pattern"], re.I) if a.get("pattern") else None
    gl = a.get("glob") or "*"
    mx = int(a.get("max_results") or 50)
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    res = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip]
        for fn in files:
            if not fnmatch.fnmatch(fn, gl):
                continue
            fp = os.path.join(root, fn)
            if pat is None:
                res.append(fp)
            else:
                try:
                    if os.path.getsize(fp) > 2_000_000:
                        continue
                    with open(fp, "r", encoding="utf-8", errors="strict") as f:
                        for i, line in enumerate(f, 1):
                            if pat.search(line):
                                res.append("%s:%d: %s" % (fp, i, line.strip()[:200]))
                                if len(res) >= mx:
                                    break
                except Exception:
                    continue
            if len(res) >= mx:
                return "\n".join(res) + "\n...[máximo alcanzado]"
    return "\n".join(res) or "Sin resultados."


# ---------------------------------------------------------------- ejecucion
def _kill_tree(pid):
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=0x08000000)
    except Exception:
        pass


@tool("run_command", "exec", "Ejecuta un comando de PowerShell en la carpeta de trabajo y devuelve su salida. Para scripts: `python archivo.py`. "
      "Con background=true lo deja corriendo (servidores, vigilantes) y devuelve un id para command_output/stop_command.",
      {"command": S("Comando o script de PowerShell"), "timeout": I("Segundos máximos (por defecto 60, máx. 900)"), "cwd": S("Carpeta donde ejecutar (opcional)"),
       "background": B("Dejarlo corriendo en segundo plano")}, ["command"])
def run_command(a, ctx):
    cmd = str(a["command"])
    timeout = min(max(int(a.get("timeout") or (ctx.extras or {}).get("command_timeout") or 60), 1), 900)
    cwd = ctx.path(a["cwd"]) if a.get("cwd") else ctx.workspace
    os.makedirs(cwd, exist_ok=True)
    if a.get("background"):
        from . import harness
        pid = harness.bg_start(cmd, cwd)
        time.sleep(2.5)
        return "Iniciado en segundo plano con id %s.\n%s" % (pid, harness.bg_output(pid, 30))
    prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';"
    enc = base64.b64encode((prefix + cmd).encode("utf-16-le")).decode()
    p = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                         cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000)
    chunks = []

    def reader():
        for b in iter(lambda: p.stdout.read(4096), b""):
            chunks.append(b)
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    t0, why = time.time(), None
    while p.poll() is None:
        if ctx.stop.is_set():
            why = "cancelado por el usuario"
            break
        if time.time() - t0 > timeout:
            why = "tiempo agotado (%ds)" % timeout
            break
        time.sleep(0.1)
    if why:
        _kill_tree(p.pid)
    th.join(2)
    out = b"".join(chunks).decode("utf-8", errors="replace").strip()
    out = clip(out, ctx.max_out)
    if why:
        return (out + "\n" if out else "") + "[Proceso terminado: %s]" % why
    return (out or "(sin salida)") + "\n[código de salida %d]" % p.returncode


@tool("open_target", "exec", "Abre un programa, archivo, carpeta o URL con la aplicación predeterminada de Windows (no espera a que termine).",
      {"target": S("Ruta del programa/archivo, o URL"), "args": S("Argumentos (opcional, solo para programas)")}, ["target"])
def open_target(a, ctx):
    t = str(a["target"])
    if re.match(r"^[a-z]+://", t, re.I):
        os.startfile(t)
        return "Abierto: " + t
    if a.get("args"):
        subprocess.Popen('start "" "%s" %s' % (t, a["args"]), shell=True, cwd=ctx.workspace)
    else:
        try:
            os.startfile(ctx.path(t) if os.path.exists(ctx.path(t)) else t)
        except OSError:
            subprocess.Popen('start "" "%s"' % t, shell=True, cwd=ctx.workspace)
    return "Abierto: " + t


@tool("wait", "read", "Espera unos segundos (por ejemplo a que cargue una ventana).", {"seconds": I("Segundos (1-30)")}, ["seconds"])
def wait(a, ctx):
    s = min(max(float(a.get("seconds") or 1), 0.1), 30)
    end = time.time() + s
    while time.time() < end and not ctx.stop.is_set():
        time.sleep(0.1)
    return "Esperé %.1fs" % s


# ---------------------------------------------------------------- web
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "es,en;q=0.8"}


def html_to_text(h):
    h = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|section|article|ul|ol|table)>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t\r\f\v]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n\n", h)
    return h.strip()


def _http_get(url, timeout=20, data=None, max_bytes=2_500_000):
    req = urllib.request.Request(url, data=data, headers=UA)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        raise ToolError("No se pudo acceder (¿sin conexión?): %s" % e)
    raw = r.read(max_bytes)
    ctype = r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype)
    return raw, ctype, (m.group(1) if m else "utf-8"), r.geturl()


@tool("web_fetch", "net", "Descarga una página web y devuelve su texto (requiere internet).",
      {"url": S("URL completa"), "max_chars": I("Máximo de caracteres (por defecto 6000)")}, ["url"])
def web_fetch(a, ctx):
    raw, ctype, cs, final = _http_get(a["url"])
    if not re.search(r"text|json|xml|html", ctype, re.I):
        return "Contenido no textual (%s, %d bytes). Usa download_file para guardarlo." % (ctype, len(raw))
    try:
        txt = raw.decode(cs, errors="replace")
    except LookupError:
        txt = raw.decode("utf-8", errors="replace")
    if "html" in ctype.lower() or txt.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        txt = html_to_text(txt)
    return clip(txt, int(a.get("max_chars") or 6000))


def _search_brave(q, mx, key):
    req = urllib.request.Request("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "count": mx}),
                                 headers={"Accept": "application/json", "X-Subscription-Token": key})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
    except Exception as e:
        raise ToolError("Brave Search falló: %s" % e)
    res = (d.get("web") or {}).get("results") or []
    return "\n".join("%d. %s\n   %s\n   %s" % (i, r.get("title", ""), r.get("url", ""), html_to_text(r.get("description", ""))) for i, r in enumerate(res[:mx], 1))


def _search_searxng(q, mx, base):
    """SearXNG: buscador libre que se puede alojar en casa (formato JSON activado)."""
    url = base.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": q, "format": "json"})
    raw, _, _, _ = _http_get(url)
    try:
        res = json.loads(raw.decode("utf-8")).get("results", [])
    except ValueError:
        raise ToolError("SearXNG no devolvió JSON: activa 'json' en search.formats de su configuración.")
    return "\n".join("%d. %s\n   %s\n   %s" % (i, r.get("title", ""), r.get("url", ""), _strip(r.get("content", ""))) for i, r in enumerate(res[:mx], 1))


def _strip(s):
    return html_to_text(s or "")


def _search_wikipedia(q, mx):
    out = []
    for lang in ("es", "en"):
        url = "https://%s.wikipedia.org/w/api.php?" % lang + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": mx})
        raw, _, _, _ = _http_get(url)
        for r in json.loads(raw.decode("utf-8")).get("query", {}).get("search", []):
            out.append("%d. %s (Wikipedia %s)\n   https://%s.wikipedia.org/wiki/%s\n   %s" % (
                len(out) + 1, r["title"], lang, lang, urllib.parse.quote(r["title"].replace(" ", "_")), html_to_text(r["snippet"])))
        if len(out) >= mx:
            break
    return "\n".join(out[:mx])


@tool("web_search", "net", "Busca en la web y devuelve títulos, enlaces y resúmenes (requiere internet).",
      {"query": S("Texto de búsqueda"), "max_results": I("Resultados (por defecto 6)")}, ["query"])
def web_search(a, ctx):
    mx = int(a.get("max_results") or 6)
    ex = ctx.extras or {}
    prov = ex.get("search_provider", "auto")
    if prov == "searxng" and ex.get("searxng_url"):
        return _search_searxng(a["query"], mx, ex["searxng_url"]) or "Sin resultados."
    key = ex.get("brave_key")
    if key and prov in ("auto", "brave"):
        return _search_brave(a["query"], mx, key) or "Sin resultados."
    raw, _, _, _ = _http_get("https://html.duckduckgo.com/html/", data=urllib.parse.urlencode({"q": a["query"]}).encode())
    page = raw.decode("utf-8", errors="replace")
    if "anomaly" in page and "result__a" not in page:
        # DuckDuckGo pide un captcha a clientes automaticos: no se salta. Alternativa legitima: API de Wikipedia.
        wiki = _search_wikipedia(a["query"], mx)
        note = ("[Aviso: DuckDuckGo bloquea la búsqueda automática, así que estos resultados son solo de Wikipedia. "
                "Para buscar en toda la web, el usuario puede añadir una clave de Brave Search en Ajustes; "
                "o usa web_fetch con una URL concreta.]\n")
        return note + (wiki or "Sin resultados en Wikipedia.")
    out = []
    for blk in page.split('class="result__a"')[1:]:
        m = re.search(r'href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not m:
            continue
        link = html.unescape(m.group(1))
        q = urllib.parse.urlparse(link)
        if "uddg" in q.query:
            link = urllib.parse.parse_qs(q.query)["uddg"][0]
        title = html_to_text(m.group(2))
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', blk, re.S)
        out.append("%d. %s\n   %s\n   %s" % (len(out) + 1, title, link, html_to_text(sn.group(1)) if sn else ""))
        if len(out) >= mx:
            break
    return "\n".join(out) or "Sin resultados."


@tool("download_file", "net", "Descarga un archivo de internet a disco.",
      {"url": S("URL del archivo"), "dest": S("Ruta destino (por defecto carpeta 'descargas' de trabajo)")}, ["url"])
def download_file(a, ctx):
    url = a["url"]
    name = os.path.basename(urllib.parse.urlparse(url).path) or "descarga.bin"
    dest = ctx.path(a.get("dest") or os.path.join("descargas", name))
    if os.path.isdir(dest):
        dest = os.path.join(dest, name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
    except Exception as e:
        raise ToolError("No se pudo descargar (¿sin conexión?): %s" % e)
    total = 0
    with open(dest, "wb") as f:
        while True:
            if ctx.stop.is_set():
                raise ToolError("Descarga cancelada")
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            total += len(b)
    return "Descargado %s (%s)" % (dest, _human(total))


# ---------------------------------------------------------------- control del ordenador (ctypes)
user32 = gdi32 = None
if sys.platform == "win32":
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    V = ctypes.c_void_p
    user32.GetDC.restype = V
    user32.GetDC.argtypes = [V]
    user32.ReleaseDC.argtypes = [V, V]
    gdi32.CreateCompatibleDC.restype = V
    gdi32.CreateCompatibleDC.argtypes = [V]
    gdi32.CreateCompatibleBitmap.restype = V
    gdi32.CreateCompatibleBitmap.argtypes = [V, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = V
    gdi32.SelectObject.argtypes = [V, V]
    gdi32.SetStretchBltMode.argtypes = [V, ctypes.c_int]
    gdi32.StretchBlt.argtypes = [V, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, V, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.GetDIBits.argtypes = [V, V, wintypes.UINT, wintypes.UINT, V, V, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [V]
    gdi32.DeleteDC.argtypes = [V]

ULONG_PTR = ctypes.c_size_t


class _KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _MI(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _HI(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", _MI), ("ki", _KI), ("hi", _HI)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _png(w, h, rgb):
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    stride = w * 3
    rows = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride]) for y in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b"")


_dpi_done = False


def _dpi():
    """Coordenadas en pixeles reales. Si el proceso ya es DPI-aware (p. ej. la app Qt) esto no cambia nada."""
    global _dpi_done
    if not _dpi_done:
        _dpi_done = True
        try:
            if not user32.IsProcessDPIAware():
                user32.SetProcessDPIAware()
        except Exception:
            pass


def screen_size():
    _dpi()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def capture(max_w=1024):
    W, H = screen_size()
    tw = min(W, max_w)
    th = max(1, round(H * tw / W))
    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, tw, th)
    old = gdi32.SelectObject(mdc, bmp)
    gdi32.SetStretchBltMode(mdc, 4)  # HALFTONE
    gdi32.StretchBlt(mdc, 0, 0, tw, th, hdc, 0, 0, W, H, 0x00CC0020)
    bih = _BIH(ctypes.sizeof(_BIH), tw, -th, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(tw * th * 4)
    gdi32.GetDIBits(mdc, bmp, 0, th, buf, ctypes.byref(bih), 0)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(None, hdc)
    raw = bytearray(buf.raw)
    rgb = bytearray(tw * th * 3)
    rgb[0::3] = raw[2::4]
    rgb[1::3] = raw[1::4]
    rgb[2::3] = raw[0::4]
    return _png(tw, th, rgb), tw, th, W, H


def _cursor():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _failsafe():
    x, y = _cursor()
    if x <= 0 and y <= 0:
        raise Abort("Failsafe: el ratón está en la esquina superior izquierda; se detuvo el agente.")


def _real(ctx, x, y):
    W, H = screen_size()
    sc = ctx.scale or (W / min(W, 1024))
    return max(3, min(W - 3, round(float(x) * sc))), max(3, min(H - 3, round(float(y) * sc)))


@tool("screenshot", "control", "Captura la pantalla. Devuelve una imagen; las coordenadas de click/scroll son píxeles de esa imagen.", {})
def screenshot(a, ctx):
    _failsafe()
    png, tw, th, W, H = capture()
    ctx.scale, ctx.img_w = W / tw, tw
    cx, cy = _cursor()
    return {"text": "Captura %dx%d (pantalla real %dx%d). Ratón en (%d,%d)." % (tw, th, W, H, cx / ctx.scale, cy / ctx.scale), "image": png}


def _mouse(flags, data=0):
    user32.mouse_event(flags, 0, 0, data & 0xFFFFFFFF, 0)


@tool("click", "control", "Mueve el ratón a (x,y) de la última captura y hace clic.",
      {"x": I("X en la captura"), "y": I("Y en la captura"), "button": S("left (por defecto), right o middle"), "double": B("Doble clic")}, ["x", "y"])
def click(a, ctx):
    _failsafe()
    x, y = _real(ctx, a["x"], a["y"])
    user32.SetCursorPos(x, y)
    time.sleep(0.08)
    d, u = {"right": (0x8, 0x10), "middle": (0x20, 0x40)}.get(str(a.get("button") or "left").lower(), (0x2, 0x4))
    for _ in range(2 if a.get("double") else 1):
        _mouse(d)
        _mouse(u)
        time.sleep(0.06)
    time.sleep(0.4)
    return "Clic %s en (%s,%s)" % (a.get("button") or "left", a["x"], a["y"])


@tool("move_mouse", "control", "Mueve el ratón a (x,y) de la última captura.", {"x": I("X"), "y": I("Y")}, ["x", "y"])
def move_mouse(a, ctx):
    _failsafe()
    x, y = _real(ctx, a["x"], a["y"])
    user32.SetCursorPos(x, y)
    return "Ratón en (%s,%s)" % (a["x"], a["y"])


@tool("scroll", "control", "Gira la rueda del ratón (positivo = arriba, negativo = abajo).",
      {"amount": I("Pasos de rueda, ej. -5"), "x": I("X (opcional)"), "y": I("Y (opcional)")}, ["amount"])
def scroll(a, ctx):
    _failsafe()
    if a.get("x") is not None and a.get("y") is not None:
        x, y = _real(ctx, a["x"], a["y"])
        user32.SetCursorPos(x, y)
    _mouse(0x800, int(a["amount"]) * 120)
    time.sleep(0.3)
    return "Scroll %s" % a["amount"]


def _send_unicode(unit, up):
    inp = _INPUT(type=1)
    inp.ki = _KI(0, unit, 0x4 | (0x2 if up else 0), 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


@tool("type_text", "control", "Escribe texto con el teclado en la ventana que tenga el foco.", {"text": S("Texto a escribir")}, ["text"])
def type_text(a, ctx):
    _failsafe()
    txt = str(a["text"])
    for ch in txt:
        if ctx.stop.is_set():
            break
        if ch == "\n":
            _key(0x0D, False), _key(0x0D, True)
        elif ch == "\t":
            _key(0x09, False), _key(0x09, True)
        elif ch != "\r":
            data = ch.encode("utf-16-le")
            for i in range(0, len(data), 2):
                unit = struct.unpack("<H", data[i:i + 2])[0]
                _send_unicode(unit, False)
                _send_unicode(unit, True)
        time.sleep(0.01)
    time.sleep(0.2)
    return "Escrito %d caracteres" % len(txt)


VK = {"ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "windows": 0x5B, "super": 0x5B, "enter": 0x0D, "return": 0x0D,
      "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24,
      "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "capslock": 0x14, "printscreen": 0x2C}
EXT = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x5B}
for _i in range(1, 13):
    VK["f%d" % _i] = 0x70 + _i - 1


def _key(vk, up):
    fl = (0x2 if up else 0) | (0x1 if vk in EXT else 0)
    user32.keybd_event(vk, user32.MapVirtualKeyW(vk, 0), fl, 0)


@tool("press_keys", "control", "Pulsa una tecla o combinación, ej. 'enter', 'ctrl+c', 'alt+tab', 'win', 'ctrl+shift+s'.", {"keys": S("Combinación separada por +")}, ["keys"])
def press_keys(a, ctx):
    _failsafe()
    codes = []
    for part in str(a["keys"]).lower().replace(" ", "").split("+"):
        if part in VK:
            codes.append(VK[part])
        elif len(part) == 1:
            codes.append(user32.VkKeyScanW(ord(part)) & 0xFF)
        else:
            raise ToolError("Tecla desconocida: " + part)
    for c in codes:
        _key(c, False)
    for c in reversed(codes):
        _key(c, True)
    time.sleep(0.3)
    return "Teclas: " + a["keys"]


def _windows():
    res = []
    cb_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lp):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                res.append((hwnd, b.value))
        return True
    user32.EnumWindows(cb_t(cb), 0)
    return res


@tool("list_windows", "control", "Lista los títulos de las ventanas abiertas.", {})
def list_windows(a, ctx):
    return "\n".join(t for _, t in _windows()) or "Sin ventanas."


@tool("focus_window", "control", "Trae al frente la primera ventana cuyo título contenga el texto dado.", {"title": S("Parte del título")}, ["title"])
def focus_window(a, ctx):
    q = str(a["title"]).lower()
    for hwnd, t in _windows():
        if q in t.lower():
            user32.ShowWindow(hwnd, 9)
            _key(0x12, False), _key(0x12, True)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.4)
            return "Foco en: " + t
    raise ToolError("No hay ventana con ese título.")


# ---------------------------------------------------------------- procesos en segundo plano
@tool("command_output", "read", "Muestra la salida reciente de un comando lanzado con background=true.",
      {"id": S("Id devuelto por run_command (bg_…)"), "lines": I("Últimas líneas (por defecto 60)")}, ["id"])
def command_output(a, ctx):
    from . import harness
    out = harness.bg_output(str(a["id"]), int(a.get("lines") or 60))
    if out is None:
        raise ToolError("No hay ningún proceso en segundo plano con id %s." % a["id"])
    return clip(out, ctx.max_out)


@tool("stop_command", "exec", "Detiene un comando lanzado en segundo plano.", {"id": S("Id del proceso (bg_…)")}, ["id"])
def stop_command(a, ctx):
    from . import harness
    if not harness.bg_stop(str(a["id"])):
        raise ToolError("No hay ningún proceso con id %s." % a["id"])
    return "Detenido %s" % a["id"]


# ---------------------------------------------------------------- documentos e imagenes del disco
@tool("read_document", "read", "Extrae el texto de documentos Word (.docx), Excel (.xlsx), PowerPoint (.pptx) o PDF.",
      {"path": S("Ruta del documento")}, ["path"])
def read_document(a, ctx):
    from . import harness
    p = ctx.path(a["path"])
    if not os.path.isfile(p):
        raise ToolError("No existe el archivo: " + p)
    try:
        return clip(harness.read_document(p), ctx.max_out) or "(documento sin texto)"
    except RuntimeError as e:
        raise ToolError(str(e))


@tool("view_image", "read", "Abre una imagen del disco (png, jpg, webp…) para verla (requiere un modelo con visión).",
      {"path": S("Ruta de la imagen")}, ["path"])
def view_image(a, ctx):
    p = ctx.path(a["path"])
    if not os.path.isfile(p):
        raise ToolError("No existe la imagen: " + p)
    if os.path.getsize(p) > 12_000_000:
        raise ToolError("La imagen es demasiado grande (más de 12 MB).")
    with open(p, "rb") as f:
        return {"text": "Imagen %s (%d KB)" % (os.path.basename(p), os.path.getsize(p) // 1024), "image": f.read()}


# ---------------------------------------------------------------- herramientas del propio agente (las gestiona el bucle)
@tool("update_plan", "agent", "Crea o actualiza tu lista de tareas para trabajos de varios pasos (el usuario la ve). "
      "Mantén una sola tarea in_progress y marca completed al terminar cada una.",
      {"items": {"type": "array", "description": "Lista completa de tareas",
                 "items": {"type": "object", "properties": {"content": S("Tarea breve"), "status": S("pending | in_progress | completed")},
                           "required": ["content", "status"]}}}, ["items"])
def update_plan(a, ctx):
    items = a.get("items") or []
    done = sum(1 for i in items if i.get("status") == "completed")
    return "Plan actualizado (%d de %d completadas)." % (done, len(items))


@tool("ask_user", "agent", "Pregunta al usuario cuando falta información o hay que elegir entre opciones. Espera su respuesta.",
      {"question": S("Pregunta breve"), "options": {"type": "array", "items": {"type": "string"}, "description": "Opciones sugeridas (opcional)"}},
      ["question"])
def ask_user(a, ctx):
    return "(la respuesta la gestiona el agente)"


@tool("remember", "agent", "Guarda un dato duradero sobre el usuario o sus preferencias para futuras conversaciones (p. ej. 'usa pnpm').",
      {"fact": S("Dato breve a recordar")}, ["fact"])
def remember(a, ctx):
    from . import harness
    harness.remember(str(a["fact"]))
    return "Guardado en la memoria."
