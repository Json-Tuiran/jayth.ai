# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Instalar, ver y quitar el generador de imágenes (imagegen) desde Ajustes o desde una tarjeta en el chat."""
import os
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QMessageBox
from . import APP_NAME, core, osys, imagegen as IG, provision as P, hardware as HW
from .i18n import tr
from .theme import C
from .wizard import btn, lbl

GB = 1024 ** 3


def fit_text(cfg, m):
    """Si el modelo cabe en la memoria de este equipo y cuánto suele tardar."""
    try:
        total = HW.ram()[0]
    except Exception:
        total = 0
    w, h = IG.pick_size(cfg)
    need = IG.need_bytes(m, w, h)
    if not total:
        room = ""
    elif need <= total * 0.55:
        room = tr("Cabe bien en la memoria de tu equipo.")
    elif need <= total - 2.5 * GB:
        room = tr("Cabe justo en tu equipo: si va lento, cierra otros programas.")
    else:
        room = tr("Puede no caber en la memoria de tu equipo (necesita unos %s).") % P.fmt_bytes(need)
    speed = tr("Con tarjeta gráfica suele tardar menos de un minuto por imagen.") if IG.gpu(cfg) else \
        tr("Sin tarjeta gráfica, cada imagen tarda unos minutos (a %d px).") % IG.base_side(cfg)
    return (room + " " + speed).strip()


class ImageInstallBox(QFrame):
    """Estado del generador de imágenes con sus botones: instalar (con avance), cancelar, quitar o continuar.
    mid=None sigue el modelo elegido en Ajustes; on_continue (en el chat) avisa al agente de que ya está listo."""
    changed = Signal()

    def __init__(self, mid=None, on_continue=None, removable=False, intro=False):
        super().__init__()
        self.setObjectName("docCard")
        self.mid, self.on_continue, self.removable = mid, on_continue, removable
        self._was = None
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        if intro:
            v.addWidget(lbl(tr("Para crear imágenes, %s descarga una sola vez el generador y un modelo de imagen. Después "
                               "funciona sin internet y todo se queda en tu equipo.") % APP_NAME))
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:600")
        self.title.setWordWrap(True)
        v.addWidget(self.title)
        self.desc = lbl("", "faint")
        v.addWidget(self.desc)
        self.state = lbl("")
        v.addWidget(self.state)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        v.addWidget(self.bar)
        self.fit = lbl("", "faint")
        v.addWidget(self.fit)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.b_install = btn(tr("Instalar"), "primary", self.install, "acc_descargar")
        self.b_cancel = btn(tr("Cancelar"), None, self.cancel)
        self.b_remove = btn(tr("Quitar"), "danger", self.remove)
        self.b_go = btn(tr("Continuar"), "primary", self._go)
        for b in (self.b_install, self.b_cancel, self.b_remove, self.b_go):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.timer = QTimer(self, interval=400, timeout=self.refresh)
        self.refresh()
        if IG.installing():
            self.timer.start()

    def cfg(self):
        return core.SET.snapshot()

    def model(self):
        return IG.model(self.cfg(), self.mid)

    def refresh(self):
        cfg, m = self.cfg(), self.model()
        self.title.setText("%s · %s · %s" % (m["name"], m["lab"], tr("licencia %s") % m["license"]))
        self.desc.setText(m["desc"])
        st = IG.status(cfg, m["id"])
        job = IG.JOB
        busy = IG.installing()
        self.b_install.setText(tr("Instalar (%s)") % P.fmt_bytes(st["need"]) if not st["ready"] else tr("Instalar"))
        self.b_install.setVisible(not busy and not st["ready"] and IG.available())
        self.b_cancel.setVisible(busy)
        self.b_remove.setVisible(self.removable and not busy and any(os.path.isfile(IG.file_path(cfg, m, f)) for f in m["files"]))
        self.b_go.setVisible(bool(self.on_continue) and st["ready"] and not busy)
        self.bar.setVisible(busy)
        if not IG.available():
            txt = tr("No hay una versión del generador de imágenes para %s todavía.") % osys.os_label()
        elif busy:
            o = job.overall()
            self.bar.setValue(int(1000 * o["got"] / o["total"]) if o["total"] else 0)
            cur = next((s for s in job.steps if s["status"] == "running"), None)
            txt = tr("Instalando: %s") % P.describe_overall(o)
            if cur:
                txt += "\n%s · %s" % (cur["label"], P.describe_step(cur))
        elif st["ready"]:
            txt = tr("✓ Instalado. El agente ya puede crear imágenes.") if self.on_continue else \
                tr("✓ Instalado (%s en %s).") % (P.fmt_bytes(IG.total_size(m)), IG.model_root(cfg))
        elif job is not None and job.finished and job.error:
            txt = tr("No se pudo instalar: %s") % job.error
        else:
            txt = tr("No instalado. Se descargarán %s una sola vez.") % P.fmt_bytes(st["need"])
        self.state.setText(txt)
        failed = job is not None and job.finished and job.error and not st["ready"] and not busy
        self.state.setStyleSheet("color:%s" % C["bad"] if failed else "")
        self.fit.setText(fit_text(cfg, m) if IG.available() else "")
        now = (busy, st["ready"])
        if now != self._was:
            if self._was is not None:
                self.changed.emit()
            self._was = now
        if not busy and self.timer.isActive():
            self.timer.stop()

    def install(self):
        IG.install(self.cfg(), self.model()["id"])
        self.timer.start()
        self.refresh()

    def cancel(self):
        if IG.JOB is not None:
            IG.JOB.cancel()
        self.refresh()

    def remove(self):
        m = self.model()
        r = QMessageBox.question(self, tr("Quitar el modelo de imagen"),
                                 tr("¿Quitar «%s» de este equipo? Se liberará el espacio de sus archivos; podrás instalarlo de nuevo cuando quieras.") % m["name"],
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        freed = IG.remove(self.cfg(), m["id"])
        self.refresh()
        self.state.setText(tr("Quitado: se liberaron %s.") % P.fmt_bytes(freed))
        self.changed.emit()

    def _go(self):
        self.b_go.hide()
        if self.on_continue:
            self.on_continue()
