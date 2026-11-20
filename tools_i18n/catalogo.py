# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Catálogos de traducción de Jayth (assets/i18n/<idioma>.json).

  python tools_i18n/catalogo.py claves [archivo.py ...]     textos marcados con tr("…") (todos los módulos si no se indica)
  python tools_i18n/catalogo.py pendientes en               textos marcados que aún no tienen traducción en en.json
  python tools_i18n/catalogo.py combinar                    une tools_i18n/partes/*.<idioma>.json en assets/i18n/<idioma>.json
  python tools_i18n/catalogo.py revisar                     comprueba los catálogos: faltan, sobran, %s y etiquetas HTML
  python tools_i18n/catalogo.py plantilla NOMBRE jayth/a.py …   crea o completa partes/NOMBRE.en.json y .pt.json con las claves
                                                                de esos módulos (lo ya traducido se conserva; lo nuevo, "")
  python tools_i18n/catalogo.py parte NOMBRE jayth/a.py …       comprueba esa parte: claves que faltan o vacías, sobrantes,
                                                                marcadores %s y etiquetas HTML (sale con error si hay algo)

Cada parte es un JSON {"texto en español": "traducción"}. Al combinar, lo ya traducido en el catálogo se conserva salvo
que una parte traiga otra traducción (gana la parte).
"""
import ast
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODS = RAIZ / "jayth"
CAT = RAIZ / "assets" / "i18n"
PARTES = Path(__file__).resolve().parent / "partes"
IDIOMAS = ("en", "pt")
FMT = re.compile(r"%(?:\([^)]+\))?[-#0 +]*\d*(?:\.\d+)?[sdifrxX%]")
TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def claves(archivos=None):
    out = {}
    for f in archivos or sorted(MODS.glob("*.py")) + [RAIZ / "app.py"]:
        f = Path(f)
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.setdefault(a.value, f.name)
    return out


def leer(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def guardar(p, d):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(dict(sorted(d.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def problemas(es, tr):
    malos = []
    if sorted(FMT.findall(es)) != sorted(FMT.findall(tr)):
        malos.append("marcadores %s distintos")
    if len(TAG.findall(es)) != len(TAG.findall(tr)):
        malos.append("etiquetas HTML distintas")
    if es.endswith("\n") != tr.endswith("\n"):
        malos.append("salto de línea final distinto")
    return malos


def main():
    modo = sys.argv[1]
    if modo == "claves":
        for k, f in claves(sys.argv[2:] or None).items():
            print("%-18s %r" % (f, k))
    elif modo == "pendientes":
        lang = sys.argv[2]
        cat = leer(CAT / (lang + ".json"))
        falta = {k: f for k, f in claves().items() if k not in cat}
        for k, f in falta.items():
            print("%-18s %r" % (f, k))
        print("— %d sin traducir al %s" % (len(falta), lang))
    elif modo == "combinar":
        for lang in IDIOMAS:
            cat = leer(CAT / (lang + ".json"))
            n = 0
            for p in sorted(PARTES.glob("*.%s.json" % lang)):
                d = leer(p)
                cat.update({k: v for k, v in d.items() if isinstance(v, str) and v.strip()})
                n += len(d)
            guardar(CAT / (lang + ".json"), cat)
            print("%s: %d entradas de las partes → %d en el catálogo" % (lang, n, len(cat)))
    elif modo == "plantilla":
        nombre, mods = sys.argv[2], sys.argv[3:]
        ks = claves(mods)
        for lang in IDIOMAS:
            p = PARTES / ("%s.%s.json" % (nombre, lang))
            d = leer(p)
            nuevo = {k: d.get(k, "") for k in ks}
            guardar(p, nuevo)
            print("%s: %d claves (%d sin traducir)" % (p.name, len(nuevo), sum(1 for v in nuevo.values() if not v)))
    elif modo == "parte":
        nombre, mods = sys.argv[2], sys.argv[3:]
        ks = claves(mods)
        mal = 0
        for lang in IDIOMAS:
            d = leer(PARTES / ("%s.%s.json" % (nombre, lang)))
            for k in ks:
                if not str(d.get(k, "")).strip():
                    mal += 1
                    print("[%s] falta o vacía: %r" % (lang, k[:100]))
            for k in d:
                if k not in ks:
                    mal += 1
                    print("[%s] sobra (no está marcada en esos módulos): %r" % (lang, k[:100]))
            for k, v in d.items():
                for pr in problemas(k, str(v)) if v else ():
                    mal += 1
                    print("[%s] %s: %r" % (lang, pr, k[:100]))
        print("%s: %d claves, %d problemas" % (nombre, len(ks), mal))
        sys.exit(1 if mal else 0)
    elif modo == "revisar":
        todas = claves()
        mal = 0
        for lang in IDIOMAS:
            cat = leer(CAT / (lang + ".json"))
            falta = [k for k in todas if k not in cat]
            sobra = [k for k in cat if k not in todas]
            print("== %s: %d marcadas, %d traducidas, %d faltan, %d sobran (textos dinámicos o ya no usados)"
                  % (lang, len(todas), len(cat), len(falta), len(sobra)))
            for k in falta[:40]:
                print("   falta (%s): %r" % (todas[k], k[:100]))
            for k, v in cat.items():
                for p in problemas(k, v):
                    mal += 1
                    print("   %s → %s: %r" % (p, lang, k[:90]))
        sys.exit(1 if mal else 0)


if __name__ == "__main__":
    main()
