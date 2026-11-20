"""Herramientas que el agente puede usar. Biblioteca estandar de Python; el control del PC usa la API de Windows
directamente y, en macOS y Linux, mss + pynput (ver control_posix)."""
import os, re, sys, json, time, html, struct, zlib, ctypes, subprocess, threading, fnmatch, base64
import urllib.request, urllib.parse, urllib.error
from . import osys
if osys.WIN:
    from ctypes import wintypes
else:
    class wintypes:      # solo para poder definir las estructuras de Windows; fuera de Windows no se usan
        WORD, DWORD, LONG, UINT, BOOL = ctypes.c_ushort, ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint, ctypes.c_int
        HWND, LPARAM = ctypes.c_void_p, ctypes.c_ssize_t
    from . import control_posix as PX


class ToolError(Exception):
    """Error 'normal' de una herramienta: se le devuelve al modelo como texto."""


class Abort(Exception):
    """Aborta toda la ejecucion del agente (failsafe del raton)."""


MAX_OUT = 10000
TOOLS = {}

# Nombres comprensibles para la interfaz (el modelo usa los internos)
TOOL_LABELS = {
    "read_file": "Leer archivos", "write_file": "Crear archivos", "edit_file": "Editar archivos", "multi_edit": "Editar varias partes",
    "move_path": "Mover o renombrar", "delete_path": "Enviar a la papelera", "list_dir": "Ver carpetas", "search_files": "Buscar en archivos",
    "run_command": "Ejecutar comandos", "open_target": "Abrir programas y archivos", "wait": "Esperar", "web_fetch": "Leer páginas web",
    "web_search": "Buscar en internet", "download_file": "Descargar archivos", "screenshot": "Capturas de pantalla", "click": "Hacer clic",
    "move_mouse": "Mover el ratón", "scroll": "Desplazar (rueda)", "type_text": "Escribir con el teclado", "press_keys": "Pulsar teclas",
    "list_windows": "Ver ventanas abiertas", "focus_window": "Activar una ventana", "command_output": "Ver salida de procesos",
    "stop_command": "Detener procesos", "read_document": "Leer documentos", "view_image": "Ver imágenes", "update_plan": "Plan de tareas",
    "run_python": "Analizar datos con Python", "show_canvas": "Mostrar en el lienzo", "ask_user": "Preguntarte", "remember": "Recordar preferencias", "forget": "Olvidar un recuerdo", "use_skill": "Usar una habilidad", "create_document": "Crear documentos (Word, Excel, PowerPoint, PDF)",
}
CATEGORIES = {"read": "Lectura", "write": "Escritura", "exec": "Ejecución", "net": "Red", "control": "Control del PC",
              "agent": "Agente", "mcp": "Conector"}
