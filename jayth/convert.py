"""Modelos en otros formatos ademas de GGUF.

- Formato original de Hugging Face (safetensors o PyTorch .bin, en una carpeta local o descargado): se convierte a GGUF
  con el convertidor oficial de llama.cpp (convert_hf_to_gguf.py) y se reduce a la variante elegida con llama-quantize.
  Funciona en Windows, macOS y Linux, con o sin GPU. Las herramientas se preparan una sola vez en la carpeta de Jayth
  (Python aislado con uv; no toca el sistema) y coinciden con la version de llama.cpp instalada.
- Ollama y LM Studio guardan sus modelos en GGUF: se usan tal cual, sin copiarlos.
- AWQ, GPTQ, EXL2, ONNX o MLX ya cuantizados no los lee llama.cpp: se explica que motor los ejecuta (servidor externo).
"""
import os, re, sys, json, glob, time, shutil, platform, subprocess, threading
from . import paths, osys
from .provision import download, extract_archive, get_json, Cancelled, pretty_name

TOOLS = os.path.join(paths.RUNTIME_DIR, "convert")
QUANT_TARGETS = [("Q4_K_M", 4.85, "Equilibrada: la habitual para usar en el día a día"),
                 ("Q5_K_M", 5.69, "Algo más fiel, algo más grande y lenta"),
                 ("Q6_K", 6.56, "Muy fiel"),
                 ("Q8_0", 8.5, "Casi idéntica al original; el doble de grande que Q4"),
                 ("Q3_K_M", 3.91, "Más ligera, pierde algo de calidad"),
                 ("IQ4_XS", 4.25, "Ligera y buena, algo más lenta de crear")]
UNSUPPORTED = {"awq": "AWQ (motores para GPU NVIDIA como vLLM o SGLang)", "gptq": "GPTQ (vLLM, SGLang o ExLlama en GPU NVIDIA)",
               "exl2": "EXL2 (ExLlamaV2/TabbyAPI en GPU NVIDIA)", "exl3": "EXL3 (ExLlamaV3/TabbyAPI en GPU NVIDIA)",
               "bitsandbytes": "bitsandbytes (Transformers con GPU)", "hqq": "HQQ (Transformers)", "mlx": "MLX (mlx-lm en Mac con Apple Silicon)",
               "onnx": "ONNX (onnxruntime-genai)", "compressed-tensors": "compressed-tensors (vLLM)", "fp8": "FP8 (vLLM o SGLang en GPU moderna)"}


# ---------------------------------------------------------------- deteccion de formato
def _read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _bytes_per_param(dtype):
    return {"float32": 4, "float16": 2, "bfloat16": 2, "float8_e4m3fn": 1, "int8": 1}.get(str(dtype or "").lower(), 2)


def describe_config(cfg, size, n_files=0):
    """Datos utiles de un config.json de Hugging Face: arquitectura, visión, tipo, parámetros aproximados y si se puede convertir."""
    text = cfg.get("text_config") or cfg
    dtype = cfg.get("torch_dtype") or cfg.get("dtype") or text.get("torch_dtype") or text.get("dtype") or "bfloat16"
    qc = cfg.get("quantization_config") or text.get("quantization_config") or {}
    qm = str(qc.get("quant_method") or "").lower()
    if "quantization" in cfg and not qm:          # modelos cuantizados de MLX
        qm = "mlx"
    params = size / _bytes_per_param(dtype) if size else 0
    info = {"arch": (cfg.get("architectures") or ["?"])[0], "vision": bool(cfg.get("vision_config")), "dtype": dtype,
            "params": params, "size": size, "quant_method": qm, "files": n_files}
    if qm in ("mxfp4", "fp8"):          # el convertidor de llama.cpp los admite (p. ej. gpt-oss, DeepSeek FP8)
        qm = ""
    info["quant_method"] = qm
    info["convertible"] = not qm
    if qm:
        info["why_not"] = "Este modelo ya viene cuantizado en %s; llama.cpp no lo puede convertir. Úsalo con ese motor y conéctalo " \
                          "como servidor externo, o elige la versión original sin cuantizar." % UNSUPPORTED.get(qm, qm.upper())
    return info


