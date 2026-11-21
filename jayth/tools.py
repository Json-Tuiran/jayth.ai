# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Herramientas que el agente puede usar. Biblioteca estandar de Python; el control del PC usa la API de Windows
directamente y, en macOS y Linux, mss + pynput (ver control_posix)."""
import os, re, sys, json, time, html, struct, zlib, ctypes, subprocess, threading, fnmatch, base64
import urllib.request, urllib.parse, urllib.error
from . import osys
from .i18n import tr
if osys.WIN:
    from ctypes import wintypes
else:
    class wintypes:      # solo para poder definir las estructuras de Windows; fuera de Windows no se usan
        WORD, DWORD, LONG, UINT, BOOL = ctypes.c_ushort, ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint, ctypes.c_int
        HWND, LPARAM = ctypes.c_void_p, ctypes.c_ssize_t
    from . import control_posix as PX


class ToolError(Exception):
    """Error 'normal' de una herramienta: se le devuelve al modelo como texto. ui: datos para la interfaz (p. ej. la
    tarjeta para instalar lo que falta)."""

    def __init__(self, msg="", ui=None):
        super().__init__(msg)
        self.ui = ui or {}


class Abort(Exception):
    """Aborta toda la ejecucion del agente (failsafe del raton)."""


MAX_OUT = 10000
TOOLS = {}
PROGRESS = {}       # id de la llamada -> avance de una herramienta larga (la interfaz lo lee mientras se ejecuta)

# Nombres comprensibles para la interfaz (el modelo usa los internos)
TOOL_LABELS = {
    "read_file": tr("Leer archivos"), "write_file": tr("Crear archivos"), "edit_file": tr("Editar archivos"), "multi_edit": tr("Editar varias partes"),
    "move_path": tr("Mover o renombrar"), "delete_path": tr("Enviar a la papelera"), "list_dir": tr("Ver carpetas"), "search_files": tr("Buscar en archivos"),
    "run_command": tr("Ejecutar comandos"), "open_target": tr("Abrir programas y archivos"), "wait": tr("Esperar"), "web_fetch": tr("Leer páginas web"),
    "web_search": tr("Buscar en internet"), "download_file": tr("Descargar archivos"), "screenshot": tr("Capturas de pantalla"), "click": tr("Hacer clic"),
    "move_mouse": tr("Mover el ratón"), "scroll": tr("Desplazar (rueda)"), "type_text": tr("Escribir con el teclado"), "press_keys": tr("Pulsar teclas"),
    "list_windows": tr("Ver ventanas abiertas"), "focus_window": tr("Activar una ventana"), "command_output": tr("Ver salida de procesos"),
    "stop_command": tr("Detener procesos"), "read_document": tr("Leer documentos"), "view_image": tr("Ver imágenes"), "update_plan": tr("Plan de tareas"),
    "run_python": tr("Analizar datos con Python"), "show_canvas": tr("Mostrar en el lienzo"), "ask_user": tr("Preguntarte"), "remember": tr("Recordar preferencias"), "forget": tr("Olvidar un recuerdo"), "use_skill": tr("Usar una habilidad"), "schedule_task": tr("Programar tareas"), "list_tasks": tr("Ver tareas programadas"),
    "cancel_task": tr("Quitar tareas programadas"), "create_document": tr("Crear documentos (Word, Excel, PowerPoint, PDF)"),
    "ui_elements": tr("Leer la interfaz de un programa"), "click_element": tr("Pulsar un elemento de un programa"), "drag": tr("Arrastrar con el ratón"),
    "window_action": tr("Manejar ventanas"), "clipboard": tr("Usar el portapapeles"), "jayth_guide": tr("Consultar la guía de Jayth"),
    "browser_open": tr("Abrir páginas en el navegador de Jayth"), "browser_read": tr("Leer la página del navegador"), "browser_click": tr("Pulsar en el navegador"),
    "browser_type": tr("Escribir en el navegador"), "browser_nav": tr("Navegar (atrás, recargar, desplazar)"), "browser_screenshot": tr("Capturar el navegador"),
    "generate_image": tr("Crear imágenes"), "connect_service": tr("Proponer conectar un servicio"), "search_knowledge": tr("Buscar en tu conocimiento"),
}
CATEGORIES = {"read": tr("Lectura"), "write": tr("Escritura"), "exec": tr("Ejecución"), "net": tr("Red"), "control": tr("Control del PC"),
              "agent": tr("Agente"), "mcp": tr("Conector")}
WRITE_TOOLS = {"write_file", "edit_file", "multi_edit", "move_path", "delete_path", "create_document", "generate_image"}   # crean punto de restauracion


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
        self.origin = None  # esquina de la ventana capturada (None = pantalla entera)
        self.call_id = None  # llamada en curso (para publicar su avance en PROGRESS)

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
        if name == "browser_type":              # algo que parece un número de tarjeta: siempre lo confirma el usuario
            return bool(re.search(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", str(args.get("text", ""))))
        if name == "run_python":                # un script de análisis no debería borrar, lanzar programas ni usar la red
            return bool(re.search(r"\b(os\.(remove|unlink|rmdir|system|popen|startfile)|shutil\.(rmtree|move)|subprocess|socket|urllib|requests|"
                                  r"ctypes|winreg|eval\(|exec\(|__import__)", str(args.get("code", ""))))
        if name == "schedule_task":
            return True                         # una tarea que se ejecutará sola siempre la aprueba el usuario
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


def _search_ddg(q, mx):
    """DuckDuckGo (página HTML, por GET: por POST bloquea enseguida). None si pide un captcha (no se salta)."""
    raw, _, _, _ = _http_get("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q}))
    page = raw.decode("utf-8", errors="replace")
    if 'class="result__a"' not in page:
        return None if "anomaly" in page else ""
    out = []
    for blk in page.split('class="result__a"')[1:]:
        m = re.search(r'href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not m:
            continue
        link = html.unescape(m.group(1))
        qs = urllib.parse.urlparse(link)
        if "uddg" in qs.query:
            link = urllib.parse.parse_qs(qs.query)["uddg"][0]
        if "duckduckgo.com/y.js" in link:              # anuncios
            continue
        title = html_to_text(m.group(2))
        sn = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', blk, re.S)
        out.append("%d. %s\n   %s\n   %s" % (len(out) + 1, title, link, html_to_text(sn.group(1)) if sn else ""))
        if len(out) >= mx:
            break
    return "\n".join(out)


def _search_bing(q, mx):
    """Bing en formato RSS (sin clave): títulos, enlaces y resúmenes. None si no responde como se espera."""
    from . import i18n
    raw, _, _, _ = _http_get("https://www.bing.com/search?" + urllib.parse.urlencode({"q": q, "format": "rss", "setlang": i18n.LANG}))
    x = raw.decode("utf-8", errors="replace")
    items = re.findall(r"<item>(.*?)</item>", x, re.S)
    if not items:
        return None if "<rss" not in x else ""
    out = []
    for it in items:
        g = lambda tag: html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<%s>(.*?)</%s>" % (tag, tag), it, re.S) or [None, ""])[1]))
        link = g("link").strip()
        if not link:
            continue
        out.append("%d. %s\n   %s\n   %s" % (len(out) + 1, html_to_text(g("title")), link, html_to_text(g("description"))))
        if len(out) >= mx:
            break
    return "\n".join(out)


_DDG_PAUSE = [0.0]          # si DuckDuckGo pide captcha, se deja descansar un rato (y se usa Bing)
SEARCHER = None             # búsquedas con el motor del navegador integrado, sin mostrarlo (lo pone la ventana)


def _bing_url(u):
    """Los enlaces de Bing pasan por bing.com/ck/a?…&u=a1<base64>: el destino real."""
    if "bing.com/ck/a" not in u:
        return u
    v = (urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("u") or [""])[0]
    if v.startswith("a1"):
        try:
            return base64.urlsafe_b64decode(v[2:] + "=" * (-len(v[2:]) % 4)).decode("utf-8", "replace")
        except Exception:
            pass
    return u


def _search_browser(engine, q, mx, ctx):
    """Con el navegador integrado (oculto): como un navegador normal, sin saltarse captchas. None si no se pudo."""
    s = SEARCHER
    if s is None:
        return None
    res = s.search(engine, q, getattr(ctx, "stop", None))
    if res is None:
        return None
    out = []
    for r in res:
        link = str(r.get("u") or "")
        if engine == "ddg" and "uddg=" in link:
            link = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("uddg", [link])[0]
        link = _bing_url(link)
        if not link.startswith("http") or "duckduckgo.com/y.js" in link:
            continue
        out.append("%d. %s\n   %s\n   %s" % (len(out) + 1, " ".join(str(r.get("t") or "").split()), link, " ".join(str(r.get("s") or "").split())))
        if len(out) >= mx:
            break
    return "\n".join(out)


@tool("web_search", "net", "Busca en la web y devuelve títulos, enlaces y resúmenes (requiere internet).",
      {"query": S("Texto de búsqueda"), "max_results": I("Resultados (por defecto 6)")}, ["query"])
def web_search(a, ctx):
    mx = int(a.get("max_results") or 6)
    q = str(a["query"])
    ex = ctx.extras or {}
    prov = ex.get("search_provider", "auto")
    if prov == "searxng" and ex.get("searxng_url"):
        return _search_searxng(q, mx, ex["searxng_url"]) or "Sin resultados."
    key = ex.get("brave_key")
    if key and prov in ("auto", "brave"):
        return _search_brave(q, mx, key) or "Sin resultados."
    # sin configurar nada: DuckDuckGo y, si bloquea o no responde, Bing; Wikipedia solo si ninguno contesta
    errors = []
    sources = (("DuckDuckGo", _search_ddg),
               ("Bing (navegador)", lambda q_, mx_: _search_browser("bing", q_, mx_, ctx)),
               ("DuckDuckGo (navegador)", lambda q_, mx_: _search_browser("ddg", q_, mx_, ctx)),
               ("Bing", _search_bing))
    empty = False
    for name, fn in sources:
        if fn is _search_ddg and time.time() < _DDG_PAUSE[0]:
            continue
        try:
            res = fn(q, mx)
        except ToolError as e:
            errors.append("%s: %s" % (name, str(e)[:120]))
            continue
        if res is None:
            if fn is _search_ddg:
                _DDG_PAUSE[0] = time.time() + 600
            errors.append("%s: pidió verificación o no respondió" % name)
            continue
        if res:
            return res
        empty = True                                  # sin resultados aquí: se prueba la siguiente fuente
    if empty and not errors:
        return "Sin resultados."
    wiki = _search_wikipedia(q, mx)
    return ("[Los buscadores no respondieron ahora mismo (%s); solo hay resultados de Wikipedia. Si no sirven, abre con "
            "web_fetch una página que conozcas o vuelve a buscar en unos minutos.]\n" % "; ".join(errors)) + (wiki or "Sin resultados en Wikipedia.")


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


def capture(max_w=1024, rect=None, zoom=False):
    """PNG reducido de la pantalla o de una zona (x, y, ancho, alto): (png, ancho_img, alto_img, ancho_real, alto_real).
    zoom: una zona pequeña se amplía (hasta el doble) para leer texto menudo."""
    if not osys.WIN:
        return _px(PX.capture, max_w, rect, zoom)
    if rect:
        X, Y, W, H = rect
    else:
        X, Y = 0, 0
        W, H = screen_size()
    tw = min(max_w, W * 2 if zoom else W)
    th = max(1, round(H * tw / W))
    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, tw, th)
    old = gdi32.SelectObject(mdc, bmp)
    gdi32.SetStretchBltMode(mdc, 4)  # HALFTONE
    gdi32.StretchBlt(mdc, 0, 0, tw, th, hdc, X, Y, W, H, 0x00CC0020)
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
        raise Abort(tr("Failsafe: el ratón está en la esquina superior izquierda; se detuvo el agente."))


def _real(ctx, x, y):
    """Píxel de la última captura -> píxel real de la pantalla (si se capturó una ventana, relativo a ella)."""
    W, H = screen_size()
    sc = ctx.scale or (W / min(W, 1024))
    ox, oy = getattr(ctx, "origin", None) or (0, 0)
    return max(3, min(W - 3, round(ox + float(x) * sc))), max(3, min(H - 3, round(oy + float(y) * sc)))


def _find_window(q):
    """La ventana cuyo título encaja mejor (igual, empieza por, contiene), sin contar las de Jayth."""
    q = q.strip().lower()
    mine = os.getpid()
    best = None
    for hwnd, t in _windows():
        tl = t.lower()
        if q not in tl:
            continue
        if osys.WIN:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == mine:
                continue
        rank = 0 if tl == q else 1 if tl.startswith(q) else 2
        if best is None or rank < best[0]:
            best = (rank, hwnd, t)
    return (best[1], best[2]) if best else (None, None)


def _window_rect(hwnd, title):
    """Trae la ventana al frente y devuelve su zona en la pantalla (x, y, ancho, alto), o None si no se puede saber."""
    if not osys.WIN:
        _px(PX.focus, hwnd, title)
        time.sleep(0.5)
        return PX.window_rect(hwnd, title)
    _dpi()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    _key(0x12, False), _key(0x12, True)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)                                  # que termine de dibujarse delante
    r = wintypes.RECT()
    try:                                             # borde visible, sin la sombra de Windows 10/11
        got = ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) == 0
    except Exception:
        got = False
    if not got:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    W, H = screen_size()
    x0, y0, x1, y1 = max(0, r.left), max(0, r.top), min(W, r.right), min(H, r.bottom)
    if x1 - x0 < 20 or y1 - y0 < 20:                 # fuera de la pantalla principal: se captura la pantalla entera
        return None
    return x0, y0, x1 - x0, y1 - y0


def _win(q, ctx, wait=6):
    """(id, título) de la ventana pedida; espera unos segundos por si el programa aún está abriendo."""
    hwnd, title = _find_window(q)
    end = time.time() + wait
    while hwnd is None and time.time() < end and not ctx.stop.is_set():
        time.sleep(0.4)
        hwnd, title = _find_window(q)
    if hwnd is None:
        raise ToolError("No hay ninguna ventana cuyo título contenga «%s». Mira los títulos con list_windows." % q)
    return hwnd, title


def _zone(ctx, z):
    """«x,y,ancho,alto» de la última captura -> zona real de la pantalla."""
    try:
        vals = [float(v) for v in (z if isinstance(z, (list, tuple)) else re.split(r"[,\s;]+", str(z).strip("[]() ")))]
        x, y, w, h = vals[:4]
    except (ValueError, TypeError):
        raise ToolError("zoom debe ser «x,y,ancho,alto» en píxeles de la última captura, p. ej. «100,200,300,150».")
    W, H = screen_size()
    sc = ctx.scale or (W / min(W, 1024))
    ox, oy = getattr(ctx, "origin", None) or (0, 0)
    x0, y0 = max(0, round(ox + x * sc)), max(0, round(oy + y * sc))
    x1, y1 = min(W, round(ox + (x + w) * sc)), min(H, round(oy + (y + h) * sc))
    if x1 - x0 < 8 or y1 - y0 < 8:
        raise ToolError("La zona a ampliar es demasiado pequeña o queda fuera de la pantalla.")
    return x0, y0, x1 - x0, y1 - y0


@tool("screenshot", "control", "Captura la pantalla, solo una ventana (window) o amplía una zona de la última captura (zoom, para leer texto "
      "pequeño). El usuario también ve la captura en el chat. Las coordenadas de click/drag/scroll son píxeles de la última imagen.",
      {"window": S("Parte del título de una ventana: la trae al frente y captura solo esa ventana (opcional)"),
       "zoom": S("Zona de la última captura a ampliar: «x,y,ancho,alto» (opcional)")})
def screenshot(a, ctx):
    _failsafe()
    q = str(a.get("window") or "").strip()
    rect, title = None, ""
    if a.get("zoom"):
        rect = _zone(ctx, a["zoom"])
    elif q:
        hwnd, title = _win(q, ctx)
        rect = _window_rect(hwnd, title)
    if not osys.WIN:                                 # en Windows el brillo no sale en las capturas; aquí se aparta un instante
        _ui("hide")
        time.sleep(0.15)
    try:
        png, tw, th, W, H = capture(rect=rect, zoom=bool(a.get("zoom")))
    finally:
        if not osys.WIN:
            _ui("show")
    _ui("look")                                      # destello en los bordes: «acabo de mirar»
    ctx.scale, ctx.img_w = W / tw, tw
    ctx.origin = (rect[0], rect[1]) if rect else (0, 0)
    if a.get("zoom"):
        return {"text": "Zona ampliada (%dx%d). Las coordenadas de click/drag ahora son píxeles de esta imagen." % (tw, th), "image": png}
    if rect:
        return {"text": "Captura de la ventana «%s» (%dx%d). Las coordenadas de click/scroll son píxeles de esta imagen." % (title, tw, th), "image": png}
    cx, cy = _cursor()
    note = (" No pude saber dónde está la ventana «%s»: es la pantalla entera." % title) if q else ""
    return {"text": "Captura %dx%d (pantalla real %dx%d). Ratón en (%d,%d).%s" % (tw, th, W, H, cx / ctx.scale, cy / ctx.scale, note), "image": png}


def _mouse(flags, data=0):
    user32.mouse_event(flags, 0, 0, data & 0xFFFFFFFF, 0)


def _set_cursor(x, y):
    if osys.WIN:
        user32.SetCursorPos(x, y)
    else:
        _px(PX.set_cursor, x, y)


# la interfaz se suscribe aquí para mostrar que el agente tiene el control (brillo en los bordes, su puntero, ondas)
UI_HOOK = None


def _ui(kind, x=-1, y=-1):
    h = UI_HOOK
    if h is not None:
        try:
            h(kind, x, y)
        except Exception:
            pass


def _here():
    try:
        return _cursor()
    except Exception:
        return -1, -1


def _glide(x, y):
    """Lleva el ratón hasta (x, y) con un movimiento suave (~¼ s) en vez de un salto: se ve qué va a tocar el agente."""
    _ui("move", x, y)
    sx, sy = _here()
    d = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5 if sx >= 0 else 0
    n = 0 if d < 8 else int(min(18, max(6, d / 40)))
    for i in range(1, n + 1):
        e = 1 - (1 - i / float(n)) ** 3
        _set_cursor(round(sx + (x - sx) * e), round(sy + (y - sy) * e))
        time.sleep(0.014)
    _set_cursor(x, y)


def _mods(keys):
    """'shift', 'ctrl+shift'… -> lista de nombres de tecla."""
    return [k for k in str(keys or "").lower().replace(" ", "").split("+") if k]


def _hold(mods, down):
    if not mods:
        return
    if not osys.WIN:
        return _px(PX.hold, mods, down)
    codes = [VK[m] for m in mods if m in VK]
    for c in (codes if down else reversed(codes)):
        _key(c, not down)


_BTN = {"right": (0x8, 0x10), "middle": (0x20, 0x40)}


def _press_at(x, y, button="left", double=False, keys=None):
    """Lleva el ratón hasta (x, y) píxeles reales y hace clic (con teclas pulsadas si se piden)."""
    _glide(x, y)
    _ui("click", x, y)
    time.sleep(0.08)
    button = str(button or "left").lower()
    mods = _mods(keys)
    _hold(mods, True)
    try:
        if osys.WIN:
            d, u = _BTN.get(button, (0x2, 0x4))
            for _ in range(2 if double else 1):
                _mouse(d)
                _mouse(u)
                time.sleep(0.06)
        else:
            _px(PX.click, button, bool(double))
    finally:
        _hold(mods, False)
    time.sleep(0.4)


@tool("click", "control", "Mueve el ratón a (x,y) de la última captura y hace clic. keys: teclas a mantener pulsadas (p. ej. «shift» "
      "o «ctrl» para seleccionar varios).",
      {"x": I("X en la captura"), "y": I("Y en la captura"), "button": S("left (por defecto), right o middle"), "double": B("Doble clic"),
       "keys": S("Teclas pulsadas durante el clic: shift, ctrl, alt… (opcional)")}, ["x", "y"])
def click(a, ctx):
    _failsafe()
    x, y = _real(ctx, a["x"], a["y"])
    _press_at(x, y, a.get("button"), a.get("double"), a.get("keys"))
    return "Clic %s%s en (%s,%s)" % (a.get("button") or "left", (" con " + a["keys"]) if a.get("keys") else "", a["x"], a["y"])


@tool("drag", "control", "Arrastra con el ratón de (x1,y1) a (x2,y2) de la última captura: mover archivos o ventanas, seleccionar texto, "
      "deslizadores, dibujar…",
      {"x1": I("X inicial"), "y1": I("Y inicial"), "x2": I("X final"), "y2": I("Y final"), "button": S("left (por defecto) o right")},
      ["x1", "y1", "x2", "y2"])
def drag(a, ctx):
    _failsafe()
    x1, y1 = _real(ctx, a["x1"], a["y1"])
    x2, y2 = _real(ctx, a["x2"], a["y2"])
    button = str(a.get("button") or "left").lower()
    _glide(x1, y1)
    _ui("click", x1, y1)
    time.sleep(0.08)
    d, u = _BTN.get(button, (0x2, 0x4))
    _mouse(d) if osys.WIN else _px(PX.mouse_button, button, True)
    try:
        time.sleep(0.12)
        _glide(x2, y2)                               # en pasos: los programas ven el arrastre
        time.sleep(0.12)
    finally:
        _mouse(u) if osys.WIN else _px(PX.mouse_button, button, False)
    _ui("click", x2, y2)
    time.sleep(0.35)
    return "Arrastrado de (%s,%s) a (%s,%s)" % (a["x1"], a["y1"], a["x2"], a["y2"])


@tool("move_mouse", "control", "Mueve el ratón a (x,y) de la última captura.", {"x": I("X"), "y": I("Y")}, ["x", "y"])
def move_mouse(a, ctx):
    _failsafe()
    x, y = _real(ctx, a["x"], a["y"])
    _glide(x, y)
    return "Ratón en (%s,%s)" % (a["x"], a["y"])


@tool("scroll", "control", "Gira la rueda del ratón (positivo = arriba, negativo = abajo).",
      {"amount": I("Pasos de rueda, ej. -5"), "x": I("X (opcional)"), "y": I("Y (opcional)")}, ["amount"])
def scroll(a, ctx):
    _failsafe()
    if a.get("x") is not None and a.get("y") is not None:
        x, y = _real(ctx, a["x"], a["y"])
        _glide(x, y)
    _ui("scroll", *_here())
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
    _ui("key", *_here())
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
    _ui("key", *_here())
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
    _ui("focus")
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


# ---------------------------------------------------------------- interfaz de los programas (accesibilidad)
UI_ROLE = {"Button": "botón", "SplitButton": "botón", "Edit": "campo de texto", "Document": "documento", "Text": "texto",
           "CheckBox": "casilla", "RadioButton": "opción", "ComboBox": "lista desplegable", "ListItem": "elemento de lista",
           "MenuItem": "menú", "Hyperlink": "enlace", "TabItem": "pestaña", "TreeItem": "elemento del árbol", "Slider": "deslizador",
           "Spinner": "número", "DataItem": "celda"}
# Windows: UI Automation desde PowerShell (viene con el sistema; nada que instalar)
_UIA_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class JDpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
[void][JDpi]::SetProcessDPIAware()
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$CT = [System.Windows.Automation.ControlType]
$root = $A::FromHandle([IntPtr]::new(%(hwnd)d))
$types = @(%(types)s) | ForEach-Object { New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, $CT::$_) }
$cond = New-Object System.Windows.Automation.AndCondition(
  (New-Object System.Windows.Automation.PropertyCondition($A::IsOffscreenProperty, $false)),
  (New-Object System.Windows.Automation.OrCondition([System.Windows.Automation.Condition[]]$types)))
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$out = New-Object System.Collections.ArrayList
foreach ($e in $all) {
  if ($out.Count -ge %(limit)d) { break }
  try {
    $c = $e.Current
    $r = $c.BoundingRectangle
    if ($r.IsEmpty -or $r.Width -lt 2 -or $r.Height -lt 2) { continue }
    $v = ''
    try { $v = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value } catch {}
    [void]$out.Add([ordered]@{t = $c.ControlType.ProgrammaticName.Substring(12); n = $c.Name; v = "$v"; x = [int]$r.X; y = [int]$r.Y;
                              w = [int]$r.Width; h = [int]$r.Height; e = $c.IsEnabled})
  } catch {}
}
ConvertTo-Json -InputObject @($out) -Compress -Depth 3
"""


