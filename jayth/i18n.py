# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Idioma de la interfaz: español (el original), inglés y portugués.

- Los textos se escriben en español en el código y se envuelven con tr(): tr("Guardar"), tr("Descargando %s") % nombre.
- Las traducciones están en assets/i18n/<idioma>.json ({"texto en español": "traducción"}). Lo que falte se ve en español.
- El idioma se decide una sola vez al arrancar (antes de importar el resto): el ajuste «ui_language» de settings.json
  (auto = el del sistema), o la variable JAYTH_LANG (pruebas). Cambiarlo pide reiniciar Jayth.
- JAYTH_I18N_MISSING=<archivo>: al salir, guarda ahí los textos que se pidieron sin traducción (para completar catálogos).
"""
import os, json, atexit
from . import paths

LANGS = ("es", "en", "pt")
NAMES = {"es": "Español", "en": "English", "pt": "Português"}
DEFAULT = "en"          # sistemas en otros idiomas: la interfaz en inglés


def system_lang():
    """Primer idioma del sistema que Jayth conoce (es, en o pt); si no hay ninguno, inglés."""
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
