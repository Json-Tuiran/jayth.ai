# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Modelos que cambiaron de sitio: Jayth los encuentra y los vuelve a enlazar solo.

Casos que cubre: el archivo se cortó y se pegó en otra carpeta del mismo disco o de otro; se movió toda la carpeta de
modelos sin cambiar el ajuste; el USB del modo portátil cambió de letra; se pegaron modelos nuevos en la carpeta de
modelos; el disco externo donde estaba un modelo no está conectado (entonces no se toca nada: vuelve a funcionar al
conectarlo).

Cómo se reconoce un archivo: mismo nombre y mismo tamaño exacto (en un modelo de varios GB el tamaño en bytes es
prácticamente único). Si además se renombró, basta el tamaño exacto. Una copia que todavía se está escribiendo no se
acepta hasta que termina (está bloqueada, cambió hace muy poco o aún no tiene su tamaño completo).

Dónde se busca, de lo más rápido a lo más lento:
  guess  sitios evidentes: la carpeta de modelos, la predeterminada, junto a los demás modelos, la misma ruta en otra
         unidad. Son unas pocas comprobaciones: se usa incluso justo antes de encender el modelo.
  quick  además, una pasada corta por las carpetas habituales (Descargas, Escritorio, Documentos…) y la raíz de cada
         disco, a pocos niveles de profundidad.
  deep   además, todos los discos completos salvo las carpetas del sistema (en segundo plano).