WRITE_TOOLS = {"write_file", "edit_file", "multi_edit", "move_path", "delete_path", "create_document"}   # crean punto de restauracion


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
# (formatear un disco: «format C:» o Format-Volume; Format-Table/Format-List solo muestran datos y no deben pedir permiso)
DANGEROUS_CMD = [r"\bRemove-Item\b", r"(^|[\s;|&(])(del|erase|rmdir|rd|rm|ri)\s", r"(^|[\s;|&(])format(\.com)?\s+[a-z]:", r"\bFormat-Volume\b", r"\bdiskpart\b",
                 r"\bshutdown\b", r"\b(Stop|Restart)-Computer\b", r"\breg(\.exe)?\s+(delete|add|import)\b",
                 r"\bSet-ItemProperty\b.*HK(LM|CU)", r"\bnet\s+user\b", r"\bInvoke-Expression\b|(^|[\s;|&(])iex(\s|$)",
                 r"\bbcdedit\b", r"\bcipher\b.*/w", r"\b(takeown|icacls)\b", r"\bSet-ExecutionPolicy\b",
                 r"-Verb\s+RunAs", r"\bpip3?\s+uninstall\b", r"\bSet-MpPreference\b|\bDisable-\w+", r"\bschtasks\b.*/create",
                 r"\bsc(\.exe)?\s+(delete|config|create|stop)\b", r"\btaskkill\b", r"\bStop-Process\b", r"\bClear-Content\b",
                 r"\bmove-item\b.*\\windows", r"\bwinget\s+(uninstall|install)\b", r"\bchoco\s+(uninstall|install)\b",
                 # macOS / Linux
                 r"\bsudo\b|\bdoas\b|(^|[\s;|&(])su(\s|$)", r"\bmkfs(\.\w+)?\b", r"\bdd\s+.*\bof=", r"\b(reboot|halt|poweroff)\b",
                 r"\bsystemctl\s+(stop|disable|mask|restart|poweroff|reboot)\b", r"\blaunchctl\s+(unload|remove|bootout)\b",
                 r"(^|[\s;|&(])(kill|pkill|killall)\s", r"\bchmod\s+(-R\s+)?\S+\s+/(\s|$)", r"\bchown\b", r"\bshred\b",
                 r"\b(apt|apt-get|dnf|yum|pacman|zypper|snap|flatpak)\s+(install|remove|purge|-S|-R)", r"\bbrew\s+(install|uninstall|remove)\b",
                 r"\bcrontab\s+-r\b", r"\bdefaults\s+(write|delete)\b", r"\bcsrutil\b", r"\bspctl\b", r"\bdiskutil\s+(erase|partition|unmount)",
                 r"(curl|wget)\b.*\|\s*(sudo\s+)?(ba|z)?sh\b", r">\s*/dev/(sd|nvme|disk)", r"\bfind\b.*\s-delete\b",
                 r"\bgit\s+(clean\s+-\w*f|reset\s+--hard|push\s+.*(--force|-f\b))"]
PROTECTED_PATHS = osys.protected_paths()


def is_dangerous(name, args, ctx):
    """Acciones que siempre piden confirmacion, incluso en modo automatico."""
    try:
        if name == "run_command":
            cmd = str(args.get("command", ""))
            return any(re.search(p, cmd, re.I) for p in DANGEROUS_CMD)
        if name == "run_python":                # un script de análisis no debería borrar, lanzar programas ni usar la red
            return bool(re.search(r"\b(os\.(remove|unlink|rmdir|system|popen|startfile)|shutil\.(rmtree|move)|subprocess|socket|urllib|requests|"
                                  r"ctypes|winreg|eval\(|exec\(|__import__)", str(args.get("code", ""))))
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
_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}


def missing(p, ctx=None):
    """Error de archivo inexistente con sugerencias: los modelos pequeños suelen olvidar la subcarpeta
    («notas.md» en vez de «informe/notas.md»); buscar ese nombre en la carpeta de trabajo les ahorra pasos."""
    msg = "No existe el archivo: " + p
    root = ctx.workspace if ctx is not None else os.path.dirname(p)
    name = os.path.basename(p).lower()
    found, t0 = [], time.time()
    if name and root and os.path.isdir(root):
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".")]
            for f in files:
                if f.lower() == name:
                    found.append(os.path.relpath(os.path.join(r, f), root))
            if len(found) >= 3 or time.time() - t0 > 1.5 or r.count(os.sep) - root.count(os.sep) > 6:
                break
    if found:
        msg += ". ¿Quizás te refieres a: %s?" % ", ".join(found)
    return ToolError(msg)


@tool("read_file", "read", "Lee un archivo de texto y devuelve las líneas numeradas.",
      {"path": S("Ruta del archivo"), "offset": I("Línea inicial (por defecto 1)"), "limit": I("Máximo de líneas (por defecto 400)")}, ["path"])
def read_file(a, ctx):
    p = ctx.path(a["path"])
    if not os.path.isfile(p):
        raise missing(p, ctx)
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


