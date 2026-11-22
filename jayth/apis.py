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
        obj = _get(url + "/models/" + urllib.parse.quote(model, safe=""), key, timeout)
        ctx, out = read_limits(obj)
        _note_price(url, model, obj)
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
                    _note_price(url, model, it)
                    break
        except Exception:
            pass
    return ctx, out


_PRICES = {}               # (dirección, modelo) → (entrada, salida) en US$ por millón de tokens, si el servicio lo publica


def read_prices(obj):
    """Precio que publica el servicio en la ficha del modelo, en US$ por millón de tokens (entrada, salida), o None.
    OpenRouter lo da por token («0.000003»); otros, ya por millón."""
    pr = obj.get("pricing") if isinstance(obj, dict) else None
    if not isinstance(pr, dict):
        return None
    try:
        a = float(pr.get("prompt") or pr.get("input") or 0)
        b = float(pr.get("completion") or pr.get("output") or 0)
    except (TypeError, ValueError):
        return None
    if a <= 0 and b <= 0:
        return None
    return (a * 1e6, b * 1e6) if max(a, b) < 0.01 else (a, b)


def _note_price(url, model, obj):
    pr = read_prices(obj)
    if pr:
        _PRICES[((url or "").rstrip("/"), model)] = pr


def prices(url, model):
    """Precio publicado por el servicio para ese modelo (lo que se supo al preguntarle por sus límites), o None."""
    k = ((url or "").rstrip("/"), model)
    if k in _PRICES:
        return _PRICES[k]
    with _LOCK:
        _load()
        got = _INFO.get("%s|%s" % k) or {}
    return (float(got["pin"]), float(got["pout"])) if got.get("pin") is not None and got.get("pout") is not None else None


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
            pr = _PRICES.get(((url or "").rstrip("/"), model))
            if pr:
                got["pin"], got["pout"] = pr
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
_OPTIONAL = ("temperature", "top_p", "reasoning_effort", "stream_options", "parallel_tool_calls", "seed", "reasoning", "thinking",
             "enable_thinking", "thinking_budget", "chat_template_kwargs", "include_reasoning", "extra_body")
_OUT = ("max_tokens", "max_completion_tokens")


# ---- esfuerzo y razonamiento de cada servicio (según su documentación, consultada el 22-11-2026)
# Cada uno lo recibe con su parámetro propio. Claude va por su API nativa (jayth/claude.py), que lo toma de
# «reasoning_effort». Si un servicio rechaza el parámetro, learn() lo quita y, desde entonces, el esfuerzo se le pide al
# modelo en sus instrucciones (effort_hint): es una indicación, no un límite, pero es lo que queda.
_PROVIDERS = (("openrouter", ("openrouter.ai",)), ("openai", ("api.openai.com",)),
              ("gemini", ("generativelanguage.googleapis.com",)), ("deepseek", ("api.deepseek.com",)), ("xai", ("api.x.ai",)),
              ("groq", ("api.groq.com",)), ("kimi", ("api.moonshot.ai", "api.moonshot.cn", "api.kimi.com")),
              ("glm", ("api.z.ai", "open.bigmodel.cn")), ("dashscope", ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com",
                                                                         "dashscope-us.aliyuncs.com")),
              ("mistral", ("api.mistral.ai",)))
_EFFORT_KEYS = ("reasoning_effort", "reasoning", "thinking", "enable_thinking", "thinking_budget", "chat_template_kwargs",
                "extra_body")
# servicios que exigen que se les devuelva su razonamiento en los pasos con herramientas (si no: HTTP 400)
_ECHO_REASONING = ("deepseek", "kimi")
DASHSCOPE_BUDGET = 4096


def _host(base):
    try:
        return (urllib.parse.urlparse(base).hostname or "").lower()
    except ValueError:
        return ""


def provider(base):
    """Qué servicio es: 'claude', 'openai', 'gemini', 'openrouter', 'deepseek', 'xai', 'groq', 'kimi', 'glm',
    'dashscope', 'mistral', 'ollama', 'lmstudio', 'selfhosted' (llama.cpp, vLLM, SGLang… en la red propia) u 'other'."""
    from . import claude as CL
    if CL.is_claude(base):
        return "claude"
    h = _host(base)
    for name, hosts in _PROVIDERS:
        if any(h == x or h.endswith("." + x) for x in hosts):
            return name
    if is_local(base):
        try:
            port = urllib.parse.urlparse(base).port
        except ValueError:
            port = None
        return "ollama" if port == 11434 else "lmstudio" if port == 1234 else "selfhosted"
    return "other"