"""
import os, re, time, string
from . import paths, osys
from .i18n import tr

SIZE_ONLY_MIN = 50 << 20      # por debajo, coincidir solo por tamaño (archivo renombrado) no sería fiable
NEW_MIN = 30 << 20            # un .gguf más pequeño no es un modelo (vocabularios sueltos, pruebas)
SETTLE = 45                   # segundos sin cambios para dar por terminada una copia
BUDGET = {"guess": 0, "quick": 12, "deep": 900}
_SPLIT = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$", re.I)
_SKIP = {"windows", "program files", "program files (x86)", "programdata", "system volume information", "recovery",
         "perflogs", "msocache", "appdata", "node_modules", "__pycache__", "site-packages", "windowsapps", "config.msi",
         "proc", "sys", "dev", "usr", "bin", "sbin", "lib", "lib32", "lib64", "boot", "etc", "var", "snap", "private",
         "cores", "system", ".git", ".svn", ".venv", ".npm", ".cargo", ".rustup", ".gradle", ".m2", ".trash", ".trashes",
         ".spotlight-v100", ".fseventsd", ".documentrevisions-v100", ".temporaryitems"}


# ---------------------------------------------------------------- utilidades
def _norm(p):
    return os.path.normcase(os.path.abspath(p)) if p else ""


def _inside(path, folder):
    return bool(path and folder) and _norm(path).startswith(_norm(folder).rstrip("\\/") + os.sep)


def sig(path):
    """«tamaño-fecha» del archivo ("" si no existe)."""
    try:
        st = os.stat(path)
        return "%d-%d" % (st.st_size, int(st.st_mtime))
    except OSError:
        return ""


def _unsig(s):
    try:
        a, b = str(s).split("-")
        return int(a), int(b)
    except (ValueError, AttributeError):
        return None, None


def _expected(m, key):
    """(tamaño, fecha, seguro) que debería tener el archivo `key` ("path" o "mmproj") del modelo."""
    size, mt = _unsig(m.get(key + "_sig"))
    if size is not None:
        return size, mt, True
    if key == "path":
        size, mt = _unsig((m.get("caps") or {}).get("sig"))
        if size is not None:
            return size, mt, True
        if m.get("size") and not _SPLIT.search(m.get("path", "")):
            return int(m["size"]), None, False            # tamaño anotado al instalarlo (orientativo)
    elif m.get("mmproj_size"):
        return int(m["mmproj_size"]), None, False
    return None, None, False


def split_parts(path):
    """Todas las partes de un modelo dividido (-00001-of-0000N) a partir de la primera; [path] si no está dividido."""
    mm = _SPLIT.search(os.path.basename(path or ""))
    if not mm:
        return [path] if path else []
    n = int(mm.group(2))
    stem = os.path.basename(path)[:mm.start()]
    return [os.path.join(os.path.dirname(path), "%s-%05d-of-%05d.gguf" % (stem, i, n)) for i in range(1, n + 1)]


def files_ok(m):
    """True si están todos los archivos del modelo (partes incluidas); el proyector de visión va aparte."""
    parts = split_parts(m.get("path", ""))
    return bool(parts) and all(os.path.isfile(p) for p in parts)


def _state(path, mtime=None):
    """"ok" si el archivo está completo y es un GGUF; "copying" si aún se está escribiendo; None si no sirve."""
    try:
        st = os.stat(path)
        with open(path, "rb") as f:
            magic = f.read(4)
    except PermissionError:
        return "copying"                       # Windows lo bloquea mientras se copia
    except OSError:
        return None
    recent = time.time() - st.st_mtime < SETTLE
    if magic != b"GGUF":
        return "copying" if recent else None
    if mtime is not None and int(st.st_mtime) == int(mtime):
        return "ok"
    return "copying" if recent else "ok"


def _drive_of(path):
    """Unidad o volumen de una ruta (E:\\, /Volumes/USB, /media/yo/USB) o "" si está en el disco principal."""
    if not path:
        return ""
    if osys.WIN:
        d = os.path.splitdrive(path)[0]
        return d + "\\" if d else ""
    p = os.path.abspath(path).split("/")
    if len(p) > 3 and p[1] == "Volumes":
        return "/".join(p[:3])
    if len(p) > 4 and p[1] == "media":
        return "/".join(p[:4])
    if len(p) > 5 and p[1] == "run" and p[2] == "media":
        return "/".join(p[:5])
    if len(p) > 3 and p[1] == "mnt":
        return "/".join(p[:3])
    return ""


def drives():
    """Discos locales conectados (sin unidades de red ni lectores vacíos)."""
    out = []
    if osys.WIN:
        try:
            import ctypes
            k = ctypes.windll.kernel32
            mask = k.GetLogicalDrives()
            for i, letter in enumerate(string.ascii_uppercase):
                if mask >> i & 1:
                    root = letter + ":\\"
                    if k.GetDriveTypeW(ctypes.c_wchar_p(root)) in (2, 3, 6):     # extraíble, fijo, RAM
                        out.append(root)
        except Exception:
            out = [d + ":\\" for d in string.ascii_uppercase if os.path.isdir(d + ":\\")]
        return out
    for b in (["/Volumes"] if osys.MAC else ["/media", "/mnt", "/run/media"]):
        try:
            for e in os.scandir(b):
                if not e.is_dir(follow_symlinks=False):
                    continue
                if osys.MAC or b == "/mnt":
                    out.append(e.path)
                else:                                  # /media/usuario/DISCO
                    out += [x.path for x in os.scandir(e.path) if x.is_dir(follow_symlinks=False)]
        except OSError:
            pass
    return out


def _quiet_errors():
    """Que Windows no saque «No hay ningún disco en la unidad» al mirar un lector vacío."""
    if osys.WIN:
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadErrorMode(0x0001, None)
        except Exception:
            pass


def walk(roots, visit, deadline, stop=None):
    """Recorre [(carpeta, niveles)] llamando a visit(DirEntry) con cada .gguf. Salta carpetas del sistema, ocultas
    y enlaces. Devuelve False si se acabó el tiempo o se pidió parar."""
    seen = {}
    stack = [(r, d) for r, d in reversed(roots) if r]
    while stack:
        if (stop and stop()) or time.time() > deadline:
            return False
        d, left = stack.pop()
        key = _norm(d)
        if seen.get(key, -1) >= left:
            continue
        seen[key] = left
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        n = e.name.lower()
                        if left > 0 and n not in _SKIP and not n.startswith("$") \
                                and not getattr(e, "is_junction", lambda: False)():
                            stack.append((e.path, left - 1))
                    elif e.name.lower().endswith(".gguf"):
                        visit(e)
                except OSError:
                    pass
    return True


def _roots(level, cfg, models, old_paths):
    """Carpetas a recorrer según el nivel, de lo más probable a lo menos."""
    far = 99 if level == "deep" else None
    r = [(cfg.get("models_dir"), far or 5), (paths.MODELS_DEFAULT, far or 5)]
    for p in old_paths:                         # lo que quede de la carpeta antigua (p. ej. se movió a una hermana)
        up = os.path.dirname(p)
        while up and not os.path.isdir(up) and os.path.dirname(up) != up:
            up = os.path.dirname(up)
        if up and os.path.dirname(up) != up:
            r.append((up, far or 3))
    for m in models:
        if files_ok(m):
            r.append((os.path.dirname(os.path.dirname(m["path"])), far or 3))
    home = os.path.expanduser("~")
    for sub in ("Downloads", "Descargas", "Desktop", "Escritorio", "Documents", "Documentos"):
        r.append((os.path.join(home, sub), far or 4))
    r.append((home, far or 2))
    for d in drives():
        r.append((d, far or 3))
    if far and not osys.WIN:
        r.append(("/", 99))
    out, seen = [], set()
    for p, n in r:
        k = _norm(p)
        if p and k not in seen and os.path.isdir(p) and not os.path.islink(p):
            seen.add(k)
            out.append((p, n))
    return out


# ---------------------------------------------------------------- búsqueda
def _guesses(old, bases):
    """Rutas evidentes donde podría estar ahora `old`: dentro de las carpetas base y en la misma ruta en otra unidad."""
    name, folder = os.path.basename(old), os.path.basename(os.path.dirname(old))
    out = []
    for b in bases:
        if b:
            out += [os.path.join(b, folder, name), os.path.join(b, name)]
    drv = _drive_of(old)
    if drv:
        rest = old[len(drv):]
        out += [os.path.join(d, rest) for d in drives()]
    seen, res = {_norm(old)}, []
    for p in out:
        k = _norm(p)
        if k not in seen:
            seen.add(k)
            res.append(p)
    return res


class _Want:
    def __init__(self, m, key):
        self.mid, self.key = m["id"], key
        self.old = m.get(key) or ""
        self.name = os.path.basename(self.old).lower()
        self.folder = os.path.basename(os.path.dirname(self.old)).lower()
        self.size, self.mtime, self.strict = _expected(m, key)
        self.cands = []          # (ruta, tamaño)

    def take(self, path, size):
        if all(_norm(p) != _norm(path) for p, _ in self.cands):
            self.cands.append((path, size))


def _pick(w, taken, prefer_dir=""):
    """Mejor candidato: (ruta, "ok") / (ruta, "copying") / (None, None)."""
    free = [c for c in w.cands if _norm(c[0]) not in taken]
    named = [c for c in free if os.path.basename(c[0]).lower() == w.name]

    def near(c):
        d = os.path.dirname(c[0])
        return 0 if prefer_dir and _norm(d) == _norm(prefer_dir) else 1 if os.path.basename(d).lower() == w.folder else 2
    pools = []
    if w.size:
        pools.append([c for c in named if c[1] == w.size])                       # mismo nombre y tamaño
    if w.key == "path":
        if w.size and w.strict and w.size >= SIZE_ONLY_MIN:
            pools.append([c for c in free if c[1] == w.size and c not in named])  # renombrado: el tamaño exacto
        if not (w.size and w.strict):
            pools.append(named)                                                   # tamaño desconocido: el nombre
    else:
        pools.append([c for c in named if near(c) < 2])     # proyector: nombre genérico (mmproj-F16.gguf), solo cerca
    copying = None
    for pool in pools:
        for p, s in sorted(pool, key=near):
            st = _state(p, w.mtime)
            if st == "ok" and w.key == "path":
                rest = [_state(x) for x in split_parts(p)[1:]]
                if None in rest:
                    continue
                if "copying" in rest:
                    st = "copying"
            if st == "ok":
                return p, "ok"
            if st == "copying":
                copying = copying or p
    for p, s in named:              # mismo nombre, aún más pequeño y recién tocado: se está copiando
        if w.size and s < w.size:
            try:
                if time.time() - os.stat(p).st_mtime < SETTLE * 4:
                    copying = copying or p
            except OSError:
                pass
    return (copying, "copying") if copying else (None, None)


def _mmproj_in(folder):
    try:
        return [os.path.join(folder, n) for n in os.listdir(folder) if "mmproj" in n.lower() and n.lower().endswith(".gguf")]
    except OSError:
        return []


def find(models, cfg, level="quick", folders=None, stop=None):
    """Busca los archivos que faltan de `models`. Devuelve {id: {"path": nueva|None, "mmproj": nueva|None,
    "state": "ok"|"copying"|"missing"|"offline", "drive": unidad}} (solo de los modelos con algún archivo ausente)."""
    _quiet_errors()
    bad = [(m, not files_ok(m), bool(m.get("mmproj")) and not os.path.isfile(m["mmproj"])) for m in models]
    bad = [b for b in bad if b[1] or b[2]]
    if not bad:
        return {}
    taken = set()
    for m in models:
        if files_ok(m):
            taken.update(_norm(p) for p in split_parts(m["path"]))
    wants = {}
    for m, a, b in bad:
        if a:
            wants[(m["id"], "path")] = _Want(m, "path")
        if b:
            wants[(m["id"], "mmproj")] = _Want(m, "mmproj")
    # 1) sitios evidentes
    bases = [cfg.get("models_dir"), paths.MODELS_DEFAULT] + list(folders or [])
    for m in models:
        if files_ok(m):
            bases += [os.path.dirname(m["path"]), os.path.dirname(os.path.dirname(m["path"]))]
    for w in wants.values():
        for g in _guesses(w.old, bases):
            try:
                if os.path.isfile(g):
                    w.take(g, os.path.getsize(g))
            except OSError:
                pass
    # 2) recorrer carpetas
    if level != "guess" or folders:
        by_name, by_size = {}, {}
        for w in wants.values():
            by_name.setdefault(w.name, []).append(w)
            if w.key == "path" and w.strict and w.size and w.size >= SIZE_ONLY_MIN:
                by_size.setdefault(w.size, []).append(w)

        def visit(e):
            n = e.name.lower()
            if n in by_name or by_size:
                try:
                    size = e.stat().st_size
                except OSError:
                    return
                for w in by_name.get(n, []) + by_size.get(size, []):
                    w.take(e.path, size)

        def done():
            return all(_pick(w, taken)[1] == "ok" if w.key == "path" else bool(w.cands) for w in wants.values())
        if folders:
            walk([(f, 99) for f in folders if f and os.path.isdir(f)], visit, time.time() + BUDGET["deep"], stop)
        if level != "guess" and not (folders and done()):
            roots = _roots(level, cfg, models, [w.old for w in wants.values()])
            last = [time.time()]

            def stop2():                 # se para en cuanto aparece todo lo que falta (se mira cada pocos segundos)
                if stop and stop():
                    return True
                if time.time() - last[0] > 3:
                    last[0] = time.time()
                    return done()
                return False
            walk(roots, visit, time.time() + BUDGET[level], stop2)
    # 3) decidir
    out = {}
    for m, a, b in bad:
        r = {"path": None, "mmproj": None, "state": "ok", "drive": ""}
        folder = "" if a else os.path.dirname(m["path"])
        if a:
            p, st = _pick(wants[(m["id"], "path")], taken)
            if st == "ok":
                r["path"] = p
                folder = os.path.dirname(p)
                taken.update(_norm(x) for x in split_parts(p))
            else:
                r["state"] = st or "missing"
        if b:
            w = wants[(m["id"], "mmproj")]
            if folder:                                  # lo más probable: junto al modelo
                for x in [os.path.join(folder, os.path.basename(w.old))] + _mmproj_in(folder):
                    if os.path.isfile(x):
                        w.take(x, os.path.getsize(x))
            p, st = _pick(w, set(), prefer_dir=folder)
            if st == "ok":
                r["mmproj"] = p
            elif not a:
                r["state"] = st or "missing"            # el modelo está; solo falta su proyector de visión
                r["only_mmproj"] = True
            elif r["path"]:
                r["mmproj_lost"] = True                 # el modelo apareció y su proyector no (seguirá sin visión)
        if r["state"] != "ok":
            drv = _drive_of(m.get("path") if a else m.get("mmproj", ""))
            if drv and not os.path.isdir(drv):
                r["state"], r["drive"] = "offline", drv.rstrip("\\/")
        out[m["id"]] = r
    return out


# ---------------------------------------------------------------- modelos nuevos en una carpeta
def _is_projector(path):
    from . import gguf
    if "mmproj" in os.path.basename(path).lower():
        return True
    try:
        return str(gguf.read_meta(path, {"general.architecture"}).get("general.architecture", "")).lower() in ("clip", "mtmd")
    except (OSError, ValueError):
        return False


def _repo_from_folder(folder):
    """«autor__repo» (como guarda Jayth las descargas) -> «autor/repo»."""
    n = re.sub(r"__(gguf|original)$", "", os.path.basename(folder))
    if n.count("__") == 1 and all(n.split("__")):
        return n.replace("__", "/")
    return ""


def discover(folders, models, ignored=(), depth=3):
    """Modelos (.gguf completos) que hay en `folders` y no están en la lista. Devuelve entradas listas para añadir."""
    from .provision import pretty_name, quant_label
    known = set(_norm(p) for p in ignored)
    for m in models:
        known.update(_norm(p) for p in split_parts(m.get("path", "")))
        if m.get("mmproj"):
            known.add(_norm(m["mmproj"]))
    found = []

    def visit(e):
        n = e.name.lower()
        if n.startswith("ggml-vocab") or _norm(e.path) in known:
            return
        mm = _SPLIT.search(n)
        if mm and int(mm.group(1)) != 1:
            return
        parent = os.path.basename(os.path.dirname(e.path)).lower()
        if parent.endswith("__original"):
            return
        if parent in ("conocimiento", "imagen") or "embedding" in n:   # modelos internos (búsqueda en tus archivos, imágenes)
            return
        try:
            size = e.stat().st_size
        except OSError:
            return
        if size >= NEW_MIN or "mmproj" in n:
            found.append(e.path)
    walk([(f, depth) for f in folders if f and os.path.isdir(f)], visit, time.time() + 30)
    proj = [p for p in found if _is_projector(p)]
    out, ids = [], {m.get("id") for m in models}
    for p in found:
        if p in proj or _state(p) != "ok":
            continue
        parts = split_parts(p)
        if not all(_state(x) == "ok" for x in parts):
            continue
        folder = os.path.dirname(p)
        near = [x for x in proj if _norm(os.path.dirname(x)) == _norm(folder)]
        near += [x for x in _mmproj_in(folder) if x not in near and _norm(x) in known]   # proyector ya conocido
        repo = _repo_from_folder(folder)
        base = re.sub(r"[^\w.-]+", "_", "local_" + os.path.basename(p))
        mid, k = base, 2
        while mid in ids:
            mid, k = "%s_%d" % (base, k), k + 1
        ids.add(mid)
        q = quant_label(os.path.basename(p))
        mmp = near[0] if len(near) == 1 else ""
        out.append({"id": mid, "name": pretty_name(repo or os.path.basename(p)), "quant": "" if q == os.path.basename(p) else q,
                    "path": p, "mmproj": mmp, "repo": repo, "file": os.path.basename(p),
                    "size": sum(os.path.getsize(x) for x in parts), "added": time.time(), "found": True,
                    "path_sig": sig(p), "mmproj_sig": sig(mmp) if mmp else ""})
    return out


# ---------------------------------------------------------------- todo junto, sobre los ajustes guardados
def run(level="quick", folders=None, add_new=False, explicit=False, stop=None):
    """Arregla lo que se pueda y lo guarda.
    add_new: añadir también los modelos nuevos que haya en la carpeta de modelos (y en `folders`).
    explicit: el usuario eligió `folders` a propósito (se añade todo lo que haya, aunque antes lo quitara de la lista).
    Devuelve un informe con listas de títulos: fixed, vision, copying, missing, offline, added, lost_vision;
    models_dir (nueva carpeta de descargas, si cambió) y pending (si queda algo sin resolver)."""
    from . import core
    cfg = core.SET.snapshot()
    models = cfg["models"]
    rep = {"fixed": [], "vision": [], "copying": [], "missing": [], "offline": [], "added": [], "lost_vision": [],
           "models_dir": "", "pending": False, "by_id": {}}
    res = find(models, cfg, level, folders, stop)
    old_dir = cfg.get("models_dir") or ""
    moved_bases = []
    for m in models:
        r = res.get(m["id"])
        if not r:
            continue
        title = title_of(m, models)
        if r["state"] != "ok":
            rep["by_id"][m["id"]] = (r["state"], r["drive"])
        kw = {}
        if r["path"]:
            kw.update(path=r["path"], file=os.path.basename(r["path"]), path_sig=sig(r["path"]))
            rep["fixed"].append((title, r["path"]))
            if _inside(m["path"], old_dir):
                rel = os.path.normcase(os.path.relpath(m["path"], old_dir))
                newp = r["path"]
                if _norm(newp).endswith(os.sep + rel):
                    moved_bases.append(newp[:len(newp) - len(rel)].rstrip("\\/"))
                else:
                    moved_bases.append(os.path.dirname(newp))
        if r["mmproj"]:
            kw.update(mmproj=r["mmproj"], mmproj_sig=sig(r["mmproj"]))
            if not r["path"]:
                rep["vision"].append((title, r["mmproj"]))
        if r.get("mmproj_lost"):
            rep["lost_vision"].append(title)
        if kw:
            core.SET.update_model(m["id"], **kw)
        if r["state"] in ("copying", "missing", "offline"):
            rep["pending"] = True
            rep[r["state"]].append(title if r["state"] == "missing" else (title, r["drive"]))
    # la carpeta de descargas sigue a los modelos si se movió entera (no queda ningún modelo en la antigua)
    if moved_bases and len({_norm(b) for b in moved_bases}) == 1 and _norm(moved_bases[0]) != _norm(old_dir):
        if not any(files_ok(m) and _inside(m["path"], old_dir) for m in core.SET.snapshot()["models"]):
            core.SET.update({"models_dir": moved_bases[0]})
            rep["models_dir"] = moved_bases[0]
    # modelos nuevos pegados en la carpeta de modelos (o en la que se indicó)
    cfg = core.SET.snapshot()
    if add_new:
        look = list(folders or []) + ([] if explicit else [cfg.get("models_dir") or "", paths.MODELS_DEFAULT])
        seen, uniq = set(), []
        for f in look:
            if f and _norm(f) not in seen:
                seen.add(_norm(f))
                uniq.append(f)
        ignored = [] if explicit else cfg.get("models_ignored") or []
        new = discover(uniq, cfg["models"], ignored)
        if not explicit and not cfg.get("models_scan_init"):
            # primera vez con esta función: lo que ya hubiera sin registrar se respeta (el usuario pudo quitarlo de la lista)
            core.SET.update({"models_scan_init": True, "models_ignored": list(ignored) + [e["path"] for e in new]})
            new = []
        for e in new:
            core.SET.add_model(e, activate=not core.SET.snapshot().get("active_model"))
            rep["added"].append(core.model_title(e) or e["name"])
        if explicit and new:
            keep = [p for p in cfg.get("models_ignored") or [] if _norm(p) not in {_norm(e["path"]) for e in new}]
            core.SET.update({"models_ignored": keep})
    # anotar tamaño y fecha de los archivos presentes: así se reconocen si algún día se mueven
    for m in core.SET.snapshot()["models"]:
        kw = {}
        if files_ok(m) and m.get("path_sig") != sig(m["path"]):
            kw["path_sig"] = sig(m["path"])
        if m.get("mmproj") and os.path.isfile(m["mmproj"]) and m.get("mmproj_sig") != sig(m["mmproj"]):
            kw["mmproj_sig"] = sig(m["mmproj"])
        if kw:
            core.SET.update_model(m["id"], **kw)
    return rep


def title_of(m, models=()):
    """Nombre del modelo para los avisos; con la variante si hay otro con el mismo nombre (p. ej. dos cuantizaciones)."""
    from . import core
    t = core.model_title(m) or m.get("name", "") or os.path.basename(m.get("path", ""))
    if sum(1 for x in models if (core.model_title(x) or x.get("name", "")) == t) > 1 and core.model_quant(m):
        t += " · " + core.model_quant(m)
    return t


def relink(mid, path):
    """El usuario indicó a mano dónde está ahora el modelo. Devuelve un texto de error o ""."""
    from . import core
    m = next((x for x in core.SET.snapshot()["models"] if x.get("id") == mid), None)
    if not m:
        return tr("Ese modelo ya no está en la lista.")
    try:
        with open(path, "rb") as f:
            gguf_ok = f.read(4) == b"GGUF"
    except OSError:
        gguf_ok = False
    if not gguf_ok:
        return tr("Ese archivo no es un modelo GGUF válido (o todavía se está copiando).")
    if not all(os.path.isfile(x) for x in split_parts(path)):
        return tr("Faltan partes del modelo junto a ese archivo (%s).") % os.path.basename(split_parts(path)[-1])
    kw = {"path": path, "file": os.path.basename(path), "path_sig": sig(path)}
    if m.get("mmproj") and not os.path.isfile(m["mmproj"]):
        folder = os.path.dirname(path)
        cand = [x for x in [os.path.join(folder, os.path.basename(m["mmproj"]))] + _mmproj_in(folder) if os.path.isfile(x)]
        if cand:
            kw.update(mmproj=cand[0], mmproj_sig=sig(cand[0]))
    core.SET.update_model(mid, **kw)
    return ""


def problems(cfg):
    """Modelos de la lista a los que les falta algún archivo (rápido: solo mira si existen)."""
    return [m for m in cfg.get("models", []) if not files_ok(m) or (m.get("mmproj") and not os.path.isfile(m["mmproj"]))]


def summary(rep):
    """Lo que se arregló, en una o dos frases (o "" si no hubo nada que contar)."""
    out = []
    fx = rep.get("fixed") or []
    if len(fx) == 1:
        out.append(tr("Encontré «%s» en su nueva carpeta (%s) y lo actualicé.") % (fx[0][0], os.path.dirname(fx[0][1])))
    elif fx:
        out.append(tr("Encontré %d modelos que habías movido y los actualicé.") % len(fx))
    for t, p in rep.get("vision") or []:
        out.append(tr("Encontré el proyector de visión de «%s» en %s.") % (t, os.path.dirname(p)))
    if rep.get("models_dir"):
        out.append(tr("Las próximas descargas irán a %s, donde están ahora tus modelos.") % rep["models_dir"])
    ad = rep.get("added") or []
    if ad:
        out.append((tr("Añadí «%s», que estaba en tu carpeta de modelos.") % ad[0]) if len(ad) == 1 else
                   tr("Añadí %d modelos que estaban en tu carpeta de modelos: %s.") % (len(ad), ", ".join(ad)))
    for t in rep.get("lost_vision") or []:
        out.append(tr("«%s» quedó sin visión: su proyector (mmproj) no estaba junto a él.") % t)
    return " ".join(out)


def pending_text(rep):
    """Lo que sigue sin resolverse, explicado."""
    out = []
    for t, _ in rep.get("copying") or []:
        out.append(tr("«%s» todavía se está copiando; lo enlazaré en cuanto termine.") % t)
    for t, d in rep.get("offline") or []:
        out.append(tr("«%s» está en el disco %s, que no está conectado. Conéctalo y volverá a funcionar sin hacer nada más.") % (t, d))
    ms = rep.get("missing") or []
    if ms:
        out.append(tr("No encuentro «%s» en ningún disco. Si lo tienes en otro sitio, indícalo en Modelos → Localizar…; "
                      "si lo borraste, quítalo de la lista.") % ms[0] if len(ms) == 1 else
                   tr("No encuentro %d modelos en ningún disco (%s). Si lo tienes en otro sitio, indícalo en Modelos → "
                      "Localizar…; si lo borraste, quítalo de la lista.") % (len(ms), ", ".join(ms)))
    return " ".join(out)