def _ui_read(hwnd, title, limit=150):
    if not osys.WIN:
        return _px(PX.ui_elements, hwnd, title, limit)
    script = _UIA_PS % {"hwnd": int(hwnd), "limit": int(limit), "types": ",".join("'%s'" % t for t in UI_ROLE)}
    try:
        r = subprocess.run(osys.shell_argv(script), capture_output=True, timeout=40, **osys.popen_kwargs())
    except subprocess.TimeoutExpired:
        raise ToolError("La ventana tarda demasiado en describir su interfaz. Usa screenshot y click con coordenadas.")
    out = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode != 0 or not out.startswith("["):
        raise ToolError("No pude leer la interfaz de «%s»: %s" % (title, (r.stderr.decode("utf-8", "replace").strip() or out)[:300]))
    return json.loads(out)


def _ui_text(title, items):
    lines = ["Ventana «%s»: %d elementos (número · tipo · nombre%s):" % (title, len(items), " · valor" if any(i.get("v") for i in items) else "")]
    for k, it in enumerate(items, 1):
        name = " ".join(str(it.get("n") or "").split())[:80]
        val = " ".join(str(it.get("v") or "").split())[:80]
        lines.append("[%d] %s%s%s%s" % (k, UI_ROLE.get(it.get("t"), it.get("t")), (" «%s»" % name) if name else "",
                                       (" = «%s»" % val) if val and val != name else "", "" if it.get("e", True) else " (desactivado)"))
    if not items:
        lines.append("(no expone elementos: usa screenshot y click con coordenadas)")
    return "\n".join(lines)