def detect(path):
    """Qué es 'path': gguf (archivo listo), hf (carpeta original de Hugging Face), u otro formato no compatible."""
    path = os.path.normpath(path or "")
    if os.path.isfile(path):
        low = path.lower()
        if low.endswith(".gguf"):
            return {"format": "gguf", "path": path, "name": pretty_name(os.path.basename(path)), "size": os.path.getsize(path)}
        if os.path.basename(low) == "config.json" or low.endswith((".safetensors", ".bin")):
            return detect(os.path.dirname(path))
        if low.endswith(".onnx"):
            return {"format": "other", "path": path, "why_not": "ONNX no lo ejecuta llama.cpp; " + UNSUPPORTED["onnx"] + "."}
        return {"format": "other", "path": path, "why_not": "Formato no reconocido. Elige un .gguf o la carpeta del modelo original."}
    if not os.path.isdir(path):
        return {"format": "missing", "path": path}
    ggufs = sorted(glob.glob(os.path.join(path, "*.gguf")))
    cfgp = os.path.join(path, "config.json")
    weights = glob.glob(os.path.join(path, "*.safetensors")) or glob.glob(os.path.join(path, "pytorch_model*.bin"))
    if os.path.isfile(cfgp) and weights:
        size = sum(os.path.getsize(w) for w in weights)
        info = describe_config(_read_json(cfgp), size, len(weights))
        info.update({"format": "hf", "path": path, "name": pretty_name(os.path.basename(path)),
                     "weights": "safetensors" if weights[0].endswith(".safetensors") else "pytorch"})
        return info
    if glob.glob(os.path.join(path, "*.onnx")):
        return {"format": "other", "path": path, "why_not": "ONNX no lo ejecuta llama.cpp; " + UNSUPPORTED["onnx"] + "."}
    if ggufs:
        main = [g for g in ggufs if "mmproj" not in os.path.basename(g).lower()]
        mm = [g for g in ggufs if "mmproj" in os.path.basename(g).lower()]
        if main:
            return {"format": "gguf", "path": main[0], "mmproj": mm[0] if mm else "", "name": pretty_name(os.path.basename(main[0])),
                    "size": sum(os.path.getsize(g) for g in main)}
    return {"format": "other", "path": path, "why_not": "En esa carpeta no hay un modelo (falta config.json con sus pesos .safetensors, o un .gguf)."}


def target_size(params, quant):
    bpw = next((b for q, b, _ in QUANT_TARGETS if q == quant), 4.85)
    return params * bpw / 8 + 0.3 * 1024 ** 3


# ---------------------------------------------------------------- modelos de Ollama y LM Studio (ya son GGUF)
def ollama_models():
    """Modelos descargados con Ollama: su peso es un GGUF dentro de ~/.ollama/models/blobs (se usa sin copiarlo)."""
    root = os.environ.get("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")
    out = []
    for man in glob.glob(os.path.join(root, "manifests", "*", "*", "*", "*")):
        d = _read_json(man)
        model = proj = None
        for layer in d.get("layers") or []:
            blob = os.path.join(root, "blobs", (layer.get("digest") or "").replace(":", "-"))
            if layer.get("mediaType") == "application/vnd.ollama.image.model":
                model = blob
            elif layer.get("mediaType") == "application/vnd.ollama.image.projector":
                proj = blob
        if model and os.path.isfile(model):
            parts = man.replace("\\", "/").split("/")
            name = "%s:%s" % (parts[-2], parts[-1]) if parts[-3] == "library" else "%s/%s:%s" % (parts[-3], parts[-2], parts[-1])
            out.append({"source": "Ollama", "name": name, "path": model, "mmproj": proj if proj and os.path.isfile(proj) else "",
                        "size": os.path.getsize(model)})
    return out


