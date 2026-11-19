"""Descargas de llama.cpp (GitHub oficial) y de modelos GGUF (Hugging Face).
Reanudables (.part + HTTP Range), con reintentos y verificacion SHA-256 cuando la fuente la publica."""
import os, re, json, time, hashlib, zipfile, platform, threading, subprocess, http.client, urllib.request, urllib.error, urllib.parse
from . import osys

UA = {"User-Agent": "Jayth (+python-urllib)"}
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


_JUNK = re.compile(r"(?i)[-_. ](?:UD[-_])?(?:I?Q\d(?:_[A-Z0-9]+)*|BF16|F16|F32|FP16|FP8|MXFP4\w*|GGUF|imatrix|i1|hf)(?=$|[-_. ])")
_WORDS = {"it": "IT", "qat": "QAT", "vl": "VL", "moe": "MoE", "gpt": "GPT", "oss": "OSS", "dpo": "DPO", "sft": "SFT"}


def pretty_name(text):
    """Nombre legible de un modelo: 'unsloth/Qwen3.8-27B-GGUF' o 'Qwen3.8-27B-UD-Q4_K_S.gguf' -> 'Qwen3.8 27B'.
    Conserva familia, versión, tamaño y variantes (Instruct, Coder, Flash, Thinking…); quita cuantización y extensiones."""
    base = str(text or "").split(" · ")[0].replace("\\", "/").split("/")[-1]
    base = re.sub(r"(?i)\.gguf$", "", base)
    base = re.sub(r"-\d{5}-of-\d{5}$", "", base)
    prev = None
    while prev != base:
        prev = base
        base = _JUNK.sub("", base)
    out = []
    for p in re.split(r"[-_ ]+", base):
        if not p:
            continue
        low = p.lower()
        if low in _WORDS:
            p = _WORDS[low]
        elif re.fullmatch(r"\d+(\.\d+)?[bmk]", low):
            p = p[:-1] + p[-1].upper()           # 27b -> 27B
        elif re.fullmatch(r"[ae]\d+(\.\d+)?b", low):
            p = p.upper()                         # a3b -> A3B (expertos activos)
        elif p.islower() and len(p) > 2:
            p = p.capitalize()                    # instruct -> Instruct
        out.append(p)
    return " ".join(out) or str(text)


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
_ARM = platform.machine().lower() in ("arm64", "aarch64")
if osys.WIN:
    _A = "arm64" if _ARM else "x64"
    LLAMA_PATTERNS = {
        "cpu": [r"llama-b\d+-bin-win-cpu-%s\.zip$" % _A],
        "cuda": [r"llama-b\d+-bin-win-cuda-12\.4-x64\.zip$", r"^cudart-llama-bin-win-cuda-12\.4-x64\.zip$"],
        "vulkan": [r"llama-b\d+-bin-win-vulkan-x64\.zip$"],
    }
elif osys.MAC:
    # las compilaciones de macOS para arm64 ya llevan Metal
    LLAMA_PATTERNS = {"metal": [r"llama-b\d+-bin-macos-arm64\.(tar\.gz|zip)$"], "cpu": [r"llama-b\d+-bin-macos-%s\.(tar\.gz|zip)$" % ("arm64" if _ARM else "x64")]}
else:
    LLAMA_PATTERNS = {
        "cpu": [r"llama-b\d+-bin-ubuntu-%s\.(tar\.gz|zip)$" % ("arm64" if _ARM else "x64")],
        "cuda": [r"llama-b\d+-bin-ubuntu-cuda-12\.\d+-x64\.(tar\.gz|zip)$", r"^cudart-llama(-b\d+)?-bin-ubuntu-cuda-12\.\d+-x64\.(tar\.gz|zip)$"],
        "vulkan": [r"llama-b\d+-bin-ubuntu-vulkan-x64\.(tar\.gz|zip)$"],
    }


def llama_release(backend):
    """Ultima compilacion oficial de llama.cpp para este sistema con los archivos del motor elegido."""
    if backend not in LLAMA_PATTERNS:
        raise RuntimeError("El motor «%s» no está disponible en %s." % (backend, osys.os_label()))
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
    raise RuntimeError("No encontré una versión de llama.cpp para %s (%s)." % (osys.os_label(), backend))


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


def extract_archive(path, dest):
    """Descomprime .zip o .tar.gz sin permitir rutas fuera de dest; conserva permisos y enlaces (bibliotecas de macOS/Linux)."""
    if path.lower().endswith(".zip"):
        return extract_zip(path, dest)
    import tarfile
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(path) as t:
        root = os.path.abspath(dest)
        for m in t.getmembers():
            target = os.path.abspath(os.path.join(dest, m.name))
            if not (target == root or target.startswith(root + os.sep)):
                raise RuntimeError("Ruta peligrosa en el paquete: " + m.name)
        try:
            t.extractall(dest, filter="tar")         # Python 3.12+: bloquea rutas absolutas y enlaces hacia fuera
        except TypeError:
            t.extractall(dest)


def find_server(folder):
    name = osys.exe("llama-server")
    for root, _, files in os.walk(folder):
        if name in files:
            exe = os.path.join(root, name)
            if not osys.WIN:
                try:
                    os.chmod(exe, os.stat(exe).st_mode | 0o755)
                    if osys.MAC:                    # por si llego con cuarentena (descarga desde el navegador)
                        subprocess.run(["xattr", "-dr", "com.apple.quarantine", folder], capture_output=True)
                except OSError:
                    pass
            return exe
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
