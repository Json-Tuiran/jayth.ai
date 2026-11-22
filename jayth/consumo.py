# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Consumo de los modelos por API: lo que el usuario paga o gasta de su cuota en cada servicio.

- Cada petición a un servicio anota sus tokens (los que informa el propio servicio) en data/consumo.jsonl, con el coste
  si se puede saber: el que da el servicio, el precio que publica, el que el usuario escribió para ese modelo o, para
  Claude, el precio de lista. Sin precio conocido se cuentan solo los tokens: no se inventa ninguna cifra.
- De las cabeceras de cada respuesta se guardan los límites de la cuenta (peticiones y tokens que quedan en la ventana).
- Algunos servicios dicen el saldo de la cuenta con la propia clave (OpenRouter, DeepSeek); de los demás se enlaza su
  página de consumo, que es la única cifra oficial: Jayth solo ve lo que se envió desde este equipo.
Todo queda en el equipo: nada de esto se envía a ningún sitio."""
import os, re, json, time, threading, urllib.request, urllib.parse
from . import paths, APP_NAME

FILE = os.path.join(paths.DATA, "consumo.jsonl")
_LOCK = threading.Lock()
LIMITS = {}                # dirección del servicio → {"t", "requests": (quedan, tope, cuándo se repone), "tokens": (…)}
PRICES_DATE = "2026-11-03"     # fecha de los precios de lista de abajo (US$ por millón de tokens: entrada, salida)
LIST_PRICES = (("anthropic.com", r"claude-fable-5-2|claude-mythos-5-2", 8.0, 40.0),
               ("anthropic.com", r"claude-(fable|mythos)-5", 10.0, 50.0),
               ("anthropic.com", r"claude-opus-5-5", 4.0, 20.0),
               ("anthropic.com", r"claude-opus-(5|4-[678])", 5.0, 25.0),
               ("anthropic.com", r"claude-sonnet-5", 2.0, 10.0),
               ("anthropic.com", r"claude-sonnet-4-6", 3.0, 15.0),
               ("anthropic.com", r"claude-haiku-5-5", 0.10, 0.50),
               ("anthropic.com", r"claude-haiku-4-5", 1.0, 5.0))
USAGE_PAGES = (("openrouter.ai", "https://openrouter.ai/activity"), ("anthropic.com", "https://console.anthropic.com/settings/usage"),
               ("openai.com", "https://platform.openai.com/usage"), ("deepseek.com", "https://platform.deepseek.com/usage"),
               ("mistral.ai", "https://console.mistral.ai/usage"), ("groq.com", "https://console.groq.com/"),
               ("googleapis.com", "https://aistudio.google.com/"), ("x.ai", "https://console.x.ai/"))


def _norm(base):
    return (base or "").strip().rstrip("/")


def usage_page(base):
    """Página del servicio donde el usuario ve su consumo y su facturación oficiales ('' si no se conoce)."""
    host = (urllib.parse.urlparse(base or "").hostname or "").lower()
    return next((u for h, u in USAGE_PAGES if host == h or host.endswith("." + h)), "")


def price(base, model, cfg=None):
    """Precio del modelo en US$ por millón de tokens: (entrada, salida, de dónde sale) o None si no se sabe.
    Origen: "tuyo" (lo escribió el usuario), "servicio" (lo publica el servicio) o "lista" (precio de lista con fecha)."""
    base = _norm(base)
    try:
        if cfg is None:
            from . import core
            cfg = core.SET.snapshot()
        for p in cfg.get("providers") or []:
            pr = (p.get("prices") or {}).get(model)
            if _norm(p.get("url")) == base and pr and len(pr) >= 2 and (float(pr[0]) or float(pr[1])):
                return float(pr[0]), float(pr[1]), "tuyo"
    except Exception:
        pass
    try:
        from . import apis
        pub = apis.prices(base, model)
        if pub:
            return pub[0], pub[1], "servicio"
    except Exception:
        pass
    host = (urllib.parse.urlparse(base).hostname or "").lower()
    low = (model or "").lower()
    for h, pat, pin, pout in LIST_PRICES:
        if host.endswith(h) and re.search(pat, low):
            return pin, pout, "lista"
    return None


def _limits(base, headers):
    """Límites de la cuenta según las cabeceras de la respuesta (cada servicio las nombra a su manera)."""
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    out = {}
    for kind in ("requests", "tokens"):
        left = h.get("x-ratelimit-remaining-" + kind) or h.get("anthropic-ratelimit-%s-remaining" % kind)
        top = h.get("x-ratelimit-limit-" + kind) or h.get("x-ratelimit-" + kind) or h.get("anthropic-ratelimit-%s-limit" % kind)
        reset = h.get("x-ratelimit-reset-" + kind) or h.get("anthropic-ratelimit-%s-reset" % kind) or ""
        try:
            if left not in (None, ""):
                out[kind] = (int(float(left)), int(float(top)) if top not in (None, "") else 0, reset[:40])
        except ValueError:
            pass
    if out:
        out["t"] = time.time()
        LIMITS[_norm(base)] = out
    return out


def record(base, model, usage, headers=None, sid=""):
    """Anota una petición a un servicio por API. Devuelve la fila anotada ({i, o, usd…}) o None si el servicio no dijo
    cuántos tokens fueron. Nunca lanza errores: llevar la cuenta no puede estropear una respuesta."""
    try:
        base = _norm(base)
        if headers:
            _limits(base, headers)
        if not isinstance(usage, dict):
            return None
        pin = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        pout = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        if not pin and not pout:
            return None
        det = usage.get("prompt_tokens_details") or {}
        cached = int((det.get("cached_tokens") if isinstance(det, dict) else 0) or usage.get("cache_read_input_tokens") or 0)
        usd, src = None, ""
        if isinstance(usage.get("cost"), (int, float)) and not isinstance(usage.get("cost"), bool):
            usd, src = float(usage["cost"]), "servicio"            # el servicio dice lo que costó (OpenRouter)
        else:
            pr = price(base, model)
            if pr:                                                 # lo leído de caché se cobra a una fracción: se estima al 10 %
                usd, src = ((pin - cached) * pr[0] + cached * pr[0] * 0.1 + pout * pr[1]) / 1e6, pr[2]
        row = {"t": int(time.time()), "u": base, "m": model or "", "i": pin, "o": pout}
        if cached:
            row["c"] = cached
        if usd is not None:
            row["usd"], row["p"] = round(usd, 6), src
        if sid:
            row["s"] = sid
        with _LOCK:
            os.makedirs(os.path.dirname(FILE), exist_ok=True)
            with open(FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        return row
    except Exception:
        return None


def rows(base=None, since=0):
    """Las peticiones anotadas (de un servicio, desde una fecha), de la más antigua a la más nueva."""
    base = _norm(base) if base else None
    out = []
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if (base is None or r.get("u") == base) and r.get("t", 0) >= since:
                    out.append(r)
    except OSError:
        pass
    return out


def total(rs):
    """Suma de unas filas: peticiones, tokens y coste. «sin_precio»: cuántas no tienen coste (el total en US$ es parcial)."""
    out = {"n": len(rs), "i": 0, "o": 0, "c": 0, "usd": 0.0, "sin_precio": 0, "estimado": False}
    for r in rs:
        out["i"] += int(r.get("i") or 0)
        out["o"] += int(r.get("o") or 0)
        out["c"] += int(r.get("c") or 0)
        if r.get("usd") is None:
            out["sin_precio"] += 1
        else:
            out["usd"] += float(r["usd"])
            out["estimado"] = out["estimado"] or r.get("p") != "servicio"
    return out


def summary(base=None, now=None):
    """Consumo de un servicio (o de todos): hoy, últimos 7 y 30 días, total y por modelo en los últimos 30 días."""
    now = now or time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    every = rows(base)
    out = {"hoy": total([r for r in every if r["t"] >= midnight]), "7d": total([r for r in every if r["t"] >= now - 7 * 86400]),
           "30d": total([r for r in every if r["t"] >= now - 30 * 86400]), "todo": total(every), "desde": every[0]["t"] if every else 0, "modelos": []}
    by = {}
    for r in every:
        if r["t"] >= now - 30 * 86400:
            by.setdefault(r.get("m") or "", []).append(r)
    out["modelos"] = sorted(((m, total(rs)) for m, rs in by.items()), key=lambda x: (-x[1]["usd"], -x[1]["i"] - x[1]["o"]))
    return out


def session_total(sid):
    """Lo que lleva gastado una conversación."""
    return total([r for r in rows() if r.get("s") == sid]) if sid else total([])


def _get(url, key, timeout=10):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + (key or ""), "User-Agent": APP_NAME, "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read(200000).decode("utf-8", "replace"))


def balance(base, key):
    """Saldo o crédito de la cuenta, si el servicio lo da con la propia clave: {"texto": …} o None. Hace una petición de
    red: llamarla fuera del hilo de la interfaz."""
    base = _norm(base)
    host = (urllib.parse.urlparse(base).hostname or "").lower()
    try:
        if host.endswith("openrouter.ai"):
            d = (_get(base + "/key", key) or {}).get("data") or {}
            used, top, left = d.get("usage"), d.get("limit"), d.get("limit_remaining")
            return {"usado": used, "tope": top, "queda": left, "gratis": bool(d.get("is_free_tier"))}
        if host.endswith("deepseek.com"):
            d = _get("https://api.deepseek.com/user/balance", key) or {}
            infos = d.get("balance_infos") or []
            if infos:
                return {"queda": float(infos[0].get("total_balance") or 0), "moneda": infos[0].get("currency") or "", "activa": bool(d.get("is_available", True))}
    except Exception:
        return None
    return None


def prune(keep_days=400):
    """Quita lo anotado hace más de un año largo (se llama de vez en cuando)."""
    try:
        cut = time.time() - keep_days * 86400
        with _LOCK:
            rs = rows()
            if rs and rs[0].get("t", cut) < cut:
                tmp = FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    for r in rs:
                        if r.get("t", 0) >= cut:
                            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
                os.replace(tmp, FILE)
    except Exception:
        pass