def lmstudio_models():
    out = []
    for root in (os.path.join(os.path.expanduser("~"), ".lmstudio", "models"), os.path.join(os.path.expanduser("~"), ".cache", "lm-studio", "models")):
        for g in glob.glob(os.path.join(root, "*", "*", "*.gguf")):
            if "mmproj" in os.path.basename(g).lower():
                continue
            mm = [m for m in glob.glob(os.path.join(os.path.dirname(g), "*.gguf")) if "mmproj" in os.path.basename(m).lower()]
            out.append({"source": "LM Studio", "name": pretty_name(os.path.basename(g)), "path": g, "mmproj": mm[0] if mm else "",
                        "size": os.path.getsize(g)})
    return out


def other_apps_models():
    try:
        return ollama_models() + lmstudio_models()
    except Exception:
        return []


# ---------------------------------------------------------------- herramientas de conversion (una sola vez)
def llama_build(llama_exe):
    try:
        r = subprocess.run([llama_exe, "--version"], capture_output=True, text=True, timeout=30, creationflags=osys.NO_WINDOW)
        m = re.search(r"build (\d+)", (r.stdout or "") + (r.stderr or ""))
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def tool_exe(llama_exe, name):
    """Otra herramienta de llama.cpp junto a llama-server (p. ej. llama-quantize)."""
    p = os.path.join(os.path.dirname(llama_exe), osys.exe(name))
    return p if os.path.isfile(p) else ""


def _uv_asset():
    arch = platform.machine().lower()
    arm = arch in ("arm64", "aarch64")
    if osys.WIN:
        return "uv-%s-pc-windows-msvc.zip" % ("aarch64" if arm else "x86_64")
    if osys.MAC:
        return "uv-%s-apple-darwin.tar.gz" % ("aarch64" if arm else "x86_64")
    return "uv-%s-unknown-linux-gnu.tar.gz" % ("aarch64" if arm else "x86_64")