def _read_text(p, ctx=None):
    if not os.path.isfile(p):
        raise missing(p, ctx)
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
    text, n = _apply_edit(_read_text(p, ctx), str(a["old"]), str(a["new"]), bool(a.get("replace_all")))
    _write_text(p, text)
    return "Editado %s (%d reemplazo%s)" % (p, n, "s" if n > 1 else "")


@tool("multi_edit", "write", "Varios reemplazos en un mismo archivo de una vez (todos o ninguno). Más eficiente que varios edit_file.",
      {"path": S("Ruta del archivo"), "edits": {"type": "array", "description": "Lista de {old, new, replace_all}",
                                               "items": {"type": "object", "properties": {"old": S("Texto a reemplazar"), "new": S("Texto nuevo"),
                                                                                          "replace_all": B("Todas las apariciones")}, "required": ["old", "new"]}}},
      ["path", "edits"])
def multi_edit(a, ctx):
    p = ctx.path(a["path"])
    text = _read_text(p, ctx)
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
    return "Editado %s (%d %s, %d %s)" % (p, len(edits), "edición" if len(edits) == 1 else "ediciones",
                                          total, "reemplazo" if total == 1 else "reemplazos")


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


@tool("delete_path", "write", "Envía un archivo o carpeta a la papelera del sistema (se puede recuperar).", {"path": S("Ruta a borrar")}, ["path"])
def delete_path(a, ctx):
    p = ctx.path(a["path"])
    if not os.path.exists(p):
        raise ToolError("No existe: " + p)
    osys.trash(p)
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


DOC_EXTS = (".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pdf")


def _lines_of(fp):
    """Lineas de texto de un archivo para buscar: documentos por su texto real; binarios, ninguna."""
    ext = os.path.splitext(fp)[1].lower()
    if ext in DOC_EXTS:
        if os.path.getsize(fp) > 30_000_000:
            return []
        from . import harness
        return harness.read_document(fp, 400000).splitlines()
    if os.path.getsize(fp) > 2_000_000:
        return []
    with open(fp, "rb") as f:
        raw = f.read()
    if b"\0" in raw[:8192]:
        return []                                   # binario (imagen, ejecutable…)
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace").splitlines()


@tool("search_files", "read", "Busca texto (regex, sin distinguir mayúsculas) dentro de archivos, también dentro de documentos "
      "Word, Excel, PowerPoint y PDF; o lista archivos por patrón glob si no das 'pattern'.",
      {"pattern": S("Expresión regular a buscar (opcional)"), "path": S("Carpeta base"), "glob": S("Filtro de nombre, ej. *.py"), "max_results": I("Máximo de resultados (50)")})
def search_files(a, ctx):
    base = ctx.path(a.get("path") or ".")
    if not os.path.isdir(base):
        raise missing(base, ctx)
    pat = None
    if a.get("pattern"):
        try:
            pat = re.compile(a["pattern"], re.I)
        except re.error:                            # p. ej. «precio (con IVA»: se busca tal cual
            pat = re.compile(re.escape(a["pattern"]), re.I)
    gl = a.get("glob") or "*"
    mx = int(a.get("max_results") or 50)
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build"}
    ws = os.path.abspath(ctx.workspace)

    def short(fp):                                  # rutas cortas (relativas a la carpeta de trabajo) ahorran contexto
        r = os.path.relpath(fp, ws) if os.path.abspath(fp).lower().startswith(ws.lower() + os.sep) else fp
        return r
    res, seen = [], 0
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        for fn in sorted(files):
            if not fnmatch.fnmatch(fn.lower(), gl.lower()):
                continue
            fp = os.path.join(root, fn)
            if pat is None:
                res.append(short(fp))
            else:
                seen += 1
                try:
                    lines = _lines_of(fp)
                except Exception:
                    continue
                for i, line in enumerate(lines, 1):
                    if pat.search(line):
                        res.append("%s:%d: %s" % (short(fp), i, line.strip()[:200]))
                        if len(res) >= mx:
                            break
            if len(res) >= mx:
                return "\n".join(res) + "\n...[máximo alcanzado: afina la búsqueda con path o glob]"
    if not res:
        return "Sin resultados%s." % (" (revisados %d archivos)" % seen if pat else "")
    return "\n".join(res)