def effort_params(base, effort, model=""):
    """Campos de la petición que llevan el esfuerzo elegido (low, medium, high) a este servicio, con su parámetro propio.
    «Bajo» apaga el razonamiento donde se puede; donde no, es su nivel más bajo."""
    p, m = provider(base), (model or "").lower()
    low = effort == "low"
    if p == "openrouter":
        return {"reasoning": {"effort": effort}}                       # lo traduce a cada modelo; llega en «reasoning»
    if p in ("claude", "openai", "xai"):
        return {"reasoning_effort": effort}
    if p == "gemini":                                                  # su configuración propia; y que muestre lo que piensa
        tc = {"include_thoughts": True}
        if "2.5" in m:
            tc["thinking_budget"] = {"low": 1024, "medium": 8192, "high": 24576}[effort]
        else:
            tc["thinking_level"] = effort
        return {"extra_body": {"google": {"thinking_config": tc}}}
    if p == "deepseek":
        if low:
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "reasoning_effort": "high" if effort == "medium" else "max"}
    if p == "kimi":
        if re.search(r"k3", m):                                        # K3: niveles low / high / max, razona siempre
            return {"reasoning_effort": {"low": "low", "medium": "high", "high": "max"}[effort]}
        return {"thinking": {"type": "disabled" if low else "enabled"}}
    if p == "glm":
        if low:
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "reasoning_effort": effort}
    if p == "dashscope":
        if low:
            return {"enable_thinking": False}
        return {"enable_thinking": True, "thinking_budget": DASHSCOPE_BUDGET} if effort == "medium" else {"enable_thinking": True}
    if p == "groq":
        e = "none" if (low and "qwen" in m) else effort
        return {"reasoning_effort": e, "include_reasoning": True}
    if p == "ollama":
        return {"reasoning_effort": "none" if low else effort}
    if p == "selfhosted":                                              # llama.cpp, vLLM, SGLang: lo de la plantilla y lo común
        return {"reasoning_effort": "none" if low else effort, "chat_template_kwargs": {"enable_thinking": not low}}
    if p == "lmstudio":
        return {}                                                      # no tiene ajuste: se pide en las instrucciones
    return {"reasoning_effort": effort}


def effort_dropped(base, model, params):
    """¿Ya rechazó este servicio todo lo que lleva el esfuerzo? (entonces se pide en las instrucciones)"""
    if not params:
        return provider(base) == "lmstudio"
    r = _RULES.get((base, model))
    return bool(r) and all(k in r["drop"] for k in params)


EFFORT_HINT = {
    "low": "[Esfuerzo que pide el usuario: bajo. Responde y actúa de forma directa, sin extenderte razonando antes; prima la rapidez.]",
    "high": "[Esfuerzo que pide el usuario: alto. Razona a fondo antes de actuar y comprueba tu trabajo; prima la calidad sobre la rapidez.]",
}


def effort_hint(base, model, effort):
    """Indicación para las instrucciones del modelo cuando el servicio no deja elegir el esfuerzo ('' si no hace falta)."""
    if effort_dropped(base, model, effort_params(base, effort, model)):
        return EFFORT_HINT.get(effort, "")
    return ""


def prepare(base, payload):
    """Lo propio de cada servicio en los mensajes: DeepSeek y Kimi reciben de vuelta su razonamiento (lo exigen en los
    pasos con herramientas); a los demás no se les envía nada interno."""
    model = payload.get("model")
    r = _RULES.get((base, model)) or {}
    echo = provider(base) in _ECHO_REASONING or r.get("echo")
    if not echo:
        return payload
    msgs = []
    for m in payload.get("messages") or []:
        if m.get("role") == "assistant" and m.get("_reasoning"):
            m = dict(m, reasoning_content=m["_reasoning"])
        msgs.append(m)
    return dict(payload, messages=msgs)


def effort_support(base, model=""):
    """(clase, explicación) de lo que hace el esfuerzo con este servicio: 'levels' (niveles de verdad), 'toggle'
    (apaga o enciende el razonamiento y su profundidad), 'hint' (se le pide en las instrucciones) o 'unknown'."""
    from .i18n import tr
    p = provider(base)
    if effort_dropped(base, model, effort_params(base, "medium", model)):
        return "hint", tr("Este servicio no tiene ajuste de esfuerzo para este modelo: Jayth se lo pide en sus instrucciones "
                          "(es una indicación, no un límite).")
    if p == "claude":
        return "levels", tr("Claude lo recibe con su propio ajuste de esfuerzo: cuanto más alto, más piensa (y más tokens gasta).")
    if p == "openai":
        return "levels", tr("OpenAI lo recibe con su propio ajuste de esfuerzo. Por esta vía no muestra su razonamiento: las "
                            "cifras de cada paso dicen cuánto pensó.")
    if p == "gemini":
        return "levels", tr("Gemini lo recibe con su propia configuración de razonamiento, y Jayth le pide que lo muestre.")
    if p == "openrouter":
        return "levels", tr("OpenRouter lo traduce al ajuste propio de cada modelo; los que no razonan lo ignoran.")
    if p in ("deepseek", "kimi", "glm", "dashscope"):
        return "toggle", tr("En este servicio «Bajo» apaga el razonamiento (si el modelo lo permite) y «Medio» y «Alto» lo "
                            "encienden con más o menos profundidad.")
    return "unknown", tr("Se envía con el ajuste de esfuerzo habitual. Si el servicio no lo admite, Jayth deja de enviarlo y se "
                         "lo pide al modelo en sus instrucciones.")


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
    if "reasoning_content" in low and not r.get("echo"):              # quiere que se le devuelva su razonamiento
        r["echo"] = True
        return True
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