def _env():
    e = dict(os.environ)
    e.update({"UV_PYTHON_INSTALL_DIR": os.path.join(TOOLS, "python"), "UV_CACHE_DIR": os.path.join(TOOLS, "cache"),
              "UV_NO_CONFIG": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return e


def env_python():
    return os.path.join(TOOLS, "env", "Scripts", "python.exe") if osys.WIN else os.path.join(TOOLS, "env", "bin", "python")


def tools_ready(build):
    stamp = _read_json(os.path.join(TOOLS, "ready.json"))
    return stamp.get("build") == build and os.path.isfile(env_python()) and os.path.isfile(os.path.join(TOOLS, "src", "convert_hf_to_gguf.py"))


def _run(cmd, progress=None, stop=None, parse=None, label=""):
    """Ejecuta un proceso mostrando su progreso; devuelve las ultimas lineas (para explicar errores)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_env(), **osys.popen_kwargs())
    tail, buf = [], b""
    while True:
        if stop is not None and stop.is_set():
            osys.kill_tree(p.pid)
            raise Cancelled()
        ch = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(4096)
        if not ch:
            break
        buf += ch
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()
        for line in parts:
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            tail = (tail + [s])[-40:]
            if parse and progress:
                r = parse(s)
                if r:
                    progress(*r)
    code = p.wait()
    if code != 0:
        raise RuntimeError("%s falló (código %s):\n%s" % (label or os.path.basename(cmd[0]), code, "\n".join(tail[-12:])))
    return tail


def ensure_tools(llama_exe, progress=None, stop=None):
    """Prepara (una vez) el convertidor de la misma version que el llama.cpp instalado: uv, Python aislado,
    codigo del convertidor y sus dependencias (torch para CPU, transformers…). ~1-2 GB en la carpeta de Jayth."""
    build = llama_build(llama_exe)
    if not build:
        raise RuntimeError("No pude saber la versión de llama.cpp (%s)." % llama_exe)
    if tools_ready(build):
        return build
    os.makedirs(TOOLS, exist_ok=True)
    pr = progress or (lambda *a: None)
    # 1) uv: gestor de Python de un solo ejecutable (Astral)
    uv = os.path.join(TOOLS, osys.exe("uv"))
    if not os.path.isfile(uv):
        asset = _uv_asset()
        dl = os.path.join(TOOLS, "downloads", asset)
        download("https://github.com/astral-sh/uv/releases/latest/download/" + asset, dl, 0, "", lambda d, t, ph: pr(d, t, "uv: " + ph), stop)
        tmp = os.path.join(TOOLS, "uv_tmp")
        extract_archive(dl, tmp)
        found = next((os.path.join(r, f) for r, _, fs in os.walk(tmp) for f in fs if f == osys.exe("uv")), None)
        if not found:
            raise RuntimeError("El paquete de uv no contiene %s" % osys.exe("uv"))
        shutil.move(found, uv)
        shutil.rmtree(tmp, ignore_errors=True)
        if not osys.WIN:
            os.chmod(uv, 0o755)
    # 2) codigo del convertidor de esa version de llama.cpp
    src = os.path.join(TOOLS, "src")
    stamp_src = _read_json(os.path.join(src, "build.json")).get("build")
    if stamp_src != build:
        z = os.path.join(TOOLS, "downloads", "llama.cpp-b%d.zip" % build)
        download("https://codeload.github.com/ggml-org/llama.cpp/zip/refs/tags/b%d" % build, z, 0, "", lambda d, t, ph: pr(d, t, "convertidor: " + ph), stop)
        pr(0, 0, "descomprimiendo el convertidor")
        import zipfile
        shutil.rmtree(src, ignore_errors=True)
        os.makedirs(src)
        keep = ("convert_hf_to_gguf.py", "conversion/", "gguf-py/", "requirements/", "requirements.txt")
        with zipfile.ZipFile(z) as zf:
            for m in zf.infolist():
                rel = m.filename.split("/", 1)[1] if "/" in m.filename else ""
                if not rel or not rel.startswith(keep) or m.is_dir():
                    continue
                target = os.path.normpath(os.path.join(src, rel))
                if not target.startswith(os.path.normpath(src) + os.sep):
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(m) as fi, open(target, "wb") as fo:
                    shutil.copyfileobj(fi, fo)
        with open(os.path.join(src, "build.json"), "w") as f:
            json.dump({"build": build}, f)
    # 3) Python aislado y dependencias (torch solo para CPU: basta para convertir y pesa mucho menos)
    py = env_python()
    if not os.path.isfile(py):
        pr(0, 0, "preparando Python (una sola vez)")
        venv = [uv, "venv", "--python", "3.12", "--seed", os.path.join(TOOLS, "env")]
        try:
            _run(venv, label="Preparar Python", stop=stop)
        except RuntimeError:
            # uv en Windows a veces descarga Python bien pero falla al crear su acceso directo interno la primera vez;
            # el segundo intento usa el Python ya descargado
            shutil.rmtree(os.path.join(TOOLS, "env"), ignore_errors=True)
            _run(venv, label="Preparar Python", stop=stop)
    reqs = _requirements(src)
    torch = [r for r in reqs if r.lower().startswith("torch")]
    rest = [r for r in reqs if not r.lower().startswith("torch")]
    pr(0, 0, "instalando dependencias del convertidor (torch, transformers…)")
    if torch:
        _run([uv, "pip", "install", "--python", py, "--index-url", "https://download.pytorch.org/whl/cpu"] + torch, label="instalar torch", stop=stop)
    _run([uv, "pip", "install", "--python", py] + rest + ["safetensors", "pyyaml", "tqdm", "requests", "jinja2"], label="instalar dependencias", stop=stop)
    _run([uv, "cache", "clean"], label="limpiar cache")
    with open(os.path.join(TOOLS, "ready.json"), "w") as f:
        json.dump({"build": build, "date": time.strftime("%Y-%m-%d")}, f)
    shutil.rmtree(os.path.join(TOOLS, "downloads"), ignore_errors=True)
    return build


def _requirements(src):
    """Dependencias del convertidor segun sus propios archivos de requisitos (sin el gguf de PyPI: se usa el suyo)."""
    out, seen = [], set()

    def read(p):
        if p in seen or not os.path.isfile(p):
            return
        seen.add(p)
        for line in open(p, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if not line or line.startswith("--"):
                continue
            if line.startswith("-r"):
                read(os.path.normpath(os.path.join(os.path.dirname(p), line[2:].strip())))
            elif not re.match(r"(?i)^(-e\s+)?\.?/?gguf", line):
                out.append(line)
    read(os.path.join(src, "requirements", "requirements-convert_hf_to_gguf.txt"))
    return out or ["numpy", "sentencepiece", "transformers", "protobuf", "torch"]


# ---------------------------------------------------------------- conversion
def _pct_convert(s):
    m = re.search(r"(\d{1,3})%\|", s)
    return (int(m.group(1)), 100, "convirtiendo a GGUF") if m else None


def _pct_quant(s):
    m = re.search(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]", s)
    return (int(m.group(1)), int(m.group(2)), "reduciendo") if m else None


def convert_to_gguf(src_dir, out_file, outtype="bf16", mmproj=False, progress=None, stop=None):
    py = env_python()
    script = os.path.join(TOOLS, "src", "convert_hf_to_gguf.py")
    cmd = [py, script, src_dir, "--outfile", out_file, "--outtype", outtype] + (["--mmproj"] if mmproj else [])
    _run(cmd, progress, stop, _pct_convert, "La conversión a GGUF")
    if mmproj and not os.path.isfile(out_file):          # algunas versiones añaden el prefijo mmproj- al nombre
        cands = glob.glob(os.path.join(os.path.dirname(out_file), "mmproj*.gguf"))
        if cands:
            shutil.move(cands[0], out_file)
    if not os.path.isfile(out_file):
        raise RuntimeError("El convertidor terminó pero no creó %s" % out_file)
    return out_file


def quantize(llama_exe, src_gguf, out_file, quant, threads=0, progress=None, stop=None):
    q = tool_exe(llama_exe, "llama-quantize")
    if not q:
        raise RuntimeError("Falta llama-quantize junto a %s (instala el motor desde el asistente)." % llama_exe)
    cmd = [q, src_gguf, out_file, quant] + ([str(threads)] if threads else [])
    _run(cmd, progress, stop, _pct_quant, "La reducción a %s" % quant)
    return out_file


def plan_space(info, quant):
    """Espacio temporal: la conversion intermedia (16 bits) + la variante final."""
    inter = info["params"] * 2
    final = target_size(info["params"], quant)
    return inter + final, final


def convert_model(src_dir, out_dir, quant, llama_exe, vision=True, threads=0, progress=None, stop=None, name=""):
    """Original de Hugging Face -> GGUF reducido a 'quant' (+ proyector de vision si lo tiene). Devuelve (modelo, mmproj).
    'name': nombre del modelo para los archivos (si no, el de la carpeta)."""
    info = detect(src_dir)
    if info.get("format") != "hf":
        raise RuntimeError("No es una carpeta con un modelo original de Hugging Face: %s" % src_dir)
    if info.get("why_not"):
        raise RuntimeError(info["why_not"])
    os.makedirs(out_dir, exist_ok=True)
    base = re.sub(r"[^\w.-]+", "-", name or re.sub(r"(?i)\s*original$", "", info["name"])).strip("-") or "modelo"
    final = os.path.join(out_dir, "%s-%s.gguf" % (base, quant))
    inter = os.path.join(out_dir, "%s-BF16.tmp.gguf" % base)
    mm = os.path.join(out_dir, "mmproj-%s-F16.gguf" % base)
    need, _ = plan_space(info, quant)
    free = shutil.disk_usage(out_dir).free
    if free < need:
        raise RuntimeError("Hace falta ~%.0f GB libres en %s para convertir (hay %.0f GB)." % (need / 1024 ** 3, out_dir, free / 1024 ** 3))
    pr = progress or (lambda *a: None)
    if not os.path.isfile(final):
        convert_to_gguf(src_dir, inter, "bf16", False, pr, stop)
        quantize(llama_exe, inter, final + ".part", quant, threads, pr, stop)
        os.replace(final + ".part", final)
        try:
            os.remove(inter)
        except OSError:
            pass
    if vision and info.get("vision") and not os.path.isfile(mm):
        convert_to_gguf(src_dir, mm, "f16", True, lambda d, t, ph: pr(d, t, "visión: " + ph), stop)
    return final, (mm if os.path.isfile(mm) else "")