@tool("ui_elements", "control", "Lista los botones, menús, campos, casillas, enlaces y textos visibles de una ventana (accesibilidad del sistema), "
      "numerados. Es la forma más fiable de usar un programa: luego click_element con el número. También sirve sin ver imágenes.",
      {"window": S("Parte del título de la ventana"), "filter": S("Mostrar solo los que contengan este texto (opcional)")}, ["window"])
def ui_elements(a, ctx):
    hwnd, title = _win(str(a["window"]), ctx)
    items = _ui_read(hwnd, title)
    f = str(a.get("filter") or "").strip().lower()
    if f:
        items = [i for i in items if f in str(i.get("n") or "").lower() or f in str(i.get("v") or "").lower()]
    ctx.ui = {"window": title, "hwnd": hwnd, "items": items}
    _ui("look")
    return _ui_text(title, items)


@tool("click_element", "control", "Hace clic en un elemento de la interfaz por su número de ui_elements (o por su nombre): trae la ventana al "
      "frente y pulsa en su centro, sin adivinar coordenadas.",
      {"index": I("Número del elemento en la última lista de ui_elements"), "name": S("O el nombre del elemento (p. ej. «Guardar»)"),
       "window": S("Ventana (si se busca por nombre sin haber listado antes)"), "button": S("left (por defecto), right o middle"),
       "double": B("Doble clic"), "keys": S("Teclas pulsadas durante el clic (opcional)")})