# ---------------------------------------------------------------- ejecucion
def _kill_tree(pid):
    osys.kill_tree(pid)


def cmd_env():
    """Entorno para los comandos del agente: UTF-8 y sin paginadores ni colores que esperen teclado."""
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PAGER": "cat", "GIT_PAGER": "cat", "NO_COLOR": "1"})
    if not osys.WIN:
        env["TERM"] = "dumb"
    return env


@tool("run_command", "exec", "Ejecuta un comando de la terminal del sistema (%s) en la carpeta de trabajo y devuelve su salida. "
      "Para scripts: `python archivo.py`. Con background=true lo deja corriendo (servidores, vigilantes) y devuelve un id "
      "para command_output/stop_command." % osys.shell_name(),
      {"command": S("Comando o script de %s" % osys.shell_name()), "timeout": I("Segundos máximos (por defecto 60, máx. 900)"), "cwd": S("Carpeta donde ejecutar (opcional)"),
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
    p = subprocess.Popen(osys.shell_argv(cmd), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env=cmd_env(), **osys.popen_kwargs())
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
    # sin espacios de relleno al final de cada linea ni filas vacias repetidas (las tablas de PowerShell rellenan mucho):
    # menos tokens = el modelo local lee la salida antes
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(l.rstrip() for l in out.splitlines()))
    out = clip(out, ctx.max_out)
    if why:
        return (out + "\n" if out else "") + "[Proceso terminado: %s]" % why
    return (out or "(sin salida)") + "\n[código de salida %d]" % p.returncode


@tool("run_python", "exec",
      "Ejecuta un script de Python para analizar datos o hacer cálculos y gráficos. Tiene pandas (pd), numpy y matplotlib. "
      "Lee los archivos de la carpeta de trabajo (pd.read_csv, pd.read_excel…), imprime con print() lo que quieras ver "
      "y dibuja con matplotlib: cada figura se muestra al usuario en la conversación (no hace falta plt.show ni guardar). "
      "Para dejar un gráfico como archivo usa plt.savefig('nombre.png').",
      {"code": S("Código Python completo"), "timeout": I("Segundos máximos (por defecto 120, máx. 900)")}, ["code"])
def run_python(a, ctx):
    from . import analysis
    code = str(a.get("code") or "")
    if not code.strip():
        raise ToolError("Falta el código.")
    timeout = min(max(int(a.get("timeout") or 120), 5), 900)
    try:
        out, figs, note, status, ok = analysis.run_code(code, ctx.workspace, ctx.stop, timeout)
    except RuntimeError as e:
        raise ToolError("No se pudo preparar Python para el análisis: %s" % e)
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(l.rstrip() for l in out.splitlines()))
    text = note + (clip(out, ctx.max_out) or "(sin salida de texto)")
    if figs:
        text += "\n[%s al usuario]" % ("1 gráfico mostrado" if len(figs) == 1 else "%d gráficos mostrados" % len(figs))
    if status:
        text += "\n" + status
    if not ok and not figs:
        raise ToolError(text)
    return {"text": text, "images": figs} if figs else text


@tool("open_target", "exec", "Abre un programa, archivo, carpeta o URL con la aplicación predeterminada del sistema (no espera a que termine).",
      {"target": S("Ruta del programa/archivo, o URL"), "args": S("Argumentos (opcional, solo para programas)")}, ["target"])
def open_target(a, ctx):
    t = str(a["target"])
    if re.match(r"^[a-z]+://", t, re.I):
        osys.open_path(t)
        return "Abierto: " + t
    local = ctx.path(t) if os.path.exists(ctx.path(t)) else t
    if a.get("args"):
        osys.run_program(local, str(a["args"]))
    else:
        try:
            osys.open_path(local)
        except OSError:
            osys.run_program(local)
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


