# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Conocimiento local: el agente busca por significado dentro de las carpetas que elige el usuario (notas, documentos,
proyectos) sin tener que leerlas enteras, algo clave con los contextos pequeños de los modelos locales.

- Un modelo de embeddings pequeño (Qwen3-Embedding 0.6B, Apache-2.0, multilingüe) servido por el mismo llama.cpp
  (llama-server --embedding) en un puerto aparte, solo mientras hace falta (se apaga solo al rato).
- Índice en SQLite (biblioteca estándar) dentro de la carpeta de datos: fragmentos de ~1200 caracteres con su archivo y
  línea, y su vector (los primeros 384 valores, renormalizados: el modelo los admite, MRL) para buscar rápido sin numpy.
- Al actualizar solo se vuelven a leer los archivos que cambiaron."""
import os, re, json, time, math, array, socket, sqlite3, threading, subprocess, urllib.request
from . import osys, paths, core, provision as P
from .i18n import tr

EMB = {"repo": "Qwen/Qwen3-Embedding-0.6B-GGUF", "file": "Qwen3-Embedding-0.6B-Q8_0.gguf", "size": 639150592,
       "sha256": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"}
DIMS = 384
DB = os.path.join(paths.DATA, "conocimiento.sqlite3")
TASK = "Given a question or topic, retrieve passages from the user's files that help answer it"
CHUNK, OVERLAP = 1200, 150
MAX_TEXT = 3_000_000              # archivos de texto más grandes no se indexan (registros, volcados)
TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".tex", ".org", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".csv", ".tsv", ".html",
            ".htm", ".css", ".scss", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".sql",
            ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".sh", ".ps1", ".bat", ".lua", ".r", ".m", ".vue", ".svelte", ".dart"}
DOC_EXT = {".docx", ".pdf", ".pptx", ".xlsx"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target", ".idea", ".vscode", "env"}


def model_path(cfg=None):
    return os.path.join((cfg or core.SET.snapshot()).get("models_dir") or paths.MODELS_DEFAULT, "conocimiento", EMB["file"])


def installed(cfg=None):
    p = model_path(cfg)
    return os.path.isfile(p) and os.path.getsize(p) == EMB["size"]


def folders(cfg=None):
    return [f for f in (cfg or core.SET.snapshot()).get("knowledge_folders") or [] if f]


def ready(cfg=None):
    """¿Puede buscar ya? (modelo instalado, carpetas elegidas e índice con algo dentro)"""
    cfg = cfg or core.SET.snapshot()
    return installed(cfg) and bool(folders(cfg)) and stats()["chunks"] > 0


JOB = None


def install(cfg=None):
    """Descarga el modelo de búsqueda (provision.Job)."""
    global JOB
    cfg = cfg or core.SET.snapshot()
    if JOB is not None and not JOB.finished:
        return JOB
    job = P.Job()
    job.add(tr("Buscador por significado (Qwen3-Embedding 0.6B)"),
            lambda progress, stop, result: P.download(P.hf_url(EMB["repo"], EMB["file"]), model_path(cfg), EMB["size"], EMB["sha256"], progress, stop),
            EMB["size"])
    job.start()
    JOB = job
    return job


# ---------------------------------------------------------------- motor de embeddings (llama-server aparte)
class Engine:
    def __init__(self):
        self.proc, self.port, self.last = None, 0, 0.0
        self.lock = threading.Lock()

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, cfg):
        if self.alive():
            return
        exe = cfg.get("llama_exe") or ""
        if not os.path.isfile(exe):
            raise RuntimeError(tr("No encuentro llama-server: configúralo en Ajustes › Rendimiento."))
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        threads = str(max(1, int(cfg.get("threads") or 2) // 2))       # que no le quite todo el procesador al modelo principal
        cmd = [exe, "-m", model_path(cfg), "--embedding", "--pooling", "last", "--host", "127.0.0.1", "--port", str(self.port),
               "-c", "8192", "-b", "8192", "-ub", "8192", "-t", threads, "--no-warmup", "-np", "1"]
        env = dict(os.environ)
        if osys.LINUX:
            env["LD_LIBRARY_PATH"] = os.path.dirname(exe) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
        elif osys.MAC:
            env["DYLD_LIBRARY_PATH"] = os.path.dirname(exe) + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                     cwd=os.path.dirname(exe), env=env, **osys.popen_kwargs())
        t0 = time.time()
        while time.time() - t0 < 120:
            if self.proc.poll() is not None:
                raise RuntimeError(tr("El buscador por significado no arrancó (código %s).") % self.proc.returncode)
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/health" % self.port, timeout=2) as r:
                    if json.loads(r.read().decode()).get("status") == "ok":
                        break
            except Exception:
                time.sleep(0.4)
        threading.Thread(target=self._idle, daemon=True).start()

    def _idle(self):
        while self.alive():                       # se apaga solo tras 3 minutos sin usarse (libera ~1 GB)
            time.sleep(10)
            if time.time() - self.last > 180:
                self.stop()

    def stop(self):
        if self.alive():
            osys.kill_tree(self.proc.pid)
        self.proc = None

    def embed(self, cfg, texts):
        """Vectores (DIMS valores, longitud 1) de cada texto."""
        with self.lock:
            self.start(cfg)
            self.last = time.time()
            body = json.dumps({"input": texts, "model": "emb"}).encode()
            req = urllib.request.Request("http://127.0.0.1:%d/v1/embeddings" % self.port, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read().decode())["data"]
            self.last = time.time()
        out = []
        for d in sorted(data, key=lambda x: x.get("index", 0)):
            v = d["embedding"][:DIMS]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append(array.array("f", (x / n for x in v)))
        return out


ENGINE = Engine()


# ---------------------------------------------------------------- índice
def _db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, chunks INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, path TEXT, line INTEGER, text TEXT, vec BLOB)")
    c.execute("CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path)")
    return c


def stats():
    try:
        c = _db()
        n_files = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        n_chunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        c.close()
        return {"files": n_files, "chunks": n_chunks}
    except Exception:
        return {"files": 0, "chunks": 0}


def read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in DOC_EXT:
        from . import harness
        return harness.read_document(path, 400_000)
    with open(path, "rb") as f:
        raw = f.read(MAX_TEXT + 1)
    if len(raw) > MAX_TEXT or b"\0" in raw[:4096]:
        return ""
    return raw.decode("utf-8", "replace")


def chunks_of(text):
    """[(línea, texto)] en trozos de ~CHUNK caracteres, cortando por párrafos o líneas cuando se puede."""
    out, i, n = [], 0, len(text)
    while i < n:
        end = min(n, i + CHUNK)
        if end < n:
            cut = max(text.rfind("\n\n", i + CHUNK // 2, end), text.rfind("\n", i + CHUNK // 2, end))
            end = cut + 1 if cut > i else end
        piece = text[i:end].strip()
        if piece:
            out.append((text.count("\n", 0, i) + 1, piece))
        if end >= n:
            break
        i = max(i + 1, end - OVERLAP)
    return out


def walk(cfg=None):
    """Archivos que entran en el índice."""
    for root_dir in folders(cfg):
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if (ext in TEXT_EXT or ext in DOC_EXT) and not f.startswith("~$"):
                    yield os.path.join(root, f)


class Cancelled(Exception):
    pass


def index(cfg=None, progress=None, stop=None):
    """Actualiza el índice: lee solo lo nuevo o cambiado y olvida lo que ya no existe. Devuelve el resumen."""
    cfg = cfg or core.SET.snapshot()
    if not installed(cfg):
        raise RuntimeError(tr("Primero instala el buscador por significado."))
    c = _db()
    known = {p: (m, s) for p, m, s in c.execute("SELECT path, mtime, size FROM files")}
    files = list(walk(cfg))
    seen, todo = set(files), []
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if known.get(p) != (st.st_mtime, st.st_size):
            todo.append((p, st.st_mtime, st.st_size))
    gone = [p for p in known if p not in seen]
    for p in gone:
        c.execute("DELETE FROM chunks WHERE path=?", (p,))
        c.execute("DELETE FROM files WHERE path=?", (p,))
    c.commit()
    added = 0
    for k, (p, mt, sz) in enumerate(todo):
        if stop is not None and stop.is_set():
            c.close()
            raise Cancelled()
        if progress:
            progress(k, len(todo), os.path.basename(p))
        try:
            parts = chunks_of(read_text(p))
        except Exception:
            parts = []
        vecs = []
        for b in range(0, len(parts), 16):
            vecs += ENGINE.embed(cfg, [t for _, t in parts[b:b + 16]])
        c.execute("DELETE FROM chunks WHERE path=?", (p,))
        c.executemany("INSERT INTO chunks (path, line, text, vec) VALUES (?,?,?,?)",
                      [(p, ln, t, v.tobytes()) for (ln, t), v in zip(parts, vecs)])
        c.execute("INSERT OR REPLACE INTO files (path, mtime, size, chunks) VALUES (?,?,?,?)", (p, mt, sz, len(parts)))
        c.commit()
        added += len(parts)
    c.close()
    _CACHE.clear()
    s = stats()
    core.SET.update({"knowledge_indexed": time.strftime("%Y-%m-%d %H:%M")})
    return dict(s, updated=len(todo), removed=len(gone), added=added)


_CACHE = {}


def _vectors():
    if "rows" not in _CACHE:
        c = _db()
        rows = []
        for i, path, line, vec in c.execute("SELECT id, path, line, vec FROM chunks"):
            a = array.array("f")
            a.frombytes(vec)
            rows.append((i, path, line, a))
        c.close()
        _CACHE["rows"] = rows
    return _CACHE["rows"]


def search(query, k=6, cfg=None):
    """Los k fragmentos más parecidos: [{'path', 'line', 'text', 'score'}]."""
    cfg = cfg or core.SET.snapshot()
    q = ENGINE.embed(cfg, ["Instruct: %s\nQuery:%s" % (TASK, query)])[0]
    scored = []
    for i, path, line, v in _vectors():
        scored.append((sum(a * b for a, b in zip(q, v)), i, path, line))
    scored.sort(reverse=True)
    best = scored[:max(1, int(k))]
    c = _db()
    out = []
    for sc, i, path, line in best:
        t = c.execute("SELECT text FROM chunks WHERE id=?", (i,)).fetchone()
        out.append({"path": path, "line": line, "text": t[0] if t else "", "score": round(sc, 3)})
    c.close()
    return out


INDEX_JOB = None


def start_index(cfg=None, done=None):
    """Actualiza el índice en segundo plano (INDEX_JOB guarda el avance para la interfaz)."""
    global INDEX_JOB
    if INDEX_JOB is not None and INDEX_JOB.get("running"):
        return INDEX_JOB
    job = {"running": True, "text": tr("Buscando archivos…"), "error": "", "result": None, "stop": threading.Event()}
    INDEX_JOB = job

    def prog(i, n, name):
        job["text"] = tr("Leyendo %d de %d: %s") % (i + 1, n, name)

    def run():
        try:
            job["result"] = index(cfg, prog, job["stop"])
        except Cancelled:
            job["error"] = tr("Cancelado.")
        except Exception as e:
            job["error"] = str(e) or type(e).__name__
        job["running"] = False
        if done:
            done(job)
    threading.Thread(target=run, daemon=True).start()
    return job