def click_element(a, ctx):
    _failsafe()
    ui = getattr(ctx, "ui", None)
    if a.get("window") and (not ui or str(a["window"]).lower() not in ui["window"].lower()):
        hwnd, title = _win(str(a["window"]), ctx)
        ui = ctx.ui = {"window": title, "hwnd": hwnd, "items": _ui_read(hwnd, title)}
    if not ui:
        raise ToolError("Primero lista los elementos de la ventana con ui_elements (o indica window).")
    it = None
    if a.get("index") not in (None, ""):
        k = int(a["index"])
        if not 1 <= k <= len(ui["items"]):
            raise ToolError("No hay elemento %d: la lista tiene %d." % (k, len(ui["items"])))
        it = ui["items"][k - 1]
    elif a.get("name"):
        q = " ".join(str(a["name"]).split()).lower()
        cand = [i for i in ui["items"] if " ".join(str(i.get("n") or "").split()).lower() == q] or \
               [i for i in ui["items"] if q in str(i.get("n") or "").lower()]
        if not cand:
            raise ToolError("No encuentro «%s» en la ventana «%s». Vuelve a listar con ui_elements." % (a["name"], ui["window"]))
        it = cand[0]
    else:
        raise ToolError("Indica index (número de ui_elements) o name.")
    if not it.get("e", True):
        raise ToolError("Ese elemento está desactivado ahora mismo.")
    _window_rect(ui["hwnd"], ui["window"])           # al frente (el clic tiene que caer en esa ventana)
    x, y = int(it["x"] + it["w"] / 2), int(it["y"] + it["h"] / 2)
    _press_at(x, y, a.get("button"), a.get("double"), a.get("keys"))
    name = " ".join(str(it.get("n") or "").split())[:60]
    return "Clic en %s%s" % (UI_ROLE.get(it.get("t"), it.get("t")), (" «%s»" % name) if name else "")


