# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Ayuda a marcar los textos de la interfaz con tr() (ver jayth/i18n.py).

  python tools_i18n/marcar.py lista jayth/quick.py            candidatos: «línea  contexto  texto»
  python tools_i18n/marcar.py aplicar jayth/quick.py 12 40 41  envuelve con tr(...) los candidatos de esas líneas
  python tools_i18n/marcar.py aplicar jayth/quick.py todo      todos los candidatos (revisar el diff después)

Un candidato es un texto literal que parece español o que se pasa a una función de interfaz (setText, QLabel, btn…),
sin contar docstrings, claves de diccionario, comparaciones ni textos ya marcados. Añade «from .i18n import tr» si falta.
"""
import ast
import re
import sys
from pathlib import Path

ES = re.compile(r"[áéíóúñü¿¡ÁÉÍÓÚÑ«»…]|\b(el|la|los|las|de|del|un|una|unos|para|con|sin|que|en|por|no|se|al|tu|tus|su|sus|"
                r"es|está|hay|más|ya|este|esta|esto|ese|esa|aquí|ahora|cada|todo|todos|nada|algo|otro|otra)\b", re.I)
UI = {"setText", "setToolTip", "setPlaceholderText", "setWindowTitle", "setStatusTip", "setWhatsThis", "addAction", "addMenu",
      "QAction", "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox", "QToolButton", "QMenu", "btn", "lbl",
      "information", "warning", "question", "critical", "about", "getText", "getItem", "getInt", "getOpenFileName",
      "getSaveFileName", "getExistingDirectory", "getOpenFileNames", "setTitle", "addTab", "insertTab", "setTabText",
      "setTabToolTip", "addItem", "insertItem", "setItemText", "setHeaderLabels", "showMessage", "setSpecialValueText",
      "setPrefix", "setSuffix", "field", "_section", "section", "notify", "toast", "set_status", "status", "setWindowIconText",
      "setAccessibleName", "setAccessibleDescription", "QListWidgetItem", "QTreeWidgetItem", "OptionRow", "set_text"}
NO = {"setObjectName", "setProperty", "property", "objectName", "join", "split", "replace", "startswith", "endswith", "strip",
      "lstrip", "rstrip", "get", "pop", "setdefault", "getattr", "hasattr", "setattr", "open", "compile", "match", "search",
      "sub", "findall", "fullmatch", "finditer", "icon", "pix", "set_icon", "pix_label", "QIcon", "QKeySequence", "QShortcut",
      "isfile", "isdir", "exists", "makedirs", "listdir", "remove", "rename", "environ", "Popen", "run", "check_output", "call",
      "encode", "decode", "format_exc", "debug", "log", "loads", "dumps", "load", "dump", "QColor", "QFont", "setStyleSheet",
      "restyle", "findData", "connect", "emit", "tr", "endswith", "update", "snapshot", "translate"}


def _name(f):
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def candidatos(src):
    tree = ast.parse(src)
    padre = {}
    for n in ast.walk(tree):
        for h in ast.iter_child_nodes(n):
            padre[h] = n
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                doc.add(b.value)
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)) or n in doc:
            continue
        s = n.value
        if len(s.strip()) < 2 or isinstance(padre.get(n), ast.JoinedStr):
            continue
        p = padre.get(n)
        # ya marcado, clave de diccionario, índice, comparación
        if isinstance(p, ast.Call) and _name(p.func) == "tr":
            continue
        if isinstance(p, ast.Dict) and n in p.keys:
            continue
        if isinstance(p, ast.Subscript) or isinstance(p, ast.Compare):
            continue
        if isinstance(p, (ast.Tuple, ast.List, ast.Set)) and isinstance(padre.get(p), ast.Compare):
            continue
        # contexto: función a la que se pasa (directa o como argumento con nombre)
        ctx = ""
        q = p
        if isinstance(q, ast.keyword):
            ctx = "%s=" % q.arg
            q = padre.get(q)
        if isinstance(q, ast.Call):
            ctx = _name(q.func) + ("(" + ctx + ")" if ctx else "")
        elif isinstance(q, ast.BinOp) and isinstance(q.op, ast.Mod):
            ctx = "%"
        elif isinstance(q, ast.Assign):
            ctx = "= " + ",".join(_name(t) or getattr(t, "id", "?") for t in q.targets)
        func = ctx.split("(")[0]
        if func in NO or (isinstance(p, ast.keyword) and p.arg in ("objectName", "kind", "fmt", "name", "key", "ico", "icon")):
            continue
        parece_es = bool(ES.search(s))
        identificador = re.fullmatch(r"[\w.\-/:\\%{}()*+#@ ]*", s) is not None and " " not in s.strip()
        if identificador and not (func in UI and s[:1].isupper()):
            continue
        if not parece_es and func not in UI:
            continue
        out.append((n.lineno, n.col_offset, n.end_lineno, n.end_col_offset, ctx, s))
    return sorted(out)


def _offset(lines, ln, col):
    return sum(len(l) for l in lines[:ln - 1]) + len(lines[ln - 1].encode("utf-8")[:col].decode("utf-8", "ignore"))


def aplicar(path, sel):
    src = Path(path).read_text(encoding="utf-8")
    cands = candidatos(src)
    if sel != ["todo"]:
        quiero = {int(x) for x in sel}
        cands = [c for c in cands if c[0] in quiero]
    lines = src.splitlines(keepends=True)
    cambios = []
    for ln, col, eln, ecol, ctx, s in cands:
        a, b = _offset(lines, ln, col), _offset(lines, eln, ecol)
        cambios.append((a, b))
    for a, b in sorted(cambios, reverse=True):
        src = src[:a] + "tr(" + src[a:b] + ")" + src[b:]
    if cambios and not re.search(r"^from \.i18n import .*\btr\b", src, re.M):
        # tras el último «from . import» / «from .x import» de la cabecera
        m = list(re.finditer(r"^from \.[\w ,.]* import .*(?:\n[ \t]+.*)*$", src[:20000], re.M))
        pos = m[-1].end() if m else 0
        src = src[:pos] + "\nfrom .i18n import tr" + src[pos:]
    ast.parse(src)                        # que siga siendo Python válido
    Path(path).write_text(src, encoding="utf-8")
    print("%s: %d textos marcados" % (path, len(cambios)))


if __name__ == "__main__":
    modo, path = sys.argv[1], sys.argv[2]
    if modo == "lista":
        for ln, col, eln, ecol, ctx, s in candidatos(Path(path).read_text(encoding="utf-8")):
            print("%5d  %-22s %r" % (ln, ctx[:22], s if len(s) < 110 else s[:107] + "…"))
    else:
        aplicar(path, sys.argv[3:])
