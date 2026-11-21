# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Imágenes creadas en el propio equipo con stable-diffusion.cpp (github.com/leejet/stable-diffusion.cpp, licencia MIT).

Funciona como llama.cpp: la primera vez que el usuario lo instala, Jayth descarga la compilación oficial adecuada para
su equipo (CPU, Vulkan, CUDA o Metal) y un modelo de imagen de licencia libre. Después todo funciona sin internet.

Solo se usa cuando el modelo de texto activo no genera imágenes por sí mismo (native_image_output): hoy ninguno de los
que ejecuta llama.cpp lo hace, pero si llega a hacerlo, el agente usará el del propio modelo y no este motor aparte.
"""
import os, re, sys, time, json, random, shutil, platform, threading, subprocess, queue
from . import osys, paths, provision as P
from .i18n import tr

GB = 1024 ** 3
REPO = "leejet/stable-diffusion.cpp"
LOG = os.path.join(paths.DATA, "imagen.log")

# ---------------------------------------------------------------- modelos (todos con licencia Apache-2.0)
# El codificador de texto (Qwen3 4B) es el mismo para los dos: se descarga una sola vez y lo comparten.
_QWEN3_4B = {"role": "llm", "repo": "unsloth/Qwen3-4B-GGUF", "file": "Qwen3-4B-Q4_K_M.gguf", "size": 2497281312,
             "sha256": "f6f851777709861056efcdad3af01da38b31223a3ba26e61a4f8bf3a2195813a", "shared": True}
MODELS = [
    {"id": "flux2-klein-4b", "name": "FLUX.2 [klein] 4B", "lab": "Black Forest Labs", "license": "Apache-2.0",
     "desc": tr("Rápido y versátil: fotos, ilustraciones, logotipos y texto dentro de la imagen. También modifica imágenes que ya tienes."),
     "files": [{"role": "diffusion", "repo": "leejet/FLUX.2-klein-4B-GGUF", "file": "flux-2-klein-4b-Q4_0.gguf", "size": 2460378560,
                "sha256": "d1023499ef3f2f82ff7c50e6778495195c1b6cc34835741778868428111f9ff4"},
               _QWEN3_4B,
               {"role": "vae", "repo": "Comfy-Org/Flux-2-Klein-4B", "file": "split_files/vae/flux2-vae.safetensors", "size": 336211292,
                "sha256": "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3"}],
     "steps": 4, "cfg": 1.0, "edit": True},
    {"id": "z-image-turbo", "name": "Z-Image Turbo", "lab": "Alibaba (Tongyi)", "license": "Apache-2.0",
     "desc": tr("Fotos muy realistas y buen texto dentro de la imagen. Más pesado: va mejor con tarjeta gráfica."),
     "files": [{"role": "diffusion", "repo": "leejet/Z-Image-Turbo-GGUF", "file": "z_image_turbo-Q4_K.gguf", "size": 3864250304,
                "sha256": "14b375ab4f226bc5378f68f37e899ef3c2242b8541e61e2bc1aff40976086fbd"},
               _QWEN3_4B,
               {"role": "vae", "repo": "Comfy-Org/Z-Image-Turbo", "file": "split_files/vae/ae.safetensors", "size": 335304388,
                "sha256": "afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38"}],
     "steps": 8, "cfg": 1.0, "edit": False},
]
DEFAULT_MODEL = MODELS[0]["id"]
ROLE_TXT = {"diffusion": tr("modelo de imagen"), "llm": tr("lector de la descripción"), "vae": tr("decodificador")}

# arquitecturas GGUF que generan imágenes por sí mismas con llama.cpp: hoy ninguna. Si llega alguna, se añade aquí y,
# con ese modelo activo, el agente deja de usar este motor aparte.
NATIVE_IMAGE_ARCH = set()


def model(cfg, mid=None):
    mid = mid or (cfg or {}).get("image_model") or DEFAULT_MODEL
    return next((m for m in MODELS if m["id"] == mid), MODELS[0])


def total_size(m):
    return sum(f["size"] for f in m["files"])


def native_image_output(cfg):
    """True si el modelo de texto activo genera imágenes por sí mismo (entonces no hace falta este motor)."""
    if (cfg or {}).get("llm_mode") == "external":
        return False
    try:
        from . import core
        c = core.model_caps(core.active_model(cfg), compute=False) or {}
    except Exception:
        return False
    return c.get("arch", "") in NATIVE_IMAGE_ARCH


# ---------------------------------------------------------------- motor (stable-diffusion.cpp)
_ARM = platform.machine().lower() in ("arm64", "aarch64")
if osys.WIN and not _ARM:
    PATTERNS = {"cpu": [r"-bin-win-cpu-x64\.zip$"], "vulkan": [r"-bin-win-vulkan-x64\.zip$"],
                "cuda": [r"-bin-win-cuda12-x64\.zip$", r"^cudart-sd-bin-win-cu12-x64\.zip$"]}
elif osys.MAC and _ARM:
    PATTERNS = {"metal": [r"-bin-Darwin-macOS-[\d.]+-arm64\.zip$"]}      # Apple Silicon: con Metal
elif osys.LINUX and not _ARM:
    PATTERNS = {"cpu": [r"-bin-Linux-Ubuntu-[\d.]+-x86_64\.zip$"], "vulkan": [r"-bin-Linux-Ubuntu-[\d.]+-x86_64-vulkan\.zip$"]}
else:
    PATTERNS = {}                                    # Windows/Linux ARM y Mac Intel: no hay compilación oficial


def available():
    return bool(PATTERNS)


def backend(cfg):
    """Motor de imágenes que corresponde al de llama.cpp elegido (en Linux no hay CUDA oficial: se usa Vulkan)."""
    b = (cfg or {}).get("backend") or "cpu"
    if b == "cuda" and "cuda" not in PATTERNS:
        b = "vulkan"
    if b not in PATTERNS:
        b = "cpu" if "cpu" in PATTERNS else next(iter(PATTERNS), None)
    return b


def engine_dir(b):
    return os.path.join(paths.RUNTIME_DIR, "imagen", b)


def find_cli(folder):
    for name in (osys.exe("sd-cli"), osys.exe("sd")):          # «sd» en las versiones antiguas
        for root, _, files in os.walk(folder):
            if name in files:
                exe = os.path.join(root, name)
                if not osys.WIN:
                    try:
                        os.chmod(exe, os.stat(exe).st_mode | 0o755)
                        if osys.MAC:
                            subprocess.run(["xattr", "-dr", "com.apple.quarantine", folder], capture_output=True)
                    except OSError:
                        pass
                return exe
    return ""


def engine_exe(cfg):
    b = backend(cfg)
    d = engine_dir(b) if b else ""
    return find_cli(d) if d and os.path.isdir(d) else ""


def engine_argv(cfg):
    """Orden para lanzar el motor (las pruebas la sustituyen por un motor simulado)."""
    exe = engine_exe(cfg)
    return [exe] if exe else []


def release(b):
    """Última compilación oficial de stable-diffusion.cpp con los archivos del motor elegido."""
    pats = PATTERNS.get(b)
    if not pats:
        raise RuntimeError(tr("El generador de imágenes no está disponible para %s.") % osys.os_label())
    for rel in P.get_json("https://api.github.com/repos/%s/releases?per_page=10" % REPO):
        if rel.get("draft"):
            continue
        assets = []
        for p in pats:
            a = next((a for a in rel.get("assets", []) if re.search(p, a["name"])), None)
            if not a:
                break
            dig = a.get("digest") or ""
            assets.append({"name": a["name"], "url": a["browser_download_url"], "size": a["size"],
                           "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else ""})
        if len(assets) == len(pats):
            return {"tag": rel["tag_name"], "assets": assets}
    raise RuntimeError(tr("No encontré una versión del generador de imágenes para %s (%s).") % (osys.os_label(), b))


# ---------------------------------------------------------------- archivos del modelo
def model_root(cfg):
    return os.path.join((cfg or {}).get("models_dir") or paths.MODELS_DEFAULT, "imagen")


def file_path(cfg, m, f):
    return os.path.join(model_root(cfg), "comun" if f.get("shared") else m["id"], os.path.basename(f["file"]))


def missing(cfg, m):
    """Archivos del modelo que faltan o están incompletos."""
    out = []
    for f in m["files"]:
        p = file_path(cfg, m, f)
        if not (os.path.isfile(p) and os.path.getsize(p) == f["size"]):
            out.append(f)
    return out


def status(cfg, mid=None):
    """{'engine': bool, 'model': bool, 'ready': bool, 'need': bytes por descargar, 'backend': …}"""
    m = model(cfg, mid)
    miss = missing(cfg, m)
    eng = bool(engine_argv(cfg))
    need = sum(f["size"] for f in miss) + (0 if eng else 40 * 1024 ** 2)
    if not eng and backend(cfg) == "cuda":
        need += 900 * 1024 ** 2                      # la versión CUDA trae las bibliotecas de NVIDIA (unos 900 MB)
    return {"engine": eng, "model": not miss, "ready": eng and not miss, "need": need, "backend": backend(cfg), "model_id": m["id"]}


def installed_models(cfg):
    return [m for m in MODELS if not missing(cfg, m)]


def remove(cfg, mid):
    """Borra los archivos de un modelo (el codificador compartido solo si ningún otro instalado lo usa). Devuelve bytes liberados."""
    m = model(cfg, mid)
    others = [o for o in installed_models(cfg) if o["id"] != m["id"]]
    used = {file_path(cfg, o, f) for o in others for f in o["files"]}
    freed = 0
    for f in m["files"]:
        p = file_path(cfg, m, f)
        if p in used:
            continue
        for q in (p, p + ".part", p + ".part.json"):
            if os.path.isfile(q):
                freed += os.path.getsize(q)
                try:
                    os.remove(q)
                except OSError:
                    pass
    d = os.path.join(model_root(cfg), m["id"])
    if os.path.isdir(d) and not os.listdir(d):
        os.rmdir(d)
    return freed


JOB = None          # instalación en curso: la comparten Ajustes y la tarjeta del chat


def installing():
    return JOB is not None and not JOB.finished


def install(cfg, mid=None):
    """Descarga lo que falte (motor y archivos del modelo) en segundo plano. Devuelve el trabajo (provision.Job)."""
    global JOB
    if installing():
        return JOB
    m = model(cfg, mid)
    job = P.Job()
    b = backend(cfg)
    if not engine_exe(cfg):
        def get_engine(progress, stop, result, b=b):
            rel = release(b)
            tmp = os.path.join(paths.RUNTIME_DIR, "imagen", "_descarga")
            os.makedirs(tmp, exist_ok=True)
            total = sum(a["size"] for a in rel["assets"])
            done = 0
            for a in rel["assets"]:
                z = os.path.join(tmp, a["name"])
                P.download(a["url"], z, a["size"], a["sha256"], lambda d, t, ph, base=done: progress(base + d, total, ph), stop)
                done += a["size"]
            dest = engine_dir(b)
            new = dest + "_nuevo"
            shutil.rmtree(new, ignore_errors=True)
            progress(total, total, "descomprimiendo")
            for a in rel["assets"]:
                P.extract_archive(os.path.join(tmp, a["name"]), new)
            if not find_cli(new):
                raise RuntimeError(tr("El paquete del generador de imágenes no trae sd-cli."))
            with open(os.path.join(new, "version.txt"), "w", encoding="utf-8") as fh:
                fh.write(rel["tag"])
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(new, dest)
            shutil.rmtree(tmp, ignore_errors=True)
        job.add(tr("Motor de imágenes (stable-diffusion.cpp, %s)") % b.upper(), get_engine, 900 * 1024 ** 2 if b == "cuda" else 30 * 1024 ** 2)
    for f in missing(cfg, m):
        def get_file(progress, stop, result, f=f):
            P.download(P.hf_url(f["repo"], f["file"]), file_path(cfg, m, f), f["size"], f["sha256"], progress, stop)
        job.add("%s · %s" % (m["name"], ROLE_TXT.get(f["role"], f["role"])), get_file, f["size"])
    job.start()
    JOB = job
    return job


# ---------------------------------------------------------------- memoria y tamaño
def need_bytes(m, w, h):
    """Memoria aproximada para generar: pesos + cálculo (crece con los píxeles)."""
    return total_size(m) + int(0.5 * GB + 1.5 * GB * (w * h) / (1024 * 1024))


def gpu(cfg):
    return backend(cfg) in ("cuda", "vulkan", "metal")


def base_side(cfg):
    s = str((cfg or {}).get("image_size") or "auto")
    if s.isdigit():
        return max(256, min(2048, int(s)))
    return 1024 if gpu(cfg) else 512                # sin tarjeta gráfica: 512 px tarda unas cuatro veces menos


ASPECTS = {"square": 1.0, "landscape": 16 / 9, "portrait": 9 / 16, "wide": 3 / 2, "tall": 2 / 3}
_ASPECT_ALIAS = {"cuadrada": "square", "horizontal": "landscape", "apaisada": "landscape", "vertical": "portrait",
                 "panoramica": "landscape", "panorámica": "landscape", "16:9": "landscape", "9:16": "portrait", "1:1": "square",
                 "3:2": "wide", "2:3": "tall", "4:3": "wide", "3:4": "tall"}


def _r64(x):
    return max(256, min(2048, int(round(x / 64.0)) * 64))


def pick_size(cfg, aspect="", width=0, height=0):
    """Ancho y alto en múltiplos de 64; sin medidas se usa la proporción con el lado base del equipo."""
    base = base_side(cfg)
    width, height = int(width or 0), int(height or 0)
    if width and height:
        w, h = _r64(width), _r64(height)
        limit = max(base, 1024) ** 2 * 1.5                   # no más de ~1,5 veces los píxeles de una imagen grande
        if w * h > limit:
            k = (limit / (w * h)) ** 0.5
            w, h = _r64(w * k), _r64(h * k)
        return w, h
    a = str(aspect or "square").lower().strip()
    ar = ASPECTS.get(_ASPECT_ALIAS.get(a, a), 1.0)
    return _r64(base * ar ** 0.5), _r64(base / ar ** 0.5)


# ---------------------------------------------------------------- progreso
_BAR = re.compile(r"\|\s*(\d+)/(\d+)\s*-\s*([\d.]+)\s*(s/it|it/s|[KMGT]?i?B/s)(?:\s*-\s*ETA\s*([\d:]+))?")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
PHASES = {"cargando": tr("Cargando el modelo de imagen"), "entendiendo": tr("Leyendo la descripción"), "dibujando": tr("Dibujando"),
          "terminando": tr("Terminando la imagen"), "preparando": tr("Preparando")}


def _eta(txt):
    parts = [int(x) for x in txt.split(":")]
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def parse_line(seg, st):
    """Actualiza st (fase, paso, pasos, eta) con un trozo de la salida del motor."""
    seg = _ANSI.sub("", seg).strip()
    if not seg:
        return
    m = _BAR.search(seg)
    if m:
        step, steps, val, unit = int(m.group(1)), int(m.group(2)), float(m.group(3)), m.group(4)
        if unit in ("s/it", "it/s"):
            spi = val if unit == "s/it" else (1.0 / val if val else 0)
            if st.get("phase") != "dibujando" or steps != st.get("steps"):
                st["sample_start"] = time.time()
            st.update(phase="dibujando", step=step, steps=steps, spi=spi)
            st["eta"] = _eta(m.group(5)) if m.group(5) else (steps - step) * spi
        elif st.get("phase") in (None, "preparando", "cargando"):
            st.update(phase="cargando", step=step, steps=steps)
        return
    low = seg.lower()
    st.setdefault("log", []).append(seg[:400])
    del st["log"][:-80]
    if st.get("phase") == "dibujando" and st.get("step") == st.get("steps") and re.search(r"decod|vae|sampling completed", low):
        st["phase"] = "terminando"
    elif st.get("phase") in (None, "preparando", "cargando") and re.search(r"condition|text encod|get_learned|tokeniz|llm", low):
        st["phase"] = "entendiendo"
    elif st.get("phase") in (None, "preparando") and re.search(r"load|tensor|model", low):
        st["phase"] = "cargando"
    elif re.search(r"decode_first_stage|decoding|vae decode", low) and st.get("phase") == "dibujando":
        st["phase"] = "terminando"


def describe(p):
    """«Dibujando · paso 2 de 4 · quedan 1 min 20 s» (para la interfaz)."""
    if not p:
        return ""
    txt = PHASES.get(p.get("phase") or "preparando", PHASES["preparando"])
    parts = [txt]
    if p.get("phase") == "dibujando" and p.get("steps"):
        parts.append(tr("paso %d de %d") % (p.get("step") or 0, p["steps"]))
        if p.get("eta"):
            parts.append(tr("quedan %s") % P.fmt_duration(p["eta"]))
    if p.get("elapsed", 0) >= 5:
        parts.append(tr("llevas %s") % P.fmt_duration(p["elapsed"]))
    return " · ".join(parts)


# ---------------------------------------------------------------- generar
class NotInstalled(Exception):
    pass


class Cancelled(Exception):
    pass


_RUN_LOCK = threading.Lock()          # una imagen cada vez (cada una ocupa varios GB de memoria)


def _friendly(log):
    text = "\n".join(log[-60:])
    if re.search(r"(?i)out of memory|failed to allocate|bad_alloc|cudaMalloc|ErrorOutOfDeviceMemory|not enough memory", text):
        return "Se quedó sin memoria. Prueba con un tamaño menor (aspect o width/height más pequeños) o pide al usuario que cierre programas."
    if re.search(r"(?i)unknown argument|invalid argument|unrecognized", text):
        return "El motor de imágenes no reconoció una opción (¿versión distinta?). Detalle:\n" + "\n".join(log[-6:])
    return "El motor de imágenes falló. Últimas líneas:\n" + "\n".join(log[-12:])


def generate(cfg, prompt, out_path, aspect="", width=0, height=0, seed=None, refs=(), progress=None, stop=None, mid=None):
    """Crea la imagen y la guarda en out_path (PNG). Devuelve {'path', 'width', 'height', 'seed', 'seconds', 'model'}.
    progress(dict) recibe la fase, el paso, lo que queda y la ruta de la vista previa."""
    m = model(cfg, mid)
    argv = engine_argv(cfg)
    if not argv or missing(cfg, m):
        raise NotInstalled(m["id"])
    files = {f["role"]: file_path(cfg, m, f) for f in m["files"]}
    w, h = pick_size(cfg, aspect, width, height)
    seed = int(seed) if seed not in (None, "") and str(seed).lstrip("-").isdigit() and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp_dir = os.path.join(paths.DATA, "imagen_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    prev = os.path.join(tmp_dir, "vista_%d.png" % os.getpid())
    part = os.path.join(tmp_dir, "salida_%d.png" % os.getpid())
    for q in (prev, part):
        try:
            os.remove(q)
        except OSError:
            pass
    cmd = argv + ["--diffusion-model", files["diffusion"], "--llm", files["llm"], "--vae", files["vae"],
                  "-p", prompt, "--cfg-scale", str(m["cfg"]), "--steps", str(m["steps"]), "-W", str(w), "-H", str(h),
                  "--seed", str(seed), "-o", part, "--preview", "proj", "--preview-path", prev]
    threads = int((cfg or {}).get("threads") or 0)
    if threads > 0:
        cmd += ["-t", str(threads)]
    if gpu(cfg):
        cmd += ["--offload-to-cpu"]              # los pesos esperan en la RAM y pasan a la gráfica cuando hacen falta
    for r in refs or ():
        if not m.get("edit"):
            raise RuntimeError("El modelo de imagen «%s» no modifica imágenes; crea una nueva sin reference o elige FLUX.2 [klein] en Ajustes → Imágenes." % m["name"])
        if not os.path.isfile(r):
            raise RuntimeError("No existe la imagen de referencia: %s" % r)
        cmd += ["-r", os.path.abspath(r)]
    exe_dir = os.path.dirname(argv[0]) if os.path.isabs(argv[0]) else None
    env = dict(os.environ)
    if exe_dir and osys.LINUX:
        env["LD_LIBRARY_PATH"] = exe_dir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    elif exe_dir and osys.MAC:
        env["DYLD_LIBRARY_PATH"] = exe_dir + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
    if not _RUN_LOCK.acquire(timeout=1):
        raise RuntimeError("Ya se está creando otra imagen; espera a que termine.")
    t0 = time.time()
    st = {"phase": "preparando", "log": []}
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                cwd=exe_dir or None, env=env, **osys.popen_kwargs())
        q = queue.Queue()

        def reader():
            try:
                while True:
                    b = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
                    if not b:
                        break
                    q.put(b)
            finally:
                q.put(None)
        threading.Thread(target=reader, daemon=True).start()
        buf, raw, last, last_step = "", [], 0.0, None
        while True:
            try:
                b = q.get(timeout=0.3)
            except queue.Empty:
                b = b""
            if b is None:
                break
            if b:
                raw.append(b)
                buf += b.decode("utf-8", "replace")
                *done, buf = re.split(r"[\r\n]", buf)
                for seg in done:
                    parse_line(seg, st)
                if buf and _BAR.search(buf):                 # la barra se reescribe sin salto de línea
                    parse_line(buf, st)
            if stop is not None and stop.is_set():
                osys.kill_tree(proc.pid)
                raise Cancelled()
            now = time.time()
            if progress and (now - last >= 0.5 or (st.get("phase"), st.get("step")) != last_step):
                last, last_step = now, (st.get("phase"), st.get("step"))
                info = {k: st.get(k) for k in ("phase", "step", "steps", "eta")}
                info["elapsed"] = now - t0
                info["preview"] = prev if os.path.isfile(prev) else None
                info["size"] = (w, h)
                try:
                    progress(info)
                except Exception:
                    pass
        code = proc.wait()
        try:
            with open(LOG, "wb") as fh:
                fh.write(("$ " + " ".join(cmd) + "\n\n").encode("utf-8", "replace") + b"".join(raw)[-400000:])
        except OSError:
            pass
        if buf:
            parse_line(buf, st)
        if code != 0 or not os.path.isfile(part):
            raise RuntimeError(_friendly(st["log"]))
        os.replace(part, out_path)
    finally:
        _RUN_LOCK.release()
        try:
            os.remove(prev)
        except OSError:
            pass
    return {"path": out_path, "width": w, "height": h, "seed": seed, "seconds": time.time() - t0, "model": m["name"]}


def default_path(cfg, workspace, prompt):
    """Ruta libre en la carpeta de imágenes: «imagenes/gato_naranja_en_la_ventana.png» (o _2, _3…)."""
    folder = (cfg or {}).get("image_dir") or os.path.join(workspace, tr("imagenes"))
    words = re.findall(r"\w+", prompt.lower())[:6]
    slug = "_".join(words)[:48].strip("_") or "imagen"
    p = os.path.join(folder, slug + ".png")
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, "%s_%d.png" % (slug, n))
        n += 1
    return p