# ---------------------------------------------------------------- ventanas y portapapeles
@tool("window_action", "control", "Maneja una ventana: maximize, minimize, restore, close (pide cerrarla como el botón X; el programa puede "
      "preguntar si guardar), move o resize (en píxeles reales de la pantalla).",
      {"window": S("Parte del título de la ventana"), "action": S("maximize, minimize, restore, close, move o resize"),
       "x": I("X (move)"), "y": I("Y (move)"), "width": I("Ancho (resize)"), "height": I("Alto (resize)")}, ["window", "action"])
def window_action(a, ctx):
    act = str(a["action"]).lower().strip()
    if act not in ("maximize", "minimize", "restore", "close", "move", "resize"):
        raise ToolError("action debe ser maximize, minimize, restore, close, move o resize.")
    hwnd, title = _win(str(a["window"]), ctx, wait=2)
    _ui("focus")
    g = lambda k: int(a[k]) if a.get(k) not in (None, "") else None
    if not osys.WIN:
        _px(PX.window_action, hwnd, title, act, g("x"), g("y"), g("width"), g("height"))
    elif act in ("maximize", "minimize", "restore"):
        user32.ShowWindow(hwnd, {"maximize": 3, "minimize": 6, "restore": 9}[act])
    elif act == "close":
        user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE: como pulsar la X
    else:
        _dpi()
        if user32.IsZoomed(hwnd):
            user32.ShowWindow(hwnd, 9)
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        x, y = g("x"), g("y")
        w, h = g("width"), g("height")
        user32.SetWindowPos(hwnd, 0, r.left if x is None else x, r.top if y is None else y,
                            (r.right - r.left) if w is None else max(80, w), (r.bottom - r.top) if h is None else max(60, h), 0x0004 | 0x0010)
    time.sleep(0.4)
    return {"maximize": "Maximizada", "minimize": "Minimizada", "restore": "Restaurada", "close": "Pedí cerrar", "move": "Movida",
            "resize": "Cambiada de tamaño"}[act] + " la ventana «%s»" % title


