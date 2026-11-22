# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Errores de los servicios de modelos por API, tratados igual para todos.

Cada servicio devuelve sus errores a su manera (OpenAI {"error": {...}}, Gemini una lista [{"error": {...}}], Anthropic
{"type": "error", "error": {...}}, otros texto suelto) y con códigos que significan cosas distintas según el caso (un 429
puede ser «demasiadas peticiones por minuto», que se arregla esperando, o «se acabó el saldo», que no). Aquí se lee el
mensaje venga como venga, se decide de qué tipo es y si merece reintentarse solo, y se explica en una frase clara. Así
no hace falta probar cada servicio ni cada modelo: lo que no se reconoce cae en la explicación general."""
import json, re
from .i18n import tr

# tipos: busy (saturado), rate (demasiadas peticiones), server (fallo pasajero del servidor), quota (sin saldo o cuota),
# auth (clave), model (modelo inexistente o sin acceso), context (no cabe), timeout, bad (petición rechazada), other
TRANSIENT = ("busy", "rate", "server", "timeout")
_QUOTA = re.compile(r"insufficient[_ ]quota|exceeded your current quota|quota exceeded|billing|credit|balance|payment|"
                    r"out of credits|insufficient[_ ]funds|saldo|resource_exhausted.*(per day|daily|billing)", re.I)
_BUSY = re.compile(r"overload|high demand|unavailable|capacity|try again later|temporarily|busy|no instances|"
                   r"service is currently|loading model|model is loading", re.I)
_RATE = re.compile(r"rate[ _-]?limit|too many requests|requests per (minute|second)|tokens per minute|rpm|tpm", re.I)
_CTX = re.compile(r"context[_ ]length|context window|maximum context|too many tokens|prompt is too long|input is too long|"
                  r"exceeds the (maximum|context)|max_tokens.*exceed", re.I)
_MODEL = re.compile(r"model[^.]{0,40}(not found|does not exist|not available|unknown|no access|not supported)|"
                    r"no such model|invalid model|model_not_found|is not found for api version", re.I)


def message(body):
    """El mensaje de error que trae la respuesta del servicio, venga en el formato que venga (o el texto, recortado)."""
    raw = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    raw = raw.strip()
    try:
        j = json.loads(raw)
    except ValueError:
        j = None

    def find(o, depth=0):
        if depth > 5:
            return ""
        if isinstance(o, list):
            for x in o:
                m = find(x, depth + 1)
                if m:
                    return m
            return ""
        if isinstance(o, dict):
            for k in ("message", "msg", "detail", "error_description"):
                if isinstance(o.get(k), str) and o[k].strip():
                    return o[k].strip()
            for k in ("error", "errors", "detail"):
                if k in o:
                    m = find(o[k], depth + 1)
                    if m:
                        return m
            if isinstance(o.get("error"), str):
                return o["error"]
        return ""
    msg = find(j) if j is not None else ""
    if not msg:
        msg = re.sub(r"<[^>]+>", " ", raw)              # a veces llega una página HTML de error
    return re.sub(r"\s+", " ", msg).strip()[:400]


def kind(status, body=""):
    """De qué tipo es el error (ver TRANSIENT)."""
    text = message(body) + " " + (body if isinstance(body, str) else "")
    s = int(status or 0)
    if s in (401, 403) and not _QUOTA.search(text):
        return "auth"
    if _QUOTA.search(text) and s in (0, 400, 402, 403, 429):
        return "quota"
    if s == 402:
        return "quota"
    if s == 429:
        return "busy" if _BUSY.search(text) else "rate"
    if s in (503, 529) or (s in (500, 502, 504) and _BUSY.search(text)):
        return "busy"
    if s in (408, 425, 500, 502, 504, 520, 521, 522, 523, 524):
        return "server"
    if s == 404 or _MODEL.search(text):
        return "model"
    if _CTX.search(text):
        return "context"
    if _BUSY.search(text):
        return "busy"
    if _RATE.search(text):
        return "rate"
    if 400 <= s < 500:
        return "bad"
    return "other"


def transient(status, body=""):
    return kind(status, body) in TRANSIENT


def retry_after(value):
    """Segundos que pide esperar la cabecera Retry-After (número o fecha), o None."""
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        import datetime
        d = parsedate_to_datetime(str(value))
        return max(0.0, (d - datetime.datetime.now(d.tzinfo)).total_seconds())
    except Exception:
        return None


def friendly(status, body="", model="", tries=0):
    """El error explicado en una frase, más el detalle del servicio (corto). tries: cuántas veces se reintentó."""
    k = kind(status, body)
    detail = message(body)
    again = (tr(" Jayth lo reintentó %d veces.") % tries) if tries else ""
    text = {
        "busy": tr("El servicio está saturado ahora mismo (no es un fallo de Jayth ni de tu clave).%s Prueba de nuevo en unos "
                   "minutos o elige otro modelo.") % again,
        "rate": tr("El servicio limita cuántas peticiones o tokens acepta por minuto y se superó.%s Espera un poco y pulsa "
                   "«Reintentar», o usa un modelo con más margen.") % again,
        "server": tr("El servicio tuvo un fallo pasajero.%s Pulsa «Reintentar» en un momento.") % again,
        "timeout": tr("El servicio tardó demasiado en responder.%s Puede estar saturado: pulsa «Reintentar» en un momento.") % again,
        "quota": tr("Tu cuenta en el servicio no tiene saldo o cuota suficiente. Revísalo en la página del servicio (en "
                    "«Modelos por API…», «Consumo oficial»)."),
        "auth": tr("El servicio rechazó la clave de API. Revisa que esté bien copiada y activa en «Modelos por API…»."),
        "model": (tr("El servicio no encuentra el modelo «%s» o tu cuenta no tiene acceso a él. Elige otro en «Modelos por "
                     "API…».") % model) if model else tr("El servicio no encuentra ese modelo o tu cuenta no tiene acceso a él."),
        "context": tr("La conversación no cabe en lo que admite el modelo. Pulsa el indicador de memoria y «Resumir ahora», o "
                      "empieza otra conversación."),
        "bad": tr("El servicio rechazó la petición."),
    }.get(k, tr("El servicio respondió con un error."))
    head = ("HTTP %d · " % int(status)) if status else ""
    return text + ((" " + tr("Detalle: %s") % (head + detail)) if (detail or head) else "")
