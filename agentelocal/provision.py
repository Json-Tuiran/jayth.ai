"""Descargas de llama.cpp (GitHub oficial) y de modelos GGUF (Hugging Face).
Reanudables (.part + HTTP Range), con reintentos y verificacion SHA-256 cuando la fuente la publica."""
import os, re, json, time, hashlib, zipfile, threading, http.client, urllib.request, urllib.error, urllib.parse

UA = {"User-Agent": "AgenteLocal/0.1 (+python-urllib)"}
CHUNK = 1 << 20

# Modelos sugeridos en el asistente. Cualquier otro repositorio GGUF de Hugging Face tambien sirve.
CATALOG = [
    {"name": "Qwen3.8-27B", "repo": "unsloth/Qwen3.8-27B-GGUF",
     "desc": "Multimodal (texto e imagen), muy capaz en código y tareas de agente. 27B parámetros."},
]


class Cancelled(Exception):
    pass


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=dict(UA, Accept="application/json"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- Hugging Face
QUANT_RE = re.compile(r"((?:UD-)?(?:IQ\d_[A-Z0-9_]+|Q\d_K(?:_[A-Z]+)?|Q\d_\d|Q\d_K_[A-Z]+|BF16|F16|F32|MXFP4\w*))", re.I)
SPLIT_RE = re.compile(r"^(.*)-(\d{5})-of-(\d{5})\.gguf$", re.I)


def quant_label(fname):
    m = QUANT_RE.search(os.path.basename(fname))
    return m.group(1).upper() if m else os.path.basename(fname)


def hf_files(repo):
    """Lista los GGUF de un repo. Agrupa los archivos divididos (-00001-of-0000N) en una sola entrada."""
    repo = repo.strip().strip("/")
    if repo.startswith("https://huggingface.co/"):
        repo = "/".join(repo.split("/")[3:5])
    tree = get_json("https://huggingface.co/api/models/%s/tree/main?recursive=true" % repo)
    groups, mmproj = {}, []
    for t in tree:
        p = t.get("path", "")
        if t.get("type") != "file" or not p.lower().endswith(".gguf") or "imatrix" in p.lower():
            continue
        lfs = t.get("lfs") or {}
        f = {"file": p, "size": int(lfs.get("size") or t.get("size") or 0), "sha256": lfs.get("oid") or ""}
        if "mmproj" in os.path.basename(p).lower():
            mmproj.append(f)
            continue
        m = SPLIT_RE.match(p)
        key = m.group(1) if m else p
        g = groups.setdefault(key, {"file": p, "size": 0, "parts": []})
        g["parts"].append(f)
        g["size"] += f["size"]
    quants = []
    for g in groups.values():
        g["parts"].sort(key=lambda x: x["file"])
        g["file"] = g["parts"][0]["file"]
        g["sha256"] = g["parts"][0]["sha256"] if len(g["parts"]) == 1 else ""
        folder = os.path.dirname(g["file"])
        # un GGUF suelto dentro de una subcarpeta suele ser un modelo auxiliar (p. ej. MTP/borrador), no una cuantizacion
        g["aux"] = bool(folder) and len(g["parts"]) == 1
        g["label"] = (folder + "/" if g["aux"] else "") + quant_label(g["file"]) + (" (%d partes)" % len(g["parts"]) if len(g["parts"]) > 1 else "")
        quants.append(g)
    quants.sort(key=lambda q: q["size"])
    mmproj.sort(key=lambda f: (0 if "f16" in f["file"].lower() and "bf16" not in f["file"].lower() else 1, f["size"]))
    return {"repo": repo, "quants": quants, "mmproj": mmproj}


def hf_url(repo, file):
    return "https://huggingface.co/%s/resolve/main/%s" % (repo, urllib.parse.quote(file))


# ---------------------------------------------------------------- llama.cpp
LLAMA_PATTERNS = {
    "cpu": [r"llama-b\d+-bin-win-cpu-x64\.zip$"],
    "cuda": [r"llama-b\d+-bin-win-cuda-12\.4-x64\.zip$", r"^cudart-llama-bin-win-cuda-12\.4-x64\.zip$"],
    "vulkan": [r"llama-b\d+-bin-win-vulkan-x64\.zip$"],
}


def llama_release(backend):
    """Ultima compilacion oficial de llama.cpp para Windows con los archivos del motor elegido."""
    pats = LLAMA_PATTERNS[backend]
    for rel in get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"):
        if rel.get("draft"):
            continue
        assets = []
        for p in pats:
            a = next((a for a in rel.get("assets", []) if re.search(p, a["name"])), None)
            if not a:
                break
            dig = (a.get("digest") or "")
            assets.append({"name": a["name"], "url": a["browser_download_url"], "size": a["size"],
                           "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else ""})
        if len(assets) == len(pats):
            return {"tag": rel["tag_name"], "assets": assets}
    raise RuntimeError("No encontré una versión de llama.cpp para Windows (%s)." % backend)


# ---------------------------------------------------------------- descarga generica
def sha256_file(path, progress=None, stop=None):
    h, done, total = hashlib.sha256(), 0, os.path.getsize(path)
    with open(path, "rb") as f:
        while True:
            if stop is not None and stop.is_set():
                raise Cancelled()
            b = f.read(8 * CHUNK)
            if not b:
                break
            h.update(b)
            done += len(b)
            if progress:
                progress(done, total, "verificando")
    return h.hexdigest()


def download(url, dest, size=0, sha256="", progress=None, stop=None, retries=8):
    """Descarga url -> dest. Reanuda desde dest.part. progress(hecho, total, fase)."""
    if os.path.isfile(dest) and (not size or os.path.getsize(dest) == size):
        if progress:
            progress(size or os.path.getsize(dest), size or os.path.getsize(dest), "ya descargado")
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part = dest + ".part"
    attempt = 0
    while True:
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if size and have >= size:
            break
        hdr = dict(UA)
        if have:
            hdr["Range"] = "bytes=%d-" % have
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60) as r:
                if have and r.status != 206:
                    have = 0      # el servidor no admite reanudar: empezar de cero
                total = size or (have + int(r.headers.get("Content-Length") or 0))
                with open(part, "ab" if have else "wb") as f:
                    done = have
                    while True:
                        if stop is not None and stop.is_set():
                            raise Cancelled()
                        b = r.read(CHUNK)
                        if not b:
                            break
                        f.write(b)
                        done += len(b)
                        if progress:
                            progress(done, total, "descargando")
            if not size:
                break
            if os.path.getsize(part) >= size:
                break
            raise IOError("conexión cortada")
        except Cancelled:
            raise
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, IOError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                raise RuntimeError("No se puede descargar (%s): %s" % (e.code, url))
            if isinstance(e, urllib.error.HTTPError) and e.code == 416:   # rango invalido: ya estaba completo
                break
            attempt += 1
            if attempt > retries:
                raise RuntimeError("Falló la descarga tras %d intentos: %s" % (retries, e))
            if progress:
                progress(have, size or have, "reintentando (%d/%d)…" % (attempt, retries))
            for _ in range(min(30, 2 ** attempt)):
                if stop is not None and stop.is_set():
                    raise Cancelled()
                time.sleep(1)
    if size and os.path.getsize(part) != size:
        raise RuntimeError("Tamaño incorrecto tras descargar %s" % os.path.basename(dest))
    if sha256:
        got = sha256_file(part, progress, stop)
        if got.lower() != sha256.lower():
            os.remove(part)
            raise RuntimeError("La verificación SHA-256 falló para %s; se borró el archivo dañado." % os.path.basename(dest))
    os.replace(part, dest)
    return dest


def extract_zip(zpath, dest):
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = os.path.abspath(os.path.join(dest, m.filename))
            if not target.startswith(os.path.abspath(dest) + os.sep) and target != os.path.abspath(dest):
                raise RuntimeError("Ruta peligrosa en el zip: " + m.filename)
        z.extractall(dest)


def find_server(folder):
    for root, _, files in os.walk(folder):
        if "llama-server.exe" in files:
            return os.path.join(root, "llama-server.exe")
    return ""


# ---------------------------------------------------------------- trabajos con progreso (para la interfaz)
class Job:
    """Ejecuta pasos en un hilo; la interfaz lee self.steps periodicamente."""

    def __init__(self):
        self.steps = []
        self.stop = threading.Event()
        self.thread = None
        self.error = None
        self.finished = False
        self.result = {}

    def add(self, label, fn):
        self.steps.append({"label": label, "fn": fn, "status": "pending", "done": 0, "total": 0, "phase": "", "speed": 0.0})

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def cancel(self):
        self.stop.set()

    def _run(self):
        try:
            for st in self.steps:
                st["status"] = "running"
                t0, last = [time.time(), 0], [0]

                def prog(done, total, phase, st=st):
                    now = time.time()
                    if phase == "descargando" and now - t0[0] > 1:
                        st["speed"] = (done - last[0]) / (now - t0[0])
                        t0[0], last[0] = now, done
                    elif phase != "descargando":
                        st["speed"] = 0.0
                    if not last[0]:
                        last[0] = done
                    st["done"], st["total"], st["phase"] = done, total, phase
                st["fn"](prog, self.stop, self.result)
                st["status"] = "done"
                st["phase"] = "listo"
        except Cancelled:
            for st in self.steps:
                if st["status"] == "running":
                    st["status"] = "cancelled"
            self.error = "Cancelado. Lo descargado se conserva y se reanudará la próxima vez."
        except Exception as e:
            for st in self.steps:
                if st["status"] == "running":
                    st["status"] = "error"
            self.error = str(e)
        finally:
            self.finished = True