def _clip_dll():
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    V = ctypes.c_void_p
    u.OpenClipboard.argtypes, u.GetClipboardData.restype, u.GetClipboardData.argtypes = [V], V, [ctypes.c_uint]
    u.SetClipboardData.restype, u.SetClipboardData.argtypes = V, [ctypes.c_uint, V]
    k.GlobalAlloc.restype, k.GlobalAlloc.argtypes = V, [ctypes.c_uint, ctypes.c_size_t]
    k.GlobalLock.restype, k.GlobalLock.argtypes, k.GlobalUnlock.argtypes = V, [V], [V]
    return u, k


def _clip_open(u):
    for _ in range(20):                               # otro programa puede tenerlo abierto un instante
        if u.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise ToolError("El portapapeles está ocupado por otro programa.")


def clipboard_get():
    if not osys.WIN:
        return _px(PX.clipboard_get)
    u, k = _clip_dll()
    _clip_open(u)
    try:
        if not u.IsClipboardFormatAvailable(13):      # CF_UNICODETEXT
            return ""
        h = u.GetClipboardData(13)
        p = k.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else ""
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_set(text):
    if not osys.WIN:
        return _px(PX.clipboard_set, text)
    u, k = _clip_dll()
    data = text.encode("utf-16-le") + b"\0\0"
    h = k.GlobalAlloc(0x0002, len(data))             # GMEM_MOVEABLE
    p = k.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    k.GlobalUnlock(h)
    _clip_open(u)
    try:
        u.EmptyClipboard()
        if not u.SetClipboardData(13, h):
            raise ToolError("No pude escribir en el portapapeles.")
    finally:
        u.CloseClipboard()


@tool("clipboard", "control", "Lee el texto del portapapeles o escribe en él (para pasar datos entre programas: copia aquí y pega allí con ctrl+v).",
      {"action": S("read o write"), "text": S("Texto a copiar (write)")}, ["action"])
def clipboard(a, ctx):
    act = str(a["action"]).lower().strip()
    if act in ("write", "set", "copy"):
        txt = str(a.get("text") or "")
        clipboard_set(txt)
        return "Copiado al portapapeles (%d caracteres)." % len(txt)
    txt = clipboard_get()
    return clip(txt, ctx.max_out) if txt else "El portapapeles no tiene texto."


# ---------------------------------------------------------------- navegador integrado de Jayth
BROWSER = None      # puente con el panel del navegador (lo pone la ventana; sin ventana, no hay navegador)


def _web(op, ctx, timeout=45, **args):
    b = BROWSER
    if b is None:
        raise ToolError("El navegador integrado no está disponible aquí. Usa web_fetch para leer páginas.")
    try:
        return b.call(op, args, ctx.stop, timeout)
    except RuntimeError as e:
        raise ToolError(str(e))


@tool("browser_open", "net", "Abre una página en el navegador integrado de Jayth (el usuario la ve a la vista) y devuelve su texto y lo que se "
      "puede usar, numerado. Para webs que hay que usar, no solo leer: buscar dentro de un sitio, iniciar sesión, formularios, páginas con JavaScript.",
      {"url": S("Dirección (o lo que quieras buscar)")}, ["url"])
def browser_open(a, ctx):
    return _web("open", ctx, 60, url=str(a["url"]))


@tool("browser_read", "net", "Lee la página abierta en el navegador integrado: what=all (resumen y lo que hay a la vista), text (todo el texto, por "
      "partes con offset) o elements (todo lo que se puede usar, numerado; filter para buscar uno).",
      {"what": S("all (por defecto), text o elements"), "filter": S("Solo elementos que contengan este texto (opcional)"),
       "offset": I("Desde qué carácter del texto (opcional)")})
def browser_read(a, ctx):
    return _web("read", ctx, what=a.get("what") or "all", filter=a.get("filter") or "", offset=a.get("offset") or 0)


@tool("browser_click", "net", "Pulsa un enlace, botón, casilla o pestaña de la página del navegador integrado por su número (de browser_open o "
      "browser_read) o por su texto. Es un clic real; si se abre otra página, devuelve su resumen.",
      {"index": I("Número del elemento"), "text": S("O el texto del enlace o botón")})
def browser_click(a, ctx):
    return _web("click", ctx, index=a.get("index"), text=a.get("text"))


@tool("browser_type", "net", "Escribe en un campo de la página del navegador integrado (por número, o por su nombre en field) y, con submit=true, "
      "pulsa Intro (buscar, enviar). En una lista desplegable elige la opción con ese texto. Las contraseñas las escribe el usuario.",
      {"index": I("Número del campo"), "field": S("O el nombre del campo"), "text": S("Texto a escribir (o la opción de la lista)"),
       "submit": B("Pulsar Intro al terminar"), "clear": B("Borrar lo que había antes (por defecto sí)")}, ["text"])
def browser_type(a, ctx):
    return _web("type", ctx, index=a.get("index"), field=a.get("field"), text=str(a.get("text", "")), submit=bool(a.get("submit")),
                clear=a.get("clear", True) not in (False, "false", 0))


@tool("browser_nav", "net", "En el navegador integrado: back, forward o reload; o desplaza la página: down, up, top, bottom.",
      {"action": S("back, forward, reload, down, up, top o bottom")}, ["action"])
