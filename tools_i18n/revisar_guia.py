# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Comprueba que la guía del agente (assets/guia/<idioma>.md) sigue al día con la interfaz.

  python tools_i18n/revisar_guia.py          sale con error si falta algo

- Hay una guía por cada idioma de Jayth (i18n.LANGS) y todas tienen los mismos temas («## »), en el mismo orden de cantidad.
- Cada guía nombra, tal como se ven en su idioma (catálogos de assets/i18n), las páginas, secciones y opciones de
  Ajustes y las entradas del menú del perfil. Así, si se añade o se cambia un ajuste, la publicación avisa de que hay
  que documentarlo (la guía va dentro de cada versión: el agente siempre consulta la de la versión instalada).
"""
import ast, json, re, sys, unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GUIA = RAIZ / "assets" / "guia"
CAT = RAIZ / "assets" / "i18n"
APP = "Jayth"
sys.path.insert(0, str(RAIZ))
from jayth import i18n  # noqa: E402  (la lista de idiomas)


def _tr(n):
    if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args and isinstance(n.args[0], ast.Constant):
        return n.args[0].value
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod):
        return _tr(n.left)
    return None


def etiquetas():
    """Textos (en español, tal como están en tr()) que la guía tiene que nombrar."""
    out = []
    st = ast.parse((RAIZ / "jayth" / "settings_ui.py").read_text(encoding="utf-8"))
    for n in ast.walk(st):
        if isinstance(n, ast.Tuple) and len(n.elts) == 4 and isinstance(n.elts[0], ast.Constant) and _tr(n.elts[1]):
            out.append(("página de Ajustes", _tr(n.elts[1])))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "_section" and len(n.args) > 1 and _tr(n.args[1]):
            out.append(("sección de Ajustes", _tr(n.args[1])))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "field" and len(n.args) > 2 and _tr(n.args[2]):
            out.append(("opción de Ajustes", _tr(n.args[2])))
    dt = ast.parse((RAIZ / "jayth" / "desktop.py").read_text(encoding="utf-8"))
    for fn in ast.walk(dt):
        if isinstance(fn, ast.FunctionDef) and fn.name == "_sidebar":
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "addAction" and len(n.args) > 1 and _tr(n.args[1]):
                    out.append(("menú del perfil", _tr(n.args[1])))
    return out


def _norm(s):
    s = unicodedata.normalize("NFC", s).casefold()
    s = s.replace("…", "").replace("*", "").replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", s).strip(" .:")


def main():
    problemas = 0
    temas = {}
    for lang in i18n.LANGS:
        p = GUIA / (lang + ".md")
        if not p.is_file():
            print("FALTA la guía %s" % p)
            problemas += 1
            continue
        temas[lang] = len(re.findall(r"(?m)^## ", p.read_text(encoding="utf-8")))
    if len(set(temas.values())) > 1:
        print("Las guías no tienen los mismos temas: %s" % temas)
        problemas += 1
    req = etiquetas()
    for lang in temas:
        cat = {} if lang == "es" else json.loads((CAT / (lang + ".json")).read_text(encoding="utf-8"))
        texto = _norm((GUIA / (lang + ".md")).read_text(encoding="utf-8"))
        faltan = []
        for tipo, es in req:
            t = es if lang == "es" else cat.get(es, es)
            if t.count("%s") > 1 or "%d" in t:
                continue                                   # frases con varios datos: se describen con otras palabras
            if _norm(t.replace("%s", APP)) not in texto:
                faltan.append("%s «%s»" % (tipo, t.replace("%s", APP)))
        for f in faltan:
            print("[%s] la guía no nombra la %s" % (lang, f) if False else "[%s] no aparece: %s" % (lang, f))
        problemas += len(faltan)
    print("guía de Jayth: %d etiquetas comprobadas por idioma, %d problemas" % (len(req), problemas))
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