def html_to_text(h, main=False):
    """Texto legible de una pagina. main=True: solo el contenido principal (<main>/<article>), sin menus, barras
    laterales ni pies, para que un modelo local no gaste su contexto en navegacion."""
    h = re.sub(r"(?is)<(script|style|noscript|svg|head|template)[^>]*>.*?</\1>", " ", h)
    if main:
        for tag in ("main", "article"):
            m = re.search(r"(?is)<%s\b[^>]*>(.*)</%s>" % (tag, tag), h)
            if m and len(m.group(1)) > 500:
                h = m.group(1)
                break
        else:
            m = re.search(r"(?is)<(div|section)\b[^>]*role=[\"']main[\"'][^>]*>(.*)", h)
            if m:
                h = m.group(2)
        h = re.sub(r"(?is)<(nav|aside|footer|header|form|button|select)\b[^>]*>.*?</\1>", " ", h)
        h = re.sub(r"(?is)<(div|ul|section)\b[^>]*(class|id)=[\"'][^\"']*(toc|sidebar|sphinxsidebar|navbar|menu|breadcrumb|cookie|related)[^\"']*[\"'][^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|section|article|ul|ol|table|pre|blockquote)>", "\n", h)
    h = re.sub(r"(?i)<(h[1-6])[^>]*>", "\n\n## ", h) if main else h
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t\r\f\v]+", " ", h)
    h = re.sub(r" *\n *", "\n", h)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def _http_get(url, timeout=20, data=None, max_bytes=2_500_000):
    req = urllib.request.Request(url, data=data, headers=UA)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:     # el servidor respondio, pero con error: eso le sirve al modelo
        body = ""
        try:
            body = html_to_text(e.read(4000).decode("utf-8", "replace"))[:600]
        except Exception:
            pass
        raise ToolError("El servidor respondió HTTP %d (%s) en %s%s" % (e.code, e.reason, url, ("\n" + body) if body else ""))
    except Exception as e:
        reason = getattr(e, "reason", e)
        if _is_local(url):
            raise ToolError("No responde %s: %s. ¿Está en marcha el servidor? (revisa command_output si lo lanzaste en segundo plano)" % (url, reason))
        raise ToolError("No se pudo acceder a %s (¿sin conexión o dirección incorrecta?): %s" % (url, reason))
    raw = r.read(max_bytes)
    ctype = r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype)
    return raw, ctype, (m.group(1) if m else "utf-8"), r.geturl()