def browser_nav(a, ctx):
    return _web("nav", ctx, action=str(a["action"]))


@tool("browser_screenshot", "net", "Captura lo que se ve en el navegador integrado (para ver el diseño de la página; el usuario también la ve).", {})
def browser_screenshot(a, ctx):
    return _web("shot", ctx)


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


@tool("generate_image", "write",
      "Crea una imagen nueva (foto, ilustración, logotipo, icono, fondo, portada…) a partir de una descripción, con el "
      "generador de imágenes de Jayth, que funciona en este equipo. Úsalo cuando el usuario pida una imagen o cuando la "
      "tarea la necesite (p. ej. ilustrar una web, una presentación o un documento). Describe con detalle qué se ve, el "
      "estilo, la luz, los colores y el encuadre; el texto que deba aparecer, entre comillas. Una imagen por llamada: "
      "tarda de segundos a varios minutos según el equipo. Con reference modifica una imagen existente. El usuario ve la "
      "imagen en el chat y tú también (si el modelo tiene visión): compruébala y repite con otra descripción si no encaja.",
      {"prompt": S("Descripción detallada de la imagen (funciona en cualquier idioma; en inglés suele ser más precisa)"),
       "path": S("Archivo .png donde guardarla (opcional; por defecto en la carpeta «imagenes» de la carpeta de trabajo)"),
       "aspect": S("square (cuadrada, por defecto), landscape (horizontal 16:9), portrait (vertical 9:16), wide (3:2) o tall (2:3)"),
       "width": I("Ancho en píxeles (opcional; mejor usa aspect)"), "height": I("Alto en píxeles (opcional)"),
       "seed": I("Semilla para repetir una imagen con pequeños cambios en la descripción (opcional)"),
       "reference": S("Imagen existente que modificar o usar como referencia (opcional)")}, ["prompt"])
def generate_image(a, ctx):
    from . import imagegen as IG, core
    cfg = core.SET.snapshot()
    prompt = re.sub(r"\s+", " ", str(a.get("prompt") or "")).strip()
    if not prompt:
        raise ToolError("Falta la descripción de la imagen (prompt).")
    if not IG.available():
        raise ToolError("El generador de imágenes de Jayth no está disponible en este sistema (%s). Dile al usuario que, de momento, "
                        "no se pueden crear imágenes aquí." % osys.os_label())
    m = IG.model(cfg)
    st = IG.status(cfg)
    if not st["ready"]:
        if IG.installing():
            raise ToolError("El generador de imágenes se está instalando ahora (el usuario ve el avance en el chat). Espera a que el "
                            "usuario te diga que terminó; mientras, sigue con el resto de la tarea.", ui={"image_setup": m["id"]})
        raise ToolError("El generador de imágenes todavía no está instalado en este equipo (hace falta descargar %s una sola vez). "
                        "El usuario ya ve en el chat un botón para instalarlo: no lo intentes de nuevo hasta que te diga que está listo; "
                        "mientras, sigue con el resto de la tarea o explícale que hace falta." % _human(st["need"]),
                        ui={"image_setup": m["id"]})
    out = ctx.path(a["path"]) if a.get("path") else IG.default_path(cfg, ctx.workspace, prompt)
    if os.path.splitext(out)[1].lower() != ".png":
        out = os.path.splitext(out)[0] + ".png"
    refs = [ctx.path(a["reference"])] if a.get("reference") else []
    cid = ctx.call_id
    existed = os.path.exists(out)

    def prog(info):
        if cid:
            PROGRESS[cid] = info
    try:
        r = IG.generate(cfg, prompt, out, aspect=a.get("aspect") or "", width=a.get("width") or 0, height=a.get("height") or 0,
                        seed=a.get("seed"), refs=refs, progress=prog, stop=ctx.stop)
    except IG.Cancelled:
        raise ToolError("Cancelado por el usuario.")
    except IG.NotInstalled:
        raise ToolError("Faltan archivos del generador de imágenes. El usuario ve en el chat un botón para instalarlos.", ui={"image_setup": m["id"]})
    except RuntimeError as e:
        raise ToolError(str(e))
    finally:
        PROGRESS.pop(cid, None)
    with open(r["path"], "rb") as f:
        png = f.read()
    took = r["seconds"]
    return {"text": "%s imagen %s (%dx%d, %s, semilla %d) en %s. El usuario ya la ve en el chat; no la describas entera. "
                    "Para otra versión parecida usa la misma semilla con la descripción retocada." % (
                        "Reemplazada la" if existed else "Creada la", r["path"], r["width"], r["height"], r["model"], r["seed"],
                        ("%d s" % took) if took < 120 else ("%.1f min" % (took / 60))),
            "image": png, "ui": {"generated": r["path"]}}


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


@tool("schedule_task", "agent",
      "Programa una tarea para que Jayth la haga solo más adelante o de forma periódica (p. ej. «cada mañana resúmeme las noticias», "
      "«el viernes a las 17:00 revisa esta carpeta»). El usuario debe aprobarla.",
      {"name": S("Nombre corto de la tarea"), "prompt": S("Qué debe hacer, con todo el detalle necesario (se ejecutará sin esta conversación)"),
       "frequency": S("once (una vez), daily (cada día), weekdays (lunes a viernes), weekly (cada semana) o interval (cada X minutos)"),
       "time": S("Hora HH:MM en 24 h (no hace falta con interval)"), "date": S("Fecha AAAA-MM-DD, solo para once"),
       "weekdays": {"type": "array", "items": {"type": "integer"}, "description": "Días para weekly: 0=lunes … 6=domingo"},
       "every_minutes": I("Minutos entre ejecuciones, solo para interval (mínimo 5)")}, ["name", "prompt", "frequency"])
