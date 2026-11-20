# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Descargas de llama.cpp (GitHub oficial) y de modelos GGUF (Hugging Face).
Reanudables (.part + HTTP Range), con reintentos y verificacion SHA-256 cuando la fuente la publica."""
import os, re, json, time, hashlib, zipfile, platform, threading, subprocess, http.client, urllib.request, urllib.error, urllib.parse
from . import osys
from .i18n import tr

UA = {"User-Agent": "Jayth (+python-urllib)"}
CHUNK = 1 << 20

class Cancelled(Exception):
    pass


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=dict(UA, Accept="application/json"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- catalogo de modelos abiertos (todos los laboratorios)
# Se construye solo a partir de Hugging Face (repositorios GGUF publicados) y se guarda en cache para usarlo sin internet.
# Cualquier otro repositorio GGUF tambien sirve escribiendolo a mano.
CATALOG_SOURCES = ("unsloth", "ggml-org")
LABS = [(r"^(qwen|qwq)", "Alibaba (Qwen)"), (r"^(gemma|medgemma|codegemma|shieldgemma|t5gemma)", "Google"),
        (r"nemotron|^nvidia", "NVIDIA"), (r"(^|-)llama|^codellama", "Meta"),
        (r"^(mistral|magistral|devstral|ministral|mixtral|codestral|pixtral|voxtral)", "Mistral AI"), (r"^deepseek", "DeepSeek"),
        (r"^phi", "Microsoft"), (r"^gpt-oss", "OpenAI"), (r"^granite", "IBM"), (r"^(glm|chatglm|codegeex)", "Zhipu AI (Z.ai)"),
        (r"^(kimi|moonlight)", "Moonshot AI"), (r"^minimax", "MiniMax"), (r"^smollm", "Hugging Face"), (r"^(olmo|tulu|molmo)", "Ai2"),
        (r"^ernie", "Baidu"), (r"^hunyuan", "Tencent"), (r"^seed", "ByteDance"), (r"^lfm", "Liquid AI"), (r"^falcon", "TII"),
        (r"^exaone", "LG AI Research"), (r"^(command|aya|c4ai|north)", "Cohere"), (r"^apriel", "ServiceNow"), (r"^jamba", "AI21 Labs"),
        (r"^intern", "Shanghai AI Lab"), (r"^yi-", "01.AI"), (r"^(ling|ring)-", "inclusionAI"), (r"^step", "StepFun"),
        (r"^(arcee|afm|trinity)", "Arcee AI"), (r"^(baichuan)", "Baichuan"), (r"^(openchat|openhermes|hermes)", "Nous Research"),
        (r"^mimo", "Xiaomi"), (r"^longcat", "Meituan"), (r"^dots", "rednote"), (r"^minicpm", "OpenBMB"), (r"^hy-", "Tencent"),
        (r"^smol", "Hugging Face"), (r"^moondream", "Moondream"), (r"gemma", "Google"), (r"^autoglm", "Zhipu AI (Z.ai)")]
# parametros activos de MoE conocidos cuyo nombre no los indica (para estimar bien la velocidad)
KNOWN_ACTIVE = [(r"(?i)deepseek-(v3|r1|v4)", 37e9), (r"(?i)kimi-k", 32e9), (r"(?i)^glm-4\.[5-9](?!.*(air|flash))", 32e9),
                (r"(?i)^glm-5", 40e9), (r"(?i)glm-4\.\d-air", 12e9), (r"(?i)minimax-m", 10e9), (r"(?i)llama-4-(maverick|scout)", 17e9),
                (r"(?i)longcat-flash", 27e9), (r"(?i)mimo-v2[\d.]*-flash", 15e9), (r"(?i)step-?3", 11e9), (r"(?i)mistral-large-3", 41e9),
                (r"(?i)qwen3-coder-next|qwen3-next", 3e9), (r"(?i)glm-4\.7-flash", 3e9)]
_JUNK_REPO = re.compile(r"(?i)(test|tiny|stories\d|models-moved|spec-for|^vllm-|ocr|diffusion|for-testing|router-download)")
_NOT_CHAT_PIPE = {"text-to-image", "image-to-image", "image-to-video", "text-to-video", "image-text-to-video", "text-to-speech",
                  "text-to-audio", "automatic-speech-recognition", "audio-to-audio", "feature-extraction", "sentence-similarity",
                  "image-classification", "object-detection", "depth-estimation", "image-segmentation"}
_NOT_CHAT_ARCH = re.compile(r"^(flux|lumina|wan|ltx|qwen_image|moss_image|sd|sdxl|hunyuan_video|cogvideo|bert|nomic|jina|clip|whisper)", re.I)
_NOT_CHAT_NAME = re.compile(r"(?i)(embed|rerank|[-_]tts|whisper|-image-|image-?\d|-video|z-image|flux|ltx-|wan\d|-MTP-|-MTP$|guard|safety)")
OFFLINE_CATALOG = [   # si no hay internet ni cache: unos pocos conocidos de varios laboratorios
    ("unsloth/Qwen3.5-4B-GGUF", 4.2e9, None, True), ("unsloth/Qwen3.5-9B-GGUF", 9.0e9, None, True),
    ("unsloth/gemma-4-E4B-it-GGUF", 7.5e9, 4e9, True), ("unsloth/gemma-4-12b-it-GGUF", 11.9e9, None, True),
    ("unsloth/gpt-oss-20b-GGUF", 20.9e9, 3.6e9, False), ("unsloth/Qwen3.6-35B-A3B-GGUF", 34.7e9, 3e9, True),
    ("unsloth/gemma-4-26B-A4B-it-GGUF", 25.2e9, 4e9, True), ("unsloth/Qwen3.8-27B-GGUF", 27.3e9, None, True),
    ("unsloth/Llama-3.2-3B-Instruct-GGUF", 3.2e9, None, False), ("unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF", 30.5e9, 3.3e9, False),
]


def lab_of(name):
    low = name.lower().split("/")[-1]
    for pat, lab in LABS:
        if re.search(pat, low):
            return lab
    return "Otros"


def active_params(name, total):
    """Parametros activos por palabra: en los MoE ('35B-A3B') o en los 'E4B' de Gemma son muchos menos que el total."""
    m = re.search(r"(?i)(?:^|[-_ ])[AE](\d+(?:\.\d+)?)B(?:$|[-_ ])", name.split("/")[-1])
    if m:
        return min(total, float(m.group(1)) * 1e9)
    if re.search(r"(?i)gpt-oss-20b", name):
        return 3.6e9
    if re.search(r"(?i)gpt-oss-120b", name):
        return 5.1e9
    base = name.split("/")[-1]
    for pat, act in KNOWN_ACTIVE:
        if re.search(pat, base):
            return min(total, act)
    return total


# Lo que el modelo sabe hacer se lee de su plantilla de conversación (la publica Hugging Face con el GGUF):
# si admite herramientas es «agéntico» (lo que necesita el agente de Jayth) y si tiene modo de pensar, razona.
_TOOLS_TPL = re.compile(r"\btools\b|tool_calls?|\[AVAILABLE_TOOLS\]|<tools>|<\|tool")
_THINK_TPL = re.compile(r"enable_thinking|<think>|reasoning_content|reasoning_effort|<\|channel\|>|thinking")
# sin plantilla (catálogo sin conexión): familias conocidas por usar herramientas
_TOOLS_NAME = re.compile(r"(?i)qwen[23]|qwq|gpt-oss|gemma-?4|llama-?3\.[1-9]|llama-?4|mistral|ministral|devstral|magistral|granite|glm-?4|"
                         r"glm-?5|kimi|hermes|nemotron|command-r|deepseek-v3|deepseek-r1|minimax|phi-?4|lfm2|seed-oss|hunyuan")
_CODE_ONLY = re.compile(r"(?i)coder|codestral|devstral|codegemma|codellama|starcoder|deepseek-coder")


def _entry(repo, total, active=None, vision=False, ctx=0, downloads=0, created="", pipeline="", template=None):
    name = pretty_name(repo)
    act = active or active_params(repo, total)
    tools = bool(_TOOLS_TPL.search(template)) if template else bool(_TOOLS_NAME.search(repo))
    think = bool(_THINK_TPL.search(template)) if template else False
    think = think or bool(re.search(r"(?i)thinking|reason|-r1|magistral|qwq", repo))
    audio = pipeline == "any-to-any"
    tags = []
    if tools:
        tags.append("agente")
    if vision:
        tags.append("visión")
    if audio:
        tags.append("audio")
    if _CODE_ONLY.search(repo) or re.search(r"(?i)\bcode\b", name):
        tags.append("código")
    if think:
        tags.append("razonamiento")
    if act < total * 0.6:
        tags.append("MoE")
    return {"repo": repo, "name": name, "lab": lab_of(repo), "params": total, "active": act, "vision": bool(vision),
            "tools": tools, "audio": audio, "ctx": ctx, "downloads": downloads, "created": created, "tags": tags}


def kind_text(e):
    """Etiqueta corta del tipo de modelo para la tabla del catálogo."""
    parts = []
    if e.get("tools"):
        parts.append(tr("Agente"))
    if e.get("vision"):
        parts.append(tr("Visión y audio") if e.get("audio") else tr("Visión"))
    if "código" in e.get("tags", []):
        parts.append(tr("Código"))
    if "razonamiento" in e.get("tags", []):
        parts.append(tr("Razona"))
    return " · ".join(parts) or tr("Texto")


def matches_kind(e, kind):
    """Filtro «Tipo» del catálogo."""
    tags = e.get("tags", [])
    return {"all": True, "agent": bool(e.get("tools")), "multi": bool(e.get("vision") or e.get("audio")),
            "general": "código" not in tags, "code": "código" in tags, "reason": "razonamiento" in tags}.get(kind, True)


def discover_models(limit=150):
    """Modelos de chat GGUF publicados en Hugging Face (los mas descargados y los mas nuevos), sin generadores de
    imagen/video ni embeddings. Devuelve [{repo, name, lab, params, active, vision, ctx, downloads, created, tags}]."""
    seen, out = set(), []
    fields = "&expand[]=gguf&expand[]=downloads&expand[]=createdAt&expand[]=pipeline_tag"
    for author in CATALOG_SOURCES:
        for sort in ("downloads", "createdAt"):
            url = "https://huggingface.co/api/models?author=%s&filter=gguf&sort=%s&direction=-1&limit=%d%s" % (author, sort, limit, fields)
            try:
                items = get_json(url, timeout=20)
            except Exception:
                continue
            for it in items:
                rid = it.get("id") or ""
                g = it.get("gguf") or {}
                total = g.get("total") or 0
                pipe = it.get("pipeline_tag") or ""
                arch = g.get("architecture") or ""
                if (not total or total < 2.5e8 or rid.lower() in seen or pipe in _NOT_CHAT_PIPE or _NOT_CHAT_ARCH.search(arch)
                        or _NOT_CHAT_NAME.search(rid) or _JUNK_REPO.search(rid.split("/")[-1])):
                    continue
                key = pretty_name(rid).lower()
                if key in seen:                # el mismo modelo publicado por dos fuentes: se queda el primero (unsloth)
                    continue
                seen.update({rid.lower(), key})
                out.append(_entry(rid, float(total), vision=pipe in ("image-text-to-text", "any-to-any"), ctx=g.get("context_length") or 0,
                                  downloads=it.get("downloads") or 0, created=str(it.get("createdAt") or "")[:10], pipeline=pipe,
                                  template=str(g.get("chat_template") or "") or None))
    return out


def catalog(cache_path, max_age=24 * 3600, refresh=False):
    """Catalogo con cache en disco: se renueva cada dia; sin internet usa la cache o una lista minima."""
    try:
        if not refresh and os.path.isfile(cache_path) and time.time() - os.path.getmtime(cache_path) < max_age:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if data and all("tools" in e for e in data):     # una caché anterior sin el tipo de modelo se renueva
                return data
    except (OSError, ValueError):
        pass
    try:
        data = discover_models()
        if data:
            tmp = cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, cache_path)
            return data
    except Exception:
        pass
    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
        for e in data:                       # caché antigua sin conexión: el tipo se deduce del nombre
            if "tools" not in e:
                e.update({k: v for k, v in _entry(e["repo"], e["params"], e.get("active"), e.get("vision")).items() if k in ("tools", "audio", "tags")})
        return data
    except (OSError, ValueError):
        return [_entry(r, t, a, v) for r, t, a, v in OFFLINE_CATALOG]


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
    groups, mmproj, orig = {}, [], []
    for t in tree:
        p = t.get("path", "")
        if t.get("type") != "file":
            continue
        low = p.lower()
        if "/" not in p and (low.endswith((".safetensors", ".json", ".txt", ".model", ".jinja", ".tiktoken", ".py")) or re.match(r"pytorch_model.*\.bin$", low)) \
                and not low.endswith(".gguf"):
            lfs = t.get("lfs") or {}
            orig.append({"file": p, "size": int(lfs.get("size") or t.get("size") or 0), "sha256": lfs.get("oid") or ""})
        if not low.endswith(".gguf") or "imatrix" in low:
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
    # formato original (safetensors o PyTorch): se puede descargar y convertir a GGUF en el propio equipo
    original = None
    weights = [f for f in orig if f["file"].lower().endswith(".safetensors")] or [f for f in orig if f["file"].lower().endswith(".bin")]
    if weights and any(f["file"] == "config.json" for f in orig):
        files = weights + [f for f in orig if not f["file"].lower().endswith((".safetensors", ".bin"))]
        original = {"files": files, "size": sum(f["size"] for f in weights), "config": {}}
        try:
            original["config"] = get_json(hf_url(repo, "config.json"), timeout=20)
        except Exception:
            pass
    return {"repo": repo, "quants": quants, "mmproj": mmproj, "original": original}


def base_model(repo):
    """Repositorio original (formato de Hugging Face) del que sale un repo GGUF, segun su ficha (base_model)."""
    try:
        d = get_json("https://huggingface.co/api/models/%s" % repo, timeout=15)
        bm = (d.get("cardData") or {}).get("base_model")
        if isinstance(bm, list):
            bm = bm[0] if bm else None
        return bm if isinstance(bm, str) and "/" in bm else None
    except Exception:
        return None


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
        raise RuntimeError(tr("El motor «%s» no está disponible en %s.") % (backend, osys.os_label()))
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
    raise RuntimeError(tr("No encontré una versión de llama.cpp para %s (%s).") % (osys.os_label(), backend))


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


PARALLEL_MIN = 48 << 20         # por debajo de este tamaño no compensa abrir varias conexiones
DEFAULT_CONNECTIONS = 6


class _NoRanges(Exception):
    """El servidor no admite descargar por partes: se usa una sola conexión."""


def connections():
    """Conexiones simultáneas por descarga (ajuste del usuario; 1 = como antes)."""
    try:
        from . import core
        return max(1, min(16, int(core.SET.snapshot().get("download_connections", DEFAULT_CONNECTIONS))))
    except Exception:
        return DEFAULT_CONNECTIONS


def _download_parallel(url, part, size, progress, stop, n, retries):
    """Descarga por trozos con n conexiones a la vez, escribiendo cada trozo en su sitio de part.
    Lo hecho se guarda en part.json: si se corta o se detiene, al volver a llamarla sigue donde iba."""
    state_path = part + ".json"
    state = None
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    resume = bool(state and state.get("size") == size and int(state.get("piece") or 0) > 0 and os.path.isfile(part) and os.path.getsize(part) == size)
    # al menos 4 trozos por conexión (así todas trabajan hasta el final), de 4 a 64 MB cada uno
    piece = int(state["piece"]) if resume else max(4 << 20, min(64 << 20, (size // (n * 4)) >> 20 << 20))
    pieces = [(s, min(s + piece, size)) for s in range(0, size, piece)]
    done = [0] * len(pieces)
    if resume:
        done = [min(int(x), e - s) for x, (s, e) in zip(state.get("done", []), pieces)] + [0] * max(0, len(pieces) - len(state.get("done", [])))
    else:
        # una descarga anterior de una sola conexión: lo que ya tenía (el principio del archivo) no se vuelve a bajar
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        have = have if have < size else 0
        done = [max(0, min(e, have) - s) for s, e in pieces]
        with open(part, "ab" if have else "wb") as f:
            f.truncate(size)                 # el archivo ya mide lo que medirá; cada trozo se escribe en su sitio
    lock = threading.Lock()
    todo = [i for i, (s, e) in enumerate(pieces) if done[i] < e - s]
    err, quit_ = [], threading.Event()

    def save():
        tmp = state_path + ".tmp"
        with lock:
            data = {"size": size, "piece": piece, "done": list(done), "url": url}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, state_path)

    def worker():
        with open(part, "r+b") as fh:
            while not quit_.is_set():
                with lock:
                    if not todo:
                        return
                    i = todo.pop(0)
                s, e = pieces[i]
                attempt = 0
                while done[i] < e - s and not quit_.is_set():
                    off = s + done[i]
                    hdr = dict(UA, Range="bytes=%d-%d" % (off, e - 1))
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60) as r:
                            if r.status != 206:
                                raise _NoRanges()
                            fh.seek(off)
                            while not quit_.is_set():
                                b = r.read(min(CHUNK, e - s - done[i]))
                                if not b:
                                    break
                                fh.write(b)
                                with lock:
                                    done[i] += len(b)
                                if done[i] >= e - s:
                                    break
                        attempt = 0 if done[i] >= e - s else attempt
                    except _NoRanges:
                        err.append(_NoRanges())
                        quit_.set()
                        return
                    except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, OSError) as ex:
                        if isinstance(ex, urllib.error.HTTPError) and ex.code in (401, 403, 404):
                            err.append(RuntimeError(tr("No se puede descargar (%s): %s") % (ex.code, url)))
                            quit_.set()
                            return
                        attempt += 1
                        if attempt > retries:
                            err.append(RuntimeError(tr("Falló la descarga tras %d intentos: %s") % (retries, ex)))
                            quit_.set()
                            return
                        for _ in range(min(30, 2 ** attempt) * 4):
                            if quit_.is_set():
                                return
                            time.sleep(0.25)
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, min(n, len(todo))))]
    for t in threads:
        t.start()
    last_save = time.time()
    while any(t.is_alive() for t in threads):
        if stop is not None and stop.is_set():
            quit_.set()
        if progress and not quit_.is_set():
            with lock:
                got = sum(done)
            progress(got, size, "descargando")
        if time.time() - last_save > 2:
            save()
            last_save = time.time()
        time.sleep(0.2)
    for t in threads:
        t.join(1)
    save()
    if stop is not None and stop.is_set():
        raise Cancelled()
    if err:
        raise err[0]
    if sum(done) != size:
        raise RuntimeError(tr("La descarga quedó incompleta; vuelve a intentarlo y seguirá donde iba."))
    if progress:
        progress(size, size, "descargando")
    try:
        os.remove(state_path)
    except OSError:
        pass


def download(url, dest, size=0, sha256="", progress=None, stop=None, retries=8, conns=None):
    """Descarga url -> dest. Reanuda desde dest.part. progress(hecho, total, fase).
    Los archivos grandes de tamaño conocido se bajan por varias conexiones a la vez (como un gestor de descargas):
    una sola conexión a menudo no aprovecha toda la línea."""
    if os.path.isfile(dest) and (not size or os.path.getsize(dest) == size):
        if progress:
            progress(size or os.path.getsize(dest), size or os.path.getsize(dest), "ya descargado")
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part = dest + ".part"
    n = conns or connections()
    if size and (os.path.isfile(part + ".json") or (n > 1 and size >= PARALLEL_MIN)):
        try:
            _download_parallel(url, part, size, progress, stop, n, retries)
            return _finish(part, dest, size, sha256, progress, stop)
        except _NoRanges:
            for p in (part, part + ".json"):     # el servidor no admite trozos: de cero, con una conexión
                try:
                    os.remove(p)
                except OSError:
                    pass
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
            raise IOError(tr("conexión cortada"))
        except Cancelled:
            raise
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, IOError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                raise RuntimeError(tr("No se puede descargar (%s): %s") % (e.code, url))
            if isinstance(e, urllib.error.HTTPError) and e.code == 416:   # rango invalido: ya estaba completo
                break
            attempt += 1
            if attempt > retries:
                raise RuntimeError(tr("Falló la descarga tras %d intentos: %s") % (retries, e))
            if progress:
                progress(have, size or have, "reintentando (%d/%d)…" % (attempt, retries))
            for _ in range(min(30, 2 ** attempt)):
                if stop is not None and stop.is_set():
                    raise Cancelled()
                time.sleep(1)
    return _finish(part, dest, size, sha256, progress, stop)


def _finish(part, dest, size, sha256, progress, stop):
    if size and os.path.getsize(part) != size:
        raise RuntimeError(tr("Tamaño incorrecto tras descargar %s") % os.path.basename(dest))
    if sha256:
        got = sha256_file(part, progress, stop)
        if got.lower() != sha256.lower():
            os.remove(part)
            raise RuntimeError(tr("La verificación SHA-256 falló para %s; se borró el archivo dañado.") % os.path.basename(dest))
    os.replace(part, dest)
    return dest


def extract_zip(zpath, dest):
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = os.path.abspath(os.path.join(dest, m.filename))
            if not target.startswith(os.path.abspath(dest) + os.sep) and target != os.path.abspath(dest):
                raise RuntimeError(tr("Ruta peligrosa en el zip: %s") % m.filename)
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
                raise RuntimeError(tr("Ruta peligrosa en el paquete: %s") % m.name)
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
def fmt_duration(s):
    """Duracion legible: 45 s · 3 min 20 s · 14 min · 1 h 27 min · 2 d 5 h."""
    if s < 1:
        return tr("menos de 1 s")
    s = int(round(s))
    if s < 60:
        return "%d s" % s
    m, s = divmod(s, 60)
    if m < 10:
        return "%d min %02d s" % (m, s)
    if m < 60:
        return "%d min" % m
    h, m = divmod(m, 60)
    if h < 24:
        return "%d h %02d min" % (h, m)
    d, h = divmod(h, 24)
    return "%d d %d h" % (d, h)


def fmt_bytes(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%.0f %s" if u in ("B", "KB") else "%.1f %s") % (n, u)
        n /= 1024


DOWNLOAD_PHASES = ("descargando", "ya descargado")
# las fases de download() se comparan (no se traducen): este es su texto en pantalla
_PHASE_TXT = {"descargando": tr("descargando"), "verificando": tr("verificando"), "ya descargado": tr("ya descargado"),
              "descomprimiendo": tr("descomprimiendo")}


def _phase_text(ph):
    """Texto en pantalla de una fase interna, también con el prefijo que le ponen otros módulos («uv: descargando»)."""
    pre, sep, last = ph.rpartition(": ")
    m = re.match(r"reintentando \((\d+/\d+)\)…$", last)
    return pre + sep + (tr("reintentando (%s)…") % m.group(1) if m else _PHASE_TXT.get(last, last))


class Job:
    """Ejecuta pasos en un hilo; la interfaz lee self.steps y self.overall() periodicamente.

    Por paso: done/total de la fase actual (descarga o verificacion), got = bytes descargados, speed = velocidad
    suavizada (media movil exponencial, no salta con cada bloque), eta = segundos que quedan de la fase."""

    def __init__(self):
        self.steps = []
        self.stop = threading.Event()
        self.thread = None
        self.error = None
        self.finished = False
        self.result = {}
        self.started = self.ended = 0.0

    def add(self, label, fn, size=0):
        """size: tamaño previsto en bytes (si se conoce), para calcular el total desde el principio."""
        self.steps.append({"label": label, "fn": fn, "status": "pending", "done": 0, "total": size, "size": size, "got": 0,
                           "phase": "", "speed": 0.0, "eta": None, "started": 0.0, "ended": 0.0, "base": None, "_t": 0.0, "_d": 0})

    def start(self):
        self.started = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def cancel(self):
        self.stop.set()

    def overall(self):
        """Progreso de todo el trabajo: bytes descargados de todos los pasos, velocidad actual y tiempo restante."""
        total = sum(st["size"] or st["total"] for st in self.steps)
        got = sum((st["size"] or st["total"]) if st["status"] == "done" else st["got"] for st in self.steps)
        run = next((st for st in self.steps if st["status"] == "running"), None)
        speed = run["speed"] if run and run["phase"] in DOWNLOAD_PHASES else 0.0
        eta = (total - got) / speed if speed > 0 and total > got else None
        end = self.ended or time.time()
        return {"got": got, "total": total, "speed": speed, "eta": eta, "elapsed": end - self.started if self.started else 0,
                "done_steps": sum(st["status"] == "done" for st in self.steps), "steps": len(self.steps)}

    @staticmethod
    def _progress(st, done, total, phase):
        now = time.time()
        if phase != st["phase"]:                    # nueva fase (descarga, verificacion, reintento): se reinicia la medida
            st["_t"], st["_d"], st["speed"], st["eta"] = now, done, 0.0, None
            st["_t0"], st["_d0"] = now, done
        elif now - st["_t"] >= 0.5:
            if now - st["_t0"] < 4:                 # al empezar: media real desde el inicio de la fase (estable y sin picos)
                st["speed"] = max(0, done - st["_d0"]) / (now - st["_t0"])
            else:                                   # despues: media movil, sigue los cambios de la conexion sin saltar
                inst = max(0, done - st["_d"]) / (now - st["_t"])
                st["speed"] = st["speed"] * 0.8 + inst * 0.2
            st["_t"], st["_d"] = now, done
        if phase in DOWNLOAD_PHASES or phase.startswith("reintentando"):
            if st["base"] is None:
                st["base"] = done                   # lo que ya habia de una descarga anterior (reanudada)
            st["got"] = max(st["got"], done)
        elif phase == "verificando":
            st["got"] = total
        st["done"], st["total"], st["phase"] = done, total or st["total"], phase
        if total and not st["size"]:
            st["size"] = total
        st["eta"] = (total - done) / st["speed"] if st["speed"] > 0 and total > done else None

    def _run(self):
        try:
            for st in self.steps:
                st["status"] = "running"
                st["started"] = time.time()
                st["fn"](lambda done, total, phase, st=st: self._progress(st, done, total, phase), self.stop, self.result)
                st["ended"] = time.time()
                st["status"] = "done"
                st["skipped"] = st["phase"] == "ya descargado"
                st["phase"] = "listo"
        except Cancelled:
            for st in self.steps:
                if st["status"] == "running":
                    st["status"] = "cancelled"
            self.error = tr("Cancelado. Lo descargado se conserva y se reanudará la próxima vez.")
        except Exception as e:
            for st in self.steps:
                if st["status"] == "running":
                    st["status"] = "error"
            self.error = str(e)
        finally:
            self.ended = time.time()
            self.finished = True


def describe_step(st):
    """Texto de estado de un paso para la interfaz."""
    if st["status"] == "pending":
        return tr("en espera") + (" · %s" % fmt_bytes(st["size"]) if st["size"] else "")
    if st["status"] == "done":
        if st.get("skipped"):
            return tr("✓ ya estaba descargado") + (" · %s" % fmt_bytes(st["size"]) if st["size"] else "")
        took = st["ended"] - st["started"]
        moved = st["got"] - (st["base"] or 0)
        avg = moved / took if took > 0.5 and moved > 0 else 0
        parts = [tr("✓ listo")]
        if st["size"]:
            parts.append(fmt_bytes(st["size"]))
        parts.append(tr("en %s") % fmt_duration(took))
        if avg:
            parts.append(tr("%s/s de media") % fmt_bytes(avg))
        return " · ".join(parts)
    if st["status"] == "cancelled":
        return tr("✗ cancelado · %s de %s conservados") % (fmt_bytes(st["got"]), fmt_bytes(st["size"] or st["total"]))
    if st["status"] == "error":
        return tr("✗ error")
    # en curso
    ph, done, total = st["phase"], st["done"], st["total"]
    if ph == "verificando":
        head = tr("Verificando la integridad (SHA-256)")
    elif ph == "descomprimiendo":
        return tr("Descomprimiendo…")
    elif ph.startswith("reintentando"):
        head = tr("Conexión perdida · %s") % _phase_text(ph)
    elif ph == "descargando":
        head = tr("Descargando")
    else:
        head = _phase_text(ph).capitalize() if ph else tr("Preparando…")
    parts = [head]
    if total:
        parts.append("%s %%" % (("%.1f" % (100.0 * done / total)) if total > 2 * 1024 ** 3 else ("%d" % (100 * done // total))))
        parts.append(tr("%s de %s") % (fmt_bytes(done), fmt_bytes(total)))
    elif done:
        parts.append(fmt_bytes(done))
    if ph in ("descargando", "verificando"):
        if st["speed"] > 0:
            parts.append("%s/s" % fmt_bytes(st["speed"]))
            if st["eta"] is not None:
                parts.append(tr("quedan %s") % fmt_duration(st["eta"]))
        else:
            parts.append(tr("calculando velocidad…"))
    return " · ".join(parts)


def describe_overall(o):
    """Resumen de todo el trabajo: '6.5 GB de 17.1 GB · paso 2 de 3 · 11.2 MB/s · quedan ~16 min · llevas 9 min'."""
    parts = []
    if o["total"]:
        parts.append(tr("%s de %s") % (fmt_bytes(o["got"]), fmt_bytes(o["total"])))
    parts.append(tr("paso %d de %d") % (min(o["done_steps"] + 1, o["steps"]), o["steps"]))
    if o["speed"] > 0:
        parts.append("%s/s" % fmt_bytes(o["speed"]))
    if o["eta"] is not None:
        parts.append((tr("quedan ~%s") if o["eta"] >= 1 else tr("quedan %s")) % fmt_duration(o["eta"]))
    if o["elapsed"] >= 1:
        parts.append(tr("llevas %s") % fmt_duration(o["elapsed"]))
    return " · ".join(parts)
