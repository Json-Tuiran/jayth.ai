# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Idioma de la interfaz: español (el original), inglés, portugués, francés, alemán, italiano, japonés y chino.

- Los textos se escriben en español en el código y se envuelven con tr(): tr("Guardar"), tr("Descargando %s") % nombre.
- Las traducciones están en assets/i18n/<idioma>.json ({"texto en español": "traducción"}). Lo que falte se ve en español.
- El idioma se decide una sola vez al arrancar (antes de importar el resto): el ajuste «ui_language» de settings.json
  (auto = el del sistema), o la variable JAYTH_LANG (pruebas). Cambiarlo pide reiniciar Jayth.
- JAYTH_I18N_MISSING=<archivo>: al salir, guarda ahí los textos que se pidieron sin traducción (para completar catálogos).
"""
import os, json, atexit
from . import paths

LANGS = ("es", "en", "pt", "fr", "de", "it", "ja", "zh")
NAMES = {"es": "Español", "en": "English", "pt": "Português", "fr": "Français", "de": "Deutsch", "it": "Italiano",
         "ja": "日本語", "zh": "中文（简体）"}
CJK = ("ja", "zh")                 # escritura sin espacios entre palabras: fuentes propias y búsquedas por caracteres
DEFAULT = "en"          # sistemas en otros idiomas: la interfaz en inglés


def system_lang():
    """Primer idioma del sistema que Jayth conoce (uno de LANGS); si no hay ninguno, inglés."""
    tags = []
    try:
        from PySide6.QtCore import QLocale
        tags = list(QLocale.system().uiLanguages())
    except Exception:
        pass
    if not tags:
        tags = [os.environ.get(k, "") for k in ("LC_ALL", "LC_MESSAGES", "LANG")]
    for t in tags:
        code = (t or "").replace("_", "-").split("-")[0].split(".")[0].lower()
        if code in LANGS:
            return code
    return DEFAULT


def chosen():
    """Idioma elegido: JAYTH_LANG, luego el ajuste ui_language, luego el del sistema."""
    v = os.environ.get("JAYTH_LANG", "").strip().lower()
    if not v:
        try:
            with open(os.path.join(paths.DATA, "settings.json"), encoding="utf-8") as f:
                v = str(json.load(f).get("ui_language") or "auto").lower()
        except Exception:
            v = "auto"
    return v if v in LANGS else system_lang()


LANG = chosen()
CATALOG = {}
_MISSING = set()


def _load(lang):
    if lang == "es":
        return {}
    try:
        with open(os.path.join(paths.ASSETS, "i18n", lang + ".json"), encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if isinstance(v, str) and v}
    except Exception:
        return {}


CATALOG.update(_load(LANG))


def tr(text):
    """Traduce un texto de la interfaz escrito en español (si no hay traducción, lo devuelve tal cual)."""
    if LANG == "es" or not text:
        return text
    t = CATALOG.get(text)
    if t is None:
        _MISSING.add(text)
        return text
    return t


def _save_missing():
    out = os.environ.get("JAYTH_I18N_MISSING")
    if not out or not _MISSING:
        return
    try:
        old = set()
        if os.path.isfile(out):
            with open(out, encoding="utf-8") as f:
                old = set(json.load(f))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(sorted(old | _MISSING), f, ensure_ascii=False, indent=1)
    except Exception:
        pass


atexit.register(_save_missing)


# ------------------------------------------------------------ números y tamaños
UNITS = {"fr": {"B": "o", "KB": "Ko", "MB": "Mo", "GB": "Go", "TB": "To"}}     # octets en francés
COMMA = ("pt", "fr", "de", "it")            # idiomas con coma decimal (el español de Jayth usa punto)


def number(x, decimals=1):
    """Número con el separador decimal del idioma: 6.5 / 6,5."""
    s = "%.*f" % (decimals, x)
    return s.replace(".", ",") if LANG in COMMA else s


def unit(u):
    """Unidad de tamaño en el idioma de la interfaz: «GB»; en francés «Go»."""
    return UNITS.get(LANG, {}).get(u, u)


def cjk_spacing(text):
    """En japonés y chino, un espacio entre letras latinas o cifras y los caracteres CJK pegados a ellas, en frases que
    Jayth arma uniendo trozos («使用了 github和…» -> «使用了 github 和…»)."""
    if LANG not in CJK or not text:
        return text
    import re
    cjk = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    text = re.sub(r"([A-Za-z0-9\)\]])([%s])" % cjk, r"\1 \2", text)
    return re.sub(r"([%s])([A-Za-z0-9\(\[])" % cjk, r"\1 \2", text)


def size(n):
    """Tamaño legible: «6.5 GB»; en alemán «6,5 GB», en francés «6,5 Go» (con espacio que no se separa)."""
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            break
        n /= 1024
    return number(n, 0 if u in ("B", "KB") else 1) + (" " if LANG == "fr" else " ") + unit(u)