def schedule_task(a, ctx):
    from . import schedule as SC
    kind = str(a.get("frequency") or "daily").lower().strip()
    kind = {"una vez": "once", "diaria": "daily", "diario": "daily", "semanal": "weekly", "laborables": "weekdays", "intervalo": "interval"}.get(kind, kind)
    if kind not in [k for k, _ in SC.KINDS]:
        raise ToolError("frequency debe ser once, daily, weekdays, weekly o interval.")
    tm = str(a.get("time") or "09:00").strip()
    if kind != "interval" and not re.match(r"^\d{1,2}:\d{2}$", tm):
        raise ToolError("time debe tener el formato HH:MM (por ejemplo 08:30).")
    days = [int(d) for d in (a.get("weekdays") or []) if str(d).lstrip("-").isdigit() and 0 <= int(d) <= 6]
    if kind == "weekly" and not days:
        raise ToolError("Para weekly indica weekdays (0=lunes … 6=domingo).")
    date = str(a.get("date") or time.strftime("%Y-%m-%d"))
    t = SC.new_task(str(a["name"]), str(a["prompt"]), kind, tm, date, days, a.get("every_minutes") or 60)
    if not t["next"]:
        raise ToolError("Esa fecha y hora ya han pasado (hoy es %s, son las %s)." % (time.strftime("%Y-%m-%d"), time.strftime("%H:%M")))
    SC.add(t)
    return "Tarea «%s» programada: %s. Próxima vez: %s. (Se ejecuta mientras Jayth esté abierto.)" % (t["name"], SC.describe(t).lower(), SC.when_text(t["next"]))


@tool("list_tasks", "agent", "Lista las tareas programadas del usuario con su próxima ejecución.", {})
def list_tasks(a, ctx):
    from . import schedule as SC
    ts = SC.all_tasks()
    if not ts:
        return "No hay tareas programadas."
    return "\n".join("- %s [id %s]: %s · %s" % (t["name"], t["id"], SC.describe(t),
                                                ("próxima " + SC.when_text(t.get("next"))) if t.get("enabled", True) and t.get("next") else "en pausa o ya hecha")
                     for t in ts)


@tool("cancel_task", "agent", "Quita una tarea programada (por su id o por su nombre; consulta list_tasks).", {"task": S("Id o nombre de la tarea")}, ["task"])
def cancel_task(a, ctx):
    from . import schedule as SC
    q = str(a.get("task") or "").strip().lower()
    hit = [t for t in SC.all_tasks() if q and (t["id"].lower() == q or q in t["name"].lower())]
    if len(hit) != 1:
        raise ToolError(("No hay ninguna tarea que coincida con «%s»." if not hit else "Varias tareas coinciden con «%s»: usa el id.") % a.get("task"))
    SC.remove(hit[0]["id"])
    return "Tarea «%s» quitada." % hit[0]["name"]


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


@tool("connect_service", "agent",
      "Propone al usuario conectar un servicio externo con su propia cuenta cuando lo pida o la tarea lo necesite: higgsfield "
      "(imágenes y vídeo con IA en la nube; gasta sus créditos), gmail, drive (Google Drive), calendar (Google Calendar), notion, "
      "canva, linear, atlassian (Jira y Confluence) o huggingface. En el chat aparece un botón «Conectar» y el usuario inicia sesión "
      "él mismo en la página del servicio; tú nunca ves su contraseña. No lo propongas si la tarea se puede hacer bien en el equipo.",
      {"service": S("Id del servicio (higgsfield, gmail, drive, calendar, notion, canva, linear, atlassian, huggingface)"),
       "reason": S("Para qué lo necesitas, en una frase (la ve el usuario)")}, ["service"])
def connect_service(a, ctx):
    from . import conectores as CN
    q = str(a.get("service") or "").strip().lower()
    c = CN.find(q) or next((x for x in CN.CATALOG if q and (q in x["name"].lower() or x["name"].lower() in q)), None)
    if not c:
        raise ToolError("No conozco el servicio «%s». Disponibles: %s." % (a.get("service"), ", ".join(x["id"] for x in CN.CATALOG)))
    if CN.connected(c["id"]):
        return "%s ya está conectado: usa sus herramientas (empiezan por mcp__%s__)." % (c["name"], re.sub(r"[^A-Za-z0-9_-]+", "_", c["name"])[:16])
    return {"text": "El usuario ve en el chat un botón para conectar %s con su cuenta. Espera a que te diga que ya está conectado; "
                    "mientras, sigue con lo que puedas hacer sin ese servicio." % c["name"],
            "ui": {"connect_service": c["id"], "reason": str(a.get("reason") or "")[:200]}}


@tool("search_knowledge", "read",
      "Busca por significado (no solo palabras exactas) en las carpetas de conocimiento que eligió el usuario: sus notas, documentos "
      "y proyectos. Devuelve los fragmentos más parecidos con su archivo y línea. Úsalo antes de responder sobre sus documentos o "
      "sobre temas que puedan estar en ellos; después lee lo que necesites con read_file o read_document.",
      {"query": S("Qué buscas, con tus palabras (una pregunta o un tema)"), "k": I("Cuántos fragmentos (por defecto 6, máximo 12)")}, ["query"])
def search_knowledge(a, ctx):
    from . import conocimiento as KN
    q = str(a.get("query") or "").strip()
    if not q:
        raise ToolError("Falta qué buscar (query).")
    if not KN.ready():
        raise ToolError("El conocimiento local no está listo: el usuario debe elegir carpetas e instalar el buscador en Ajustes › Conocimiento.")
    try:
        hits = KN.search(q, max(1, min(12, int(a.get("k") or 6))))
    except Exception as e:
        raise ToolError("No se pudo buscar: %s" % e)
    if not hits:
        return "No encontré nada parecido en las carpetas de conocimiento."
    return clip("\n\n".join("[%d] %s (línea %d, parecido %.2f)\n%s" % (i + 1, h["path"], h["line"], h["score"], h["text"][:900])
                            for i, h in enumerate(hits)), ctx.max_out)


@tool("jayth_guide", "agent", "Guía de Jayth, la app en la que trabajas: qué hace cada parte, dónde está cada botón, menú o ajuste, "
      "cómo se hace algo en Jayth y datos de esta instalación (versión, modelo activo, carpetas, atajos, permisos). Consúltala "
      "antes de responder cualquier pregunta sobre Jayth. Sin tema devuelve el índice.",
      {"topic": S("Tema o pregunta, p. ej. «cambiar el idioma», «dónde se guardan los modelos», «deshacer cambios»")})
def jayth_guide(a, ctx):
    from . import guide
    return guide.answer(str(a.get("topic") or ""))


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