def _is_local(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in ("localhost", "::1", "0.0.0.0") or host.startswith("127.") or host.endswith((".localhost", ".test", ".local"))


@tool("web_fetch", "net", "Descarga una página web y devuelve su texto principal (sin menús). Si sale cortada, vuelve a llamarla "
      "con start para seguir leyendo. Con raw=true devuelve el código HTML tal cual (útil para revisar tu propia web). "
      "Funciona también con servidores locales (http://127.0.0.1:puerto).",
      {"url": S("URL completa"), "max_chars": I("Máximo de caracteres (por defecto 6000)"),
       "start": I("Desde qué carácter seguir leyendo (para páginas largas)"), "raw": B("Devolver el HTML sin procesar")}, ["url"])
def web_fetch(a, ctx):
    url = str(a["url"]).strip()
    if not re.match(r"(?i)https?://", url):
        url = ("http://" if re.match(r"(?i)(localhost|127\.|0\.0\.0\.0)", url) else "https://") + url
    raw, ctype, cs, final = _http_get(url)
    if not re.search(r"text|json|xml|html|javascript", ctype, re.I):
        return "Contenido no textual (%s, %d bytes). Usa download_file para guardarlo." % (ctype, len(raw))
    try:
        txt = raw.decode(cs, errors="replace")
    except LookupError:
        txt = raw.decode("utf-8", errors="replace")
    is_html = "html" in ctype.lower() or txt.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
    if is_html and not a.get("raw"):
        # webs de internet: solo el contenido principal; tu propia web en local: todo (botones, formularios…)
        txt = html_to_text(txt, main=not _is_local(final))
    mx = max(500, int(a.get("max_chars") or 6000))
    start = max(0, int(a.get("start") or 0))
    part = txt[start:start + mx]
    rest = len(txt) - (start + mx)
    head = "[%s · %d caracteres%s]\n" % (final, len(txt), (" · desde el %d" % start) if start else "")
    tail = ("\n...[quedan %d caracteres: llama de nuevo con start=%d para seguir]" % (rest, start + mx)) if rest > 0 else ""
    return head + part + tail


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
        note = ("[Aviso: sin una clave de búsqueda solo se puede buscar en Wikipedia (DuckDuckGo bloquea las búsquedas "
                "automáticas). Si estos resultados no sirven, abre con web_fetch la página oficial que conozcas (documentación, "
                "web del proyecto, GitHub…) y dile al usuario que con una clave gratuita de Brave Search en Ajustes > Herramientas "
                "podrás buscar en toda la web.]\n")
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


def _px(fn, *a):
    """Llama al control de macOS/Linux convirtiendo sus errores en errores de herramienta."""
    try:
        return fn(*a)
    except PX.ControlError as e:
        raise ToolError(str(e))


def screen_size():
    if not osys.WIN:
        return _px(PX.screen_size)
    _dpi()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def capture(max_w=1024):
    if not osys.WIN:
        return _px(PX.capture, max_w)
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
    if not osys.WIN:
        return _px(PX.cursor)
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


def _set_cursor(x, y):
    if osys.WIN:
        user32.SetCursorPos(x, y)
    else:
        _px(PX.set_cursor, x, y)


@tool("click", "control", "Mueve el ratón a (x,y) de la última captura y hace clic.",
      {"x": I("X en la captura"), "y": I("Y en la captura"), "button": S("left (por defecto), right o middle"), "double": B("Doble clic")}, ["x", "y"])
def click(a, ctx):
    _failsafe()
    x, y = _real(ctx, a["x"], a["y"])
    _set_cursor(x, y)
    time.sleep(0.08)
    button = str(a.get("button") or "left").lower()
    if osys.WIN:
        d, u = {"right": (0x8, 0x10), "middle": (0x20, 0x40)}.get(button, (0x2, 0x4))
        for _ in range(2 if a.get("double") else 1):
            _mouse(d)
            _mouse(u)
            time.sleep(0.06)
    else:
        _px(PX.click, button, bool(a.get("double")))
    time.sleep(0.4)
    return "Clic %s en (%s,%s)" % (a.get("button") or "left", a["x"], a["y"])


@tool("move_mouse", "control", "Mueve el ratón a (x,y) de la última captura.", {"x": I("X"), "y": I("Y")}, ["x", "y"])
def move_mouse(a, ctx):
    _failsafe()
    x, y = _real(ctx, a["x"], a["y"])
    _set_cursor(x, y)
    return "Ratón en (%s,%s)" % (a["x"], a["y"])


@tool("scroll", "control", "Gira la rueda del ratón (positivo = arriba, negativo = abajo).",
      {"amount": I("Pasos de rueda, ej. -5"), "x": I("X (opcional)"), "y": I("Y (opcional)")}, ["amount"])
def scroll(a, ctx):
    _failsafe()
    if a.get("x") is not None and a.get("y") is not None:
        x, y = _real(ctx, a["x"], a["y"])
        _set_cursor(x, y)
    if osys.WIN:
        _mouse(0x800, int(a["amount"]) * 120)
    else:
        _px(PX.wheel, int(a["amount"]))
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
    if not osys.WIN:
        _px(PX.type_text, txt, ctx.stop)
        time.sleep(0.2)
        return "Escrito %d caracteres" % len(txt)
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


@tool("press_keys", "control", "Pulsa una tecla o combinación, ej. 'enter', 'ctrl+c', 'alt+tab', 'ctrl+shift+s'%s." %
      (" ('cmd' es la tecla Comando: 'cmd+c' copia)" if osys.MAC else ", 'win'"), {"keys": S("Combinación separada por +")}, ["keys"])
def press_keys(a, ctx):
    _failsafe()
    parts = str(a["keys"]).lower().replace(" ", "").split("+")
    if not osys.WIN:
        _px(PX.press_combo, parts)
        time.sleep(0.3)
        return "Teclas: " + a["keys"]
    codes = []
    for part in parts:
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
    if not osys.WIN:
        return _px(PX.windows)
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
            if not osys.WIN:
                _px(PX.focus, hwnd, t)
                time.sleep(0.4)
                return "Foco en: " + t
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
        raise missing(p, ctx)
    try:
        return clip(harness.read_document(p), ctx.max_out) or "(documento sin texto)"
    except RuntimeError as e:
        raise ToolError(str(e))


@tool("create_document", "write",
      "Crea un documento de oficina a partir de Markdown: Word (.docx), Excel (.xlsx), PowerPoint (.pptx) o PDF (.pdf); "
      "el formato lo decide la extensión de 'path'. Markdown admitido: # títulos, párrafos con **negrita** y *cursiva*, "
      "- viñetas, 1. listas, | tablas |, > citas, ```código```, ![pie](imagen.png) y <!-- salto de página -->. "
      "Excel: cada tabla es una hoja (un ## antes de la tabla le pone nombre); números, 12 %, 45.000 € y fórmulas como =SUMA(B2:B9) "
      "se guardan como tales. PowerPoint: cada # empieza una diapositiva con viñetas (y opcionalmente una tabla o una imagen).",
      {"path": S("Ruta del archivo a crear, con extensión .docx, .xlsx, .pptx o .pdf"),
       "content": S("Contenido en Markdown"), "title": S("Título del documento (opcional, para sus propiedades)")}, ["path", "content"])
def create_document(a, ctx):
    from . import office
    p = ctx.path(a["path"])
    ext = os.path.splitext(p)[1].lower()
    if ext not in office.WRITERS:
        raise ToolError("Extensión no admitida: «%s». Usa .docx, .xlsx, .pptx o .pdf (para texto o Markdown usa write_file)." % (ext or "sin extensión"))
    existed = os.path.exists(p)
    try:
        info = office.create(p, str(a.get("content") or ""), str(a.get("title") or ""))
    except PermissionError:
        raise ToolError("No se puede escribir %s: ¿está abierto en Word, Excel o PowerPoint? Ciérralo o usa otro nombre." % p)
    except ValueError as e:
        raise ToolError(str(e))
    kind = {".docx": "Word", ".xlsx": "Excel", ".pptx": "PowerPoint", ".pdf": "PDF"}[ext]
    detail = ""
    if info.get("hojas"):
        detail = "; hojas: " + ", ".join("%s (%d filas)" % h for h in info["hojas"])
    elif info.get("diapositivas"):
        detail = "; %d diapositivas" % info["diapositivas"]
    elif info.get("paginas"):
        detail = "; %d páginas" % info["paginas"]
    return "%s documento %s %s (%s%s). Puedes comprobarlo con read_document o abrirlo al usuario con open_target." % (
        "Reemplazado" if existed else "Creado", kind, p, _human(os.path.getsize(p)), detail)


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


CANVAS_EXT = {"html": ".html", "markdown": ".md", "svg": ".svg", "code": ".txt"}


@tool("show_canvas", "agent",
      "Muestra contenido en el lienzo, un panel grande junto a la conversación, en vez de pegarlo en el chat. Úsalo para "
      "páginas o aplicaciones web completas (kind=html, con su CSS y JavaScript dentro), documentos largos (kind=markdown), "
      "dibujos o diagramas (kind=svg) y programas completos (kind=code). Para corregirlo, llama de nuevo con el mismo "
      "title y el contenido entero: se guarda como una versión nueva.",
      {"title": S("Título corto del contenido"), "kind": S("html, markdown, svg o code"), "content": S("Contenido completo"),
       "language": S("Lenguaje, solo para kind=code (python, javascript…)")}, ["title", "content"])
def show_canvas(a, ctx):
    from . import paths
    content = str(a.get("content") or "")
    if not content.strip():
        raise ToolError("Falta el contenido.")
    kind = str(a.get("kind") or "").lower().strip()
    head = content.lstrip()[:400].lower()
    if kind in ("md", "texto", "text", "documento"):
        kind = "markdown"
    if kind not in CANVAS_EXT:               # sin tipo (o desconocido): se deduce del contenido
        kind = "svg" if head.startswith("<svg") or (head.startswith("<?xml") and "<svg" in head) else \
            "html" if re.search(r"<!doctype html|<html|<body|<div|<script|<style", head) else "markdown"
    title = re.sub(r"\s+", " ", str(a.get("title") or "Sin título")).strip()[:80]
    m = re.match(r"^```[\w-]*\n(.*)\n```\s*$", content.strip(), re.S)      # los modelos a veces envuelven todo en ```
    if m:
        content = m.group(1)
    d = os.path.join(paths.DATA, "canvas", str((ctx.extras or {}).get("sid") or "sin_sesion"))
    os.makedirs(d, exist_ok=True)
    slug = re.sub(r"[^\w-]+", "_", title.lower()).strip("_")[:40] or "lienzo"
    lang = str(a.get("language") or "").lower().strip()
    ext = CANVAS_EXT[kind] if kind != "code" else {"python": ".py", "javascript": ".js", "typescript": ".ts", "json": ".json", "css": ".css",
                                                   "sql": ".sql", "bash": ".sh", "powershell": ".ps1", "c": ".c", "cpp": ".cpp",
                                                   "java": ".java", "go": ".go", "rust": ".rs"}.get(lang, ".txt")
    ver = 1
    while os.path.exists(os.path.join(d, "%s_v%d%s" % (slug, ver, ext))):
        ver += 1
    p = os.path.join(d, "%s_v%d%s" % (slug, ver, ext))
    _write_text(p, content)
    what = {"html": "página web", "markdown": "documento", "svg": "dibujo", "code": "código"}[kind]
    return {"text": "Mostrado en el lienzo: «%s» (%s, versión %d). El usuario ya lo ve; no repitas el contenido en tu respuesta." % (title, what, ver),
            "ui": {"canvas": {"title": title, "kind": kind, "path": p, "version": ver, "slug": slug, "language": lang}}}


@tool("use_skill", "agent", "Carga las instrucciones completas de una habilidad de la lista «Habilidades» para seguirlas en la tarea actual.",
      {"name": S("Nombre de la habilidad")}, ["name"])
def use_skill(a, ctx):
    from . import assistants as AS
    s = AS.find_skill(a.get("name"))
    if not s:
        names = ", ".join(x["name"] for x in AS.enabled_skills()) or "(ninguna)"
        raise ToolError("No existe la habilidad «%s». Disponibles: %s" % (a.get("name"), names))
    extra = [f for f in sorted(os.listdir(s["folder"])) if f != "SKILL.md"]
    tail = ("\n\nArchivos de apoyo en %s (léelos con read_file si los necesitas): %s" % (s["folder"], ", ".join(extra))) if extra else ""
    return "Instrucciones de la habilidad «%s»:\n\n%s%s" % (s["name"], s["body"], tail)


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


@tool("forget", "agent", "Borra de la memoria un dato que el usuario ya no quiere que recuerdes (p. ej. si dice «olvida que uso pnpm»).",
      {"text": S("Palabras del dato a olvidar")}, ["text"])
def forget(a, ctx):
    from . import harness
    gone = harness.forget(str(a["text"]))
    if not gone:
        return "No había nada guardado con «%s». Memoria actual:\n%s" % (a["text"], harness.memory_text() or "(vacía)")
    return "Olvidado: " + "; ".join(gone)
