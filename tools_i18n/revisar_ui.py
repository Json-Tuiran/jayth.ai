# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Comprueba que los textos de la interfaz caben en cada idioma (sin abrir ventanas en pantalla).

  python tools_i18n/revisar_ui.py de            un idioma
  python tools_i18n/revisar_ui.py todos         todos los de Jayth
  python tools_i18n/revisar_ui.py de --ancho 1100 --alto 700     con una ventana más pequeña

Abre la ventana principal, cada página de Ajustes y los diálogos principales y, para cada elemento visible, compara el
ancho que necesita su texto con el que tiene: botones, casillas y etiquetas de una línea que quedan cortados, y listas
desplegables normales cuya opción no cabe. Las etiquetas con ajuste de línea o que ya terminan en «…» no cuentan.
Sale con error si encuentra algo (para usarlo en la compilación automática)."""
import os, re, sys, json, shutil, tempfile, subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def revisar(lang, ancho, alto):
    home = tempfile.mkdtemp(prefix="jayth_ui_")
    os.makedirs(os.path.join(home, "data"))
    dummy = os.path.join(home, "m.gguf")
    open(dummy, "wb").write(b"x")
    json.dump({"setup_done": True, "quick_hotkey": "", "models_scan_init": True, "llama_exe": dummy, "user_name": "Alex",
               "models": [{"id": "m1", "name": "Qwen3.8-27B · UD-Q4_K_S", "path": dummy, "size": 1}], "active_model": "m1",
               "mcp_servers": [{"name": "GitHub", "url": "https://api.githubcopilot.com/mcp/", "enabled": False}]},
              open(os.path.join(home, "data", "settings.json"), "w"))
    os.environ.update(JAYTH_HOME=home, QT_QPA_PLATFORM="offscreen", JAYTH_LANG=lang, JAYTH_NO_HOTKEY="1")
    sys.path.insert(0, RAIZ)
    from PySide6.QtWidgets import (QApplication, QPushButton, QToolButton, QLabel, QCheckBox, QRadioButton, QComboBox, QWidget,
                                   QAbstractButton)
    from PySide6.QtGui import QFontDatabase, QTextDocument
    app = QApplication.instance() or QApplication(sys.argv)
    if os.name == "nt":                          # sin ventanas Qt no ve las fuentes del sistema
        for f in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "segmdl2.ttf", "YuGothR.ttc", "msyh.ttc"):
            QFontDatabase.addApplicationFont(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f))
    from jayth import theme, core
    theme.apply(app, "dark")
    from jayth import desktop
    from jayth.settings_ui import SettingsDialog
    from jayth.widgets import ElideCombo
    core.load_sessions()

    def spin():
        for _ in range(4):
            app.processEvents()

    problemas = []

    def plano(t):
        if "<" in t and ">" in t:
            d = QTextDocument()
            d.setHtml(t)
            return d.toPlainText()
        return t

    def mirar(raiz, donde):
        for w in raiz.findChildren(QWidget):
            if not w.isVisibleTo(raiz) or w.width() <= 1:
                continue
            fm = w.fontMetrics()
            if isinstance(w, (QPushButton, QToolButton, QCheckBox, QRadioButton)):
                t = w.text().replace("&", "")
                if not t.strip() or getattr(w, "switch", None) is not None or w.__class__.__name__ == "Switch":
                    continue
                need = w.sizeHint().width()
                if need > w.width() + 2:
                    problemas.append((donde, w.__class__.__name__, t, need - w.width()))
            elif isinstance(w, QLabel):
                t = w.text()
                if not t or w.wordWrap() or w.pixmap() is not None and not w.pixmap().isNull() or t.endswith("…") \
                        or w.__class__.__name__ in ("ElidedLabel", "FitLabel"):
                    continue
                p = plano(t)
                if "\n" in p:
                    continue
                need = fm.horizontalAdvance(p) + w.contentsMargins().left() + w.contentsMargins().right()
                if need > w.width() + 2:
                    problemas.append((donde, "QLabel", p, need - w.width()))
            elif isinstance(w, QComboBox) and not isinstance(w, ElideCombo):
                t = w.currentText()
                need = fm.horizontalAdvance(t) + 40
                if t and need > w.width() + 2:
                    problemas.append((donde, "QComboBox", t, need - w.width()))

    w = desktop.Main()
    w.tray.hide()
    w.resize(ancho, alto)
    w.show()
    spin()
    mirar(w, "Ventana principal")
    d = SettingsDialog(w)
    d.resize(min(1000, ancho), min(700, alto))
    d.show()
    for i in range(d.nav.count()):
        d.nav.setCurrentRow(i)
        spin()
        mirar(d.pages.currentWidget(), "Ajustes › " + d.nav.item(i).text())
    mirar(d, "Ajustes (barra lateral)")
    d.close()
    try:
        from jayth.wizard import ModelsDialog
        md = ModelsDialog(w)
        md.show()
        spin()
        mirar(md, "Modelos")
        md.close()
    except Exception as e:
        problemas.append(("Modelos", "error", str(e), 0))
    try:
        from jayth.feedback import FeedbackDialog
        fd = FeedbackDialog(w, "idea")
        fd.show()
        spin()
        mirar(fd, "Comentarios")
        fd.close()
    except Exception as e:
        problemas.append(("Comentarios", "error", str(e), 0))
    w.close()
    shutil.rmtree(home, ignore_errors=True)
    return problemas


def main():
    args = sys.argv[1:]
    ancho = int(args[args.index("--ancho") + 1]) if "--ancho" in args else 1366
    alto = int(args[args.index("--alto") + 1]) if "--alto" in args else 768
    langs = [a for a in args if not a.startswith("--") and not a.isdigit()]
    if not langs or langs == ["todos"]:
        sys.path.insert(0, RAIZ)
        from jayth import i18n
        langs = list(i18n.LANGS)
    if len(langs) > 1:                       # cada idioma en su propio proceso (el idioma se fija al arrancar)
        total = 0
        for l in langs:
            r = subprocess.run([sys.executable, __file__, l, "--ancho", str(ancho), "--alto", str(alto)])
            total += r.returncode != 0
        sys.exit(1 if total else 0)
    lang = langs[0]
    probs = revisar(lang, ancho, alto)
    for donde, cls, t, falta in probs:
        print("[%s] %s · %s: «%s» (faltan %d px)" % (lang, donde, cls, t[:90], falta))
    print("interfaz en %s: %d textos que no caben (%dx%d)" % (lang, len(probs), ancho, alto))
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
