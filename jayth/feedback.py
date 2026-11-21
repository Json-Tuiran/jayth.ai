# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Enviar comentarios (errores, sugerencias, preguntas e informes de cierres inesperados).

- Directo, sin cuenta: el texto va al puente de comentarios (packaging/reportes/worker.js, un Cloudflare Worker) y llega
  como incidencia a un repositorio PRIVADO del dueño. No se publica.
- Con cuenta de GitHub: se abre una incidencia pública prellenada.
En los dos casos la persona ve exactamente qué se envía antes de hacerlo; nada sale del equipo sin su clic.
Los errores inesperados de Jayth se guardan en el equipo y se ofrece enviarlos (nunca se mandan solos)."""
import os, sys, json, time, platform, traceback, webbrowser, urllib.parse, urllib.request
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QCheckBox, QButtonGroup,
                               QPushButton, QMessageBox)
from . import APP_NAME, __version__, core, paths, osys
from .theme import C, icon
from .wizard import btn, lbl
from .updater import installed, REPO
from .i18n import tr, LANG

# dirección del puente de comentarios ("" = sin puente: solo GitHub o copiar el texto). JAYTH_REPORT_URL la cambia (pruebas)
REPORT_URL = os.environ.get("JAYTH_REPORT_URL", "https://jayth-reportes.jsontuiran.workers.dev")
SENT = os.path.join(paths.DATA, "informes_enviados.json")
CRASH = os.path.join(paths.DATA, "ultimo_error.json")

KINDS = [("error", tr("Informar de un error"), "est_error", "bug"), ("idea", tr("Sugerir una mejora"), "vfx_magia", "enhancement"),
         ("pregunta", tr("Hacer una pregunta"), "ui_ayuda", "question")]
CRASH_KIND = ("cierre", tr("Error inesperado"), "est_error", "bug")


def tech_info():
    cfg = core.SET.snapshot()
    m = core.active_model(cfg)
    lines = ["- %s %s (%s %s)" % (APP_NAME, __version__, installed().get("kind", ""), (installed().get("sha") or "")[:7]),
             "- Sistema: %s · %s · Python %s" % (osys.os_label(), platform.machine(), platform.python_version()),
             "- Motor: llama.cpp %s · %s · contexto %s%s" % (cfg["llama_tag"] or "—", cfg["backend"], core.effective_ctx(cfg),
                                                             " (automático)" if not int(cfg.get("n_ctx") or 0) else ""),
             "- Modelo: %s %s" % (core.model_title(m) if m else ("externo" if cfg["llm_mode"] == "external" else "ninguno"), core.model_quant(m) if m else "")]
    return "\n".join(lines)


def anonymize(text):
    """Sin la carpeta personal del usuario (suele llevar su nombre)."""
    home = os.path.expanduser("~")
    return text.replace(home, "%USERPROFILE%" if osys.WIN else "~") if text else ""


def bridge():
    return REPORT_URL.rstrip("/")


def send_report(kind, title, body, with_system=True):
    """Envía el informe por el puente. Devuelve el número de la incidencia o lanza RuntimeError con un texto claro."""
    data = {"kind": kind, "title": title.strip()[:140], "body": body, "version": __version__,
            "os": ("%s · %s" % (osys.os_label(), platform.machine())) if with_system else "", "lang": LANG if with_system else ""}
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(bridge() + "/reporte", data=raw, method="POST",
                                 headers={"Content-Type": "application/json", "X-Jayth": "1", "User-Agent": "Jayth/" + __version__})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            res = json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            res = {}
        raise RuntimeError(res.get("error") or ("HTTP %d" % e.code))
    except Exception as e:
        raise RuntimeError(tr("No hay conexión con el servicio de comentarios (%s).") % (getattr(e, "reason", None) or e))
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or tr("El servicio de comentarios no aceptó el informe."))
    try:                                         # para que la persona sepa qué mandó y su número
        sent = json.load(open(SENT, encoding="utf-8")) if os.path.isfile(SENT) else []
    except (OSError, ValueError):
        sent = []
    sent.append({"number": res.get("number"), "kind": kind, "title": data["title"], "date": time.strftime("%Y-%m-%d %H:%M")})
    try:
        os.makedirs(paths.DATA, exist_ok=True)
        with open(SENT, "w", encoding="utf-8") as f:
            json.dump(sent[-200:], f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return res.get("number")


# ---- errores inesperados: se guardan y se ofrece enviarlos
def record_crash(exc_type=None, exc=None, tb=None, raw=None):
    """Guarda el último error inesperado (sin rutas personales). raw: el texto de un cierre grave del proceso anterior.
    Devuelve el informe guardado."""
    trace = raw if raw is not None else "".join(traceback.format_exception(exc_type, exc, tb))
    trace = anonymize(trace)[-12000:]
    d = {"date": time.strftime("%Y-%m-%d %H:%M"), "version": __version__, "trace": trace, "sent": False, "offered": False}
    try:
        os.makedirs(paths.DATA, exist_ok=True)
        with open(CRASH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return d


def pending_crash():
    """El último error inesperado si aún no se envió ni descartó (de esta versión), o None."""
    try:
        d = json.load(open(CRASH, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if not d.get("sent") and not d.get("offered") and d.get("version") == __version__ and d.get("trace") else None


def mark_offered():
    try:
        d = json.load(open(CRASH, encoding="utf-8"))
        d["offered"] = True
        with open(CRASH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except (OSError, ValueError):
        pass


def crash_title(d):
    last = [l.strip() for l in (d.get("trace") or "").strip().splitlines() if l.strip()]
    return (tr("Error inesperado: %s") % last[-1])[:140] if last else tr("Error inesperado")


def install_crash_capture(app, on_crash):
    """Errores de Python no capturados -> se guardan y se llama a on_crash(informe) una vez por sesión. Y un registro de
    fallos graves (el proceso se cae del todo): si el arranque anterior dejó uno, se guarda como informe pendiente."""
    import faulthandler
    path = os.path.join(paths.DATA, "fallo_grave.log")
    try:
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            prev = open(path, encoding="utf-8", errors="replace").read()
            if "Traceback" in prev or "Fatal Python error" in prev or "Windows fatal exception" in prev:
                record_crash(raw=prev)
        os.makedirs(paths.DATA, exist_ok=True)
        app._fault_file = open(path, "w", encoding="utf-8")
        faulthandler.enable(app._fault_file)

        def clean_exit():                             # cierre normal: lo anotado no fue un fallo que tumbara Jayth
            try:
                faulthandler.disable()
                app._fault_file.close()
                open(path, "w").close()
            except Exception:
                pass
        app.aboutToQuit.connect(clean_exit)
    except Exception:
        pass
    prev_hook = sys.excepthook
    state = {"offered": False}

    def hook(t, e, tb):
        try:
            prev_hook(t, e, tb)                       # también a la consola, como siempre
        except Exception:
            pass
        if issubclass(t, (KeyboardInterrupt, SystemExit)):
            return
        d = record_crash(t, e, tb)
        if not state["offered"]:
            state["offered"] = True
            try:
                on_crash(d)
            except Exception:
                pass
    sys.excepthook = hook


def dismiss_crash():
    try:
        os.remove(CRASH)
    except OSError:
        pass


def crash_text(d):
    return tr("Jayth tuvo un error inesperado el %s.\n\nQué estaba haciendo: ") % d["date"] + "\n\n```\n" + d["trace"].strip() + "\n```"


def log_tail(n=25):
    t = core.LLM_MGR.tail(n)
    # sin rutas personales: se sustituye la carpeta del usuario
    home = os.path.expanduser("~")
    return t.replace(home, "%USERPROFILE%" if osys.WIN else "~") if t else ""


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, kind="error", context="", title=""):
        super().__init__(parent)
        self.setWindowTitle(tr("Enviar comentarios"))
        self.resize(620, 600)
        self.crash = kind == "cierre"
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(lbl(tr("Enviar comentarios"), "h1"))
        if bridge():
            v.addWidget(lbl(tr("Llega directamente al equipo de %s, de forma privada: no se publica y no necesitas ninguna cuenta. "
                               "Antes de enviarlo ves todo el texto; puedes editarlo o quitar lo que no quieras compartir.") % APP_NAME,
                            "muted"))
        else:
            v.addWidget(lbl(tr("Tu comentario se publica como una incidencia en GitHub (%s). Antes de enviarlo verás todo el texto; "
                               "puedes editarlo o quitar lo que no quieras compartir.") % REPO, "muted"))
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        for k, label, ico, _ in KINDS + ([CRASH_KIND] if self.crash else []):
            b = QPushButton(label)
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setIcon(icon(ico, C["acc"], 14))
            b.ensurePolished()                        # la letra que pone la hoja de estilos
            bold = b.font()                           # marcado va en negrita: el ancho, el de la negrita (si no, se cortaba)
            bold.setWeight(bold.Weight.DemiBold)
            from PySide6.QtGui import QFontMetrics
            b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(label) + 44)
            b.setProperty("k", k)
            self.group.addButton(b)
            row.addWidget(b)
            if k == kind:
                b.setChecked(True)
        row.addStretch(1)
        v.addLayout(row)
        self.title = QLineEdit(title)
        self.title.setPlaceholderText(tr("Resumen en una frase (p. ej.: El modelo no arranca tras actualizar)"))
        v.addWidget(self.title)
        self.body = QPlainTextEdit(context)
        self.body.setPlaceholderText(tr("Cuéntanos qué pasó o qué te gustaría. Si es un error: qué hiciste, qué esperabas y qué ocurrió."))
        v.addWidget(self.body, 1)
        self.chk_info = QCheckBox(tr("Incluir información técnica (versión, sistema, motor y modelo)"))
        self.chk_info.setChecked(True)
        self.chk_log = QCheckBox(tr("Incluir las últimas líneas del registro del modelo"))
        v.addWidget(self.chk_info)
        v.addWidget(self.chk_log)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("mono")
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(120)
        v.addWidget(lbl(tr("Se incluirá:"), "faint"))
        v.addWidget(self.preview)
        for w in (self.chk_info, self.chk_log):
            w.toggled.connect(self._refresh)
        self._refresh()
        b = QHBoxLayout()
        b.addWidget(btn(tr("Copiar texto"), cb=self._copy, ico="acc_copiar"))
        b.addStretch(1)
        b.addWidget(btn(tr("Cancelar"), cb=self.reject))
        if bridge():                              # sin cuenta, directo y privado; GitHub queda para quien lo prefiera
            self.b_github = btn(tr("Publicar en GitHub"), cb=self._send, ico="acc_abrir_externo")
            self.b_github.setToolTip(tr("Abre una incidencia pública en GitHub (necesitas una cuenta)"))
            b.addWidget(self.b_github)
            self.b_send = btn(tr("Enviar"), "primary", self._send_direct, "lista_subir")
            b.addWidget(self.b_send)
        else:
            b.addWidget(btn(tr("Continuar en GitHub"), "primary", self._send, "acc_abrir_externo"))
        v.addLayout(b)

    def _extra(self):
        parts = []
        if self.chk_info.isChecked():
            parts.append("### Información técnica\n" + tech_info())
        if self.chk_log.isChecked() and log_tail():
            parts.append("### Registro del modelo\n```\n" + log_tail() + "\n```")
        return "\n\n".join(parts)

    def _refresh(self):
        self.preview.setPlainText(self._extra() or tr("(nada adicional)"))

    def _kind(self):
        b = self.group.checkedButton()
        k = b.property("k") if b else "error"
        return next(x for x in KINDS + [CRASH_KIND] if x[0] == k)

    def _text(self):
        body = self.body.toPlainText().strip()
        extra = self._extra()
        return (body + ("\n\n" + extra if extra else "")).strip()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.title.text() + "\n\n" + self._text())

    def _send_direct(self):
        if not self.title.text().strip() or not self.body.toPlainText().strip():
            return QMessageBox.information(self, APP_NAME, tr("Escribe un resumen y una descripción."))
        from .wizard import run_bg
        k = self._kind()
        title, body = self.title.text().strip(), self._text()
        self.b_send.setEnabled(False)
        self.b_send.setText(tr("Enviando…"))

        def done(r):
            self.b_send.setEnabled(True)
            self.b_send.setText(tr("Enviar"))
            if isinstance(r, Exception):
                return QMessageBox.warning(self, APP_NAME, tr("No se pudo enviar: %s\n\nPuedes intentarlo más tarde, usar «Copiar texto» o "
                                                              "publicarlo en GitHub.") % r)
            if self.crash:
                try:
                    d = json.load(open(CRASH, encoding="utf-8"))
                    d["sent"] = True
                    with open(CRASH, "w", encoding="utf-8") as f:
                        json.dump(d, f, ensure_ascii=False, indent=1)
                except (OSError, ValueError):
                    pass
            QMessageBox.information(self, APP_NAME, (tr("¡Gracias! Lo recibimos (informe n.º %s).") % r) if r else tr("¡Gracias! Lo recibimos."))
            self.accept()
        run_bg(lambda: send_report(k[0], title, body, self.chk_info.isChecked()), done)

    def _send(self):
        if not self.title.text().strip() or not self.body.toPlainText().strip():
            return QMessageBox.information(self, APP_NAME, tr("Escribe un resumen y una descripción."))
        k = self._kind()
        body = self._text()
        if len(body) > 6000:                      # limite practico de una URL
            body = body[:6000] + "\n\n(texto recortado)"
        url = "https://github.com/%s/issues/new?%s" % (REPO, urllib.parse.urlencode({"title": self.title.text().strip(), "body": body, "labels": k[3]}))
        webbrowser.open(url)
        QMessageBox.information(self, APP_NAME, tr("Se abrió GitHub en tu navegador. Revisa el texto y pulsa «Submit new issue» para enviarlo.\n"
                                "(Necesitas una cuenta de GitHub; si no la tienes, usa «Copiar texto».)"))
        self.accept()
