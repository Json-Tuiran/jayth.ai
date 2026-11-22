# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Modelos por API: lo que cambia de un servicio a otro. Cada servicio compatible con OpenAI admite parámetros distintos
(unos rechazan la temperatura, otros llaman distinto al límite de salida) y cada modelo tiene su propio contexto, que no
tiene nada que ver con el de los modelos locales. Aquí se averigua —preguntando al servicio y aprendiendo de sus
rechazos— en vez de suponerlo."""
import os, re, json, time, threading, urllib.request, urllib.parse
from . import paths, APP_NAME

CTX_LOCAL = 16384          # servidor propio que no dice su contexto
CTX_REMOTE = 128000        # servicio en la nube del que no se sabe nada
OUT_REMOTE = 32000         # salida por respuesta que se pide a un servicio en la nube (el pensamiento también cuenta)
CTX_CAP = 200000           # tope por defecto de lo que se envía en cada paso (ajuste api_ctx_max; 0 = sin tope)
_FILE = os.path.join(paths.HOME, "cache", "api_modelos.json")
_INFO = {}                 # "dirección|modelo" → {"ctx", "out", "t"}
_LOADED = []
_LOCK = threading.Lock()
_GUESS = ((r"claude", 200000), (r"gemini", 1000000), (r"gpt-4o|gpt-4\.1|gpt-5|chatgpt|^o[134](-|$)", 128000),
          (r"grok", 128000), (r"deepseek", 64000), (r"mistral|codestral", 128000))
_CTX_KEYS = ("max_input_tokens", "context_length", "context_window", "max_context_length", "inputTokenLimit", "input_token_limit", "n_ctx")
_OUT_KEYS = ("max_output_tokens", "max_completion_tokens", "outputTokenLimit", "output_token_limit", "max_tokens")


def is_local(url):
    """¿Es un servidor de este equipo o de la red propia (Ollama, LM Studio, el de la oficina)?"""
    h = (urllib.parse.urlparse(url or "").hostname or "").lower()
    if not h or "." not in h or h.endswith((".local", ".lan", ".internal")):
        return True
    return bool(re.match(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0$|::1$)", h))


def _load():
    if _LOADED:
        return
    _LOADED.append(1)
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            j = json.load(f)
        if isinstance(j, dict):
            _INFO.update({k: v for k, v in j.items() if isinstance(v, dict)})
    except (OSError, ValueError):
        pass


def _store():
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        tmp = "%s.%d.tmp" % (_FILE, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_INFO, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _FILE)
    except OSError:
        pass


def _pick(obj, keys):
    for src in (obj, obj.get("top_provider"), obj.get("limits"), obj.get("meta"), obj.get("capabilities")):
        if isinstance(src, dict):
            for k in keys:
                v = src.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 1024:
                    return int(v)
    return 0


def read_limits(obj):
    """De la ficha de un modelo (cada servicio la escribe a su manera): contexto y salida máxima; 0 si no lo dice."""
    if not isinstance(obj, dict):
        return 0, 0
    return _pick(obj, _CTX_KEYS), _pick(obj, _OUT_KEYS)


def _get(url, key, timeout):
    headers = {"Authorization": "Bearer " + (key or "local"), "User-Agent": APP_NAME, "Accept": "application/json"}
    if "anthropic.com" in url:
        headers.update({"x-api-key": key or "", "anthropic-version": "2023-06-01"})
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout).read(8_000_000)
    return json.loads(raw.decode("utf-8", "replace"))


def fetch(url, key, model, timeout=8):
    """Pregunta al servicio por el modelo: primero su ficha y, si no la da, la lista entera. Devuelve (contexto, salida)."""
    url = (url or "").rstrip("/")
    ctx = out = 0
    try:
        ctx, out = read_limits(_get(url + "/models/" + urllib.parse.quote(model, safe=""), key, timeout))
    except Exception:
        pass
    if not ctx:
        try:
            j = _get(url + "/models", key, timeout)
            data = (j.get("data") or j.get("models") or []) if isinstance(j, dict) else j
            for it in data or []:
                if isinstance(it, dict) and (it.get("id") or it.get("name") or "") in (model, "models/" + model):
                    c, o = read_limits(it)
                    ctx, out = c or ctx, o or out
                    break
        except Exception:
            pass
    return ctx, out


def limits(url, key, model, ask=False):
    """Lo que se sabe del modelo: {"ctx", "out"} (0 = no se sabe). Con ask=True, si no se sabe (o el dato es de hace más
    de una semana), se pregunta al servicio; hacerlo fuera del hilo de la interfaz."""
    k = "%s|%s" % ((url or "").rstrip("/"), model or "")
    with _LOCK:
        _load()
        got = dict(_INFO.get(k) or {})
    if ask and model and (not got or time.time() - float(got.get("t") or 0) > 7 * 86400):
        ctx, out = fetch(url, key, model)
        if ctx or out or not got:
            got = {"ctx": ctx or int(got.get("ctx") or 0), "out": out or int(got.get("out") or 0),
                   "t": time.time() if (ctx or out) else time.time() - 6 * 86400}    # sin respuesta: se reintenta mañana
            with _LOCK:
                _INFO[k] = got
                _store()
    return {"ctx": int(got.get("ctx") or 0), "out": int(got.get("out") or 0)}


def guess_ctx(model):
    low = (model or "").lower().split("/")[-1]
    return next((n for pat, n in _GUESS if re.search(pat, low)), CTX_REMOTE)


def context(cfg):
    """Tokens de conversación que Jayth deja crecer con el modelo por API activo antes de recortar y resumir."""
    url, model = cfg.get("external_url") or "", cfg.get("external_model") or ""
    own = int(cfg.get("n_ctx") or 0)
    if is_local(url):                      # servidor propio: manda lo que el usuario fijó; si no, lo que diga el servidor
        return own or limits(url, "", model)["ctx"] or CTX_LOCAL
    n = limits(url, "", model)["ctx"] or guess_ctx(model)
    cap = int(cfg.get("api_ctx_max", CTX_CAP) or 0)
    return min(n, cap) if cap else n


def max_out(cfg, high=False):
    """Tokens de salida que se piden por respuesta al modelo por API activo."""
    own = int(cfg.get("max_tokens") or 4096) * (2 if high else 1)
    url = cfg.get("external_url") or ""
    if is_local(url):
        return own
    cap = limits(url, "", cfg.get("external_model") or "")["out"]
    want = max(own, OUT_REMOTE)
    return min(want, cap) if cap else want


# ---- parámetros que un servicio no admite: se aprende de su rechazo y no se le vuelven a enviar
_RULES = {}                # (dirección, modelo) → {"drop": set, "rename": bool, "max_out": int}
_OPTIONAL = ("temperature", "top_p", "reasoning_effort", "stream_options", "parallel_tool_calls", "seed")
_OUT = ("max_tokens", "max_completion_tokens")


def adapt(base, payload):
    """El payload tal como lo admite ese servicio, según lo que ya rechazó."""
    r = _RULES.get((base, payload.get("model")))
    if not r:
        return payload
    p = {k: v for k, v in payload.items() if k not in r["drop"]}
    if r["rename"] and "max_tokens" in p:
        p["max_completion_tokens"] = p.pop("max_tokens")
    if r["max_out"]:
        for k in _OUT:
            if k in p:
                p[k] = min(int(p[k]), r["max_out"])
    return p


def learn(base, payload, error):
    """De un rechazo del servicio (texto «HTTP 400: …») saca qué parámetro sobra, cómo se llama aquí el límite de salida o
    cuánta salida admite. Devuelve True si aprendió algo nuevo: vale la pena repetir la petición ya adaptada."""
    m = re.match(r"HTTP (\d+): (.*)", error or "", re.S)
    if not m or int(m.group(1)) not in (400, 422):
        return False
    text, param = m.group(2), ""
    try:
        j = json.loads(text)
        e = j.get("error") if isinstance(j, dict) else None
        if isinstance(e, dict):
            text, param = str(e.get("message") or text), str(e.get("param") or "")
        elif isinstance(e, str):
            text = e
        elif isinstance(j, dict) and j.get("detail"):
            text = json.dumps(j["detail"], ensure_ascii=False)
    except ValueError:
        pass
    low = text.lower()
    r = _RULES.setdefault((base, payload.get("model")), {"drop": set(), "rename": False, "max_out": 0})
    if "max_tokens" in payload and "max_completion_tokens" in low:        # aquí el límite de salida se llama de otra forma
        r["rename"] = True
        return True
    key = next((k for k in _OUT if k in payload), None)
    if key and (param in _OUT or re.search(r"max_(completion_)?tokens|output tokens|completion tokens", low)):
        cur = int(payload[key])
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", text) if x.replace(",", "").isdigit()]
        ok = [n for n in nums if 256 <= n < cur]
        if ok:                                                            # pide más salida de la que admite el modelo
            r["max_out"] = max(ok)
            return True
    hit = [k for k in _OPTIONAL if k in payload and (param == k or re.search(r"(?<![a-z_])%s(?![a-z_])" % k, low))]
    if hit:
        if set(hit) & {"temperature", "top_p"}:                          # si no quiere uno, usa sus propios valores para los dos
            hit += ["temperature", "top_p"]
        r["drop"].update(hit)
        return True
    return False
