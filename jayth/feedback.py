"""Enviar comentarios (errores, sugerencias, preguntas). No hay servidor: se abre una incidencia prellenada en
GitHub y la persona revisa exactamente qué se envía antes de publicarla. Nada sale del equipo sin su clic."""
import os, sys, platform, webbrowser, urllib.parse
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QCheckBox, QButtonGroup,
                               QPushButton, QMessageBox)
from . import APP_NAME, __version__, core, paths
from .theme import C, icon
from .wizard import btn, lbl
from .updater import installed, REPO

KINDS = [("error", "Informar de un error", "est_error", "bug"), ("idea", "Sugerir una mejora", "vfx_magia", "enhancement"),
         ("pregunta", "Hacer una pregunta", "ui_ayuda", "question")]


def tech_info():
    cfg = core.SET.snapshot()
    m = core.active_model(cfg)
    lines = ["- %s %s (%s %s)" % (APP_NAME, __version__, installed().get("kind", ""), (installed().get("sha") or "")[:7]),
             "- Sistema: %s %s · Python %s" % (platform.system(), platform.release(), platform.python_version()),
             "- Motor: llama.cpp %s · %s · contexto %s" % (cfg["llama_tag"] or "—", cfg["backend"], cfg["n_ctx"]),
             "- Modelo: %s %s" % (core.model_title(m) if m else ("externo" if cfg["llm_mode"] == "external" else "ninguno"), core.model_quant(m) if m else "")]
    return "\n".join(lines)


def log_tail(n=25):
    t = core.LLM_MGR.tail(n)
    # sin rutas personales: se sustituye la carpeta del usuario
    home = os.path.expanduser("~")
    return t.replace(home, "%USERPROFILE%") if t else ""


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, kind="error", context=""):
        super().__init__(parent)
        self.setWindowTitle("Enviar comentarios")
        self.resize(620, 600)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(lbl("Enviar comentarios", "h1"))
        v.addWidget(lbl("Tu comentario se publica como una incidencia en GitHub (%s). Antes de enviarlo verás todo el texto; "
                        "puedes editarlo o quitar lo que no quieras compartir." % REPO, "muted"))
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        for k, label, ico, _ in KINDS:
            b = QPushButton(label)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setIcon(icon(ico, C["acc"], 14))
            b.setProperty("k", k)
            self.group.addButton(b)
            row.addWidget(b)
            if k == kind:
                b.setChecked(True)
        row.addStretch(1)
        v.addLayout(row)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Resumen en una frase (p. ej.: El modelo no arranca tras actualizar)")
        v.addWidget(self.title)
        self.body = QPlainTextEdit(context)
        self.body.setPlaceholderText("Cuéntanos qué pasó o qué te gustaría. Si es un error: qué hiciste, qué esperabas y qué ocurrió.")
        v.addWidget(self.body, 1)
        self.chk_info = QCheckBox("Incluir información técnica (versión, sistema, motor y modelo)")
        self.chk_info.setChecked(True)
        self.chk_log = QCheckBox("Incluir las últimas líneas del registro del modelo")
        v.addWidget(self.chk_info)
        v.addWidget(self.chk_log)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("mono")
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(120)
        v.addWidget(lbl("Se incluirá:", "faint"))
        v.addWidget(self.preview)
        for w in (self.chk_info, self.chk_log):
            w.toggled.connect(self._refresh)
        self._refresh()
        b = QHBoxLayout()
        b.addWidget(btn("Copiar texto", cb=self._copy, ico="acc_copiar"))
        b.addStretch(1)
        b.addWidget(btn("Cancelar", cb=self.reject))
        b.addWidget(btn("Continuar en GitHub", "primary", self._send, "acc_abrir_externo"))
        v.addLayout(b)

    def _extra(self):
        parts = []
        if self.chk_info.isChecked():
            parts.append("### Información técnica\n" + tech_info())
        if self.chk_log.isChecked() and log_tail():
            parts.append("### Registro del modelo\n```\n" + log_tail() + "\n```")
        return "\n\n".join(parts)

    def _refresh(self):
        self.preview.setPlainText(self._extra() or "(nada adicional)")

    def _kind(self):
        b = self.group.checkedButton()
        k = b.property("k") if b else "error"
        return next(x for x in KINDS if x[0] == k)

    def _text(self):
        body = self.body.toPlainText().strip()
        extra = self._extra()
        return (body + ("\n\n" + extra if extra else "")).strip()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.title.text() + "\n\n" + self._text())

    def _send(self):
        if not self.title.text().strip() or not self.body.toPlainText().strip():
            return QMessageBox.information(self, APP_NAME, "Escribe un resumen y una descripción.")
        k = self._kind()
        body = self._text()
        if len(body) > 6000:                      # limite practico de una URL
            body = body[:6000] + "\n\n(texto recortado)"
        url = "https://github.com/%s/issues/new?%s" % (REPO, urllib.parse.urlencode({"title": self.title.text().strip(), "body": body, "labels": k[3]}))
        webbrowser.open(url)
        QMessageBox.information(self, APP_NAME, "Se abrió GitHub en tu navegador. Revisa el texto y pulsa «Submit new issue» para enviarlo.\n"
                                "(Necesitas una cuenta de GitHub; si no la tienes, usa «Copiar texto».)")
        self.accept()
