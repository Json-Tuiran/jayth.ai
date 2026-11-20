# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Ventana de tareas programadas: lista con su próxima ejecución y formulario para crearlas o cambiarlas."""
import datetime
from PySide6.QtCore import Qt, QTime, QDate
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem, QWidget,
                               QComboBox, QTimeEdit, QDateEdit, QCheckBox, QSpinBox, QMessageBox)
from . import APP_NAME, core, schedule as SC
from .wizard import btn, lbl

MODES = [("auto", "Automático: actúa sin preguntar (lo delicado siempre pide permiso)"),
         ("readonly", "Solo lectura: puede mirar y buscar, pero no cambia nada"),
         ("ask", "Preguntar: espera tu permiso antes de cada acción")]


class TasksDialog(QDialog):
    def __init__(self, main=None):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Tareas programadas")
        self.resize(900, 620)
        self.cur = None
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        left = QWidget()
        left.setObjectName("sidebar")
        left.setFixedWidth(290)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 14, 10, 10)
        t = QLabel("Tus tareas")
        t.setObjectName("h1")
        lv.addWidget(t)
        self.lst = QListWidget()
        self.lst.setObjectName("history")
        self.lst.setWordWrap(True)
        self.lst.currentRowChanged.connect(self._pick)
        lv.addWidget(self.lst, 1)
        lv.addWidget(btn("Nueva tarea", None, self._new, "acc_anadir"))
        root.addWidget(left)
        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(22, 16, 22, 14)
        v.setSpacing(7)
        v.addWidget(lbl("%s hace el encargo solo a su hora y te avisa al terminar. Las tareas se ejecutan mientras %s esté abierto "
                        "(también minimizado en la bandeja); si a esa hora estaba cerrado, se hacen al abrirlo." % (APP_NAME, APP_NAME), "faint"))
        v.addWidget(QLabel("Nombre"))
        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("Ej.: Resumen de noticias")
        v.addWidget(self.e_name)
        v.addWidget(QLabel("Qué debe hacer"))
        self.e_prompt = QPlainTextEdit()
        self.e_prompt.setPlaceholderText("Ej.: Busca las noticias de hoy sobre inteligencia artificial y hazme un resumen de 5 puntos con sus enlaces.")
        v.addWidget(self.e_prompt, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Cuándo"))
        self.kind = QComboBox()
        for k, l in SC.KINDS:
            self.kind.addItem(l, k)
        self.kind.currentIndexChanged.connect(self._sync_kind)
        row.addWidget(self.kind, 1)
        self.l_at = QLabel("a las")
        row.addWidget(self.l_at)
        self.time = QTimeEdit(QTime(9, 0))
        self.time.setDisplayFormat("HH:mm")
        row.addWidget(self.time)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setCalendarPopup(True)
        row.addWidget(self.date)
        self.every = QSpinBox()
        self.every.setRange(5, 10080)
        self.every.setValue(60)
        self.every.setSuffix(" minutos")
        row.addWidget(self.every)
        v.addLayout(row)
        self.days_w = QWidget()
        dl = QHBoxLayout(self.days_w)
        dl.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for i, d in enumerate(SC.DAYS):
            cb = QCheckBox(d[:3])
            cb.setToolTip(d)
            dl.addWidget(cb)
            self.days.append(cb)
        dl.addStretch(1)
        v.addWidget(self.days_w)
        v.addWidget(QLabel("Cómo actúa"))
        self.mode = QComboBox()
        for k, l in MODES:
            self.mode.addItem(l, k)
        v.addWidget(self.mode)
        self.on = QCheckBox("Tarea activa")
        self.on.setChecked(True)
        v.addWidget(self.on)
        self.info = lbl("", "faint")
        v.addWidget(self.info)
        self.msg = lbl("", "faint")
        v.addWidget(self.msg)
        foot = QHBoxLayout()
        self.b_del = btn("Quitar", "danger", self._delete)
        foot.addWidget(self.b_del)
        self.b_run = btn("Ejecutar ahora", None, self._run_now, "hub_lanzar")
        foot.addWidget(self.b_run)
        self.b_open = btn("Ver último resultado", None, self._open_last)
        foot.addWidget(self.b_open)
        foot.addStretch(1)
        foot.addWidget(btn("Guardar", "primary", self._save))
        foot.addWidget(btn("Cerrar", None, self.accept))
        v.addLayout(foot)
        root.addWidget(right, 1)
        self._reload()
        if self.lst.count():
            self.lst.setCurrentRow(0)
        else:
            self._new()

    def _reload(self, select=None):
        self.lst.blockSignals(True)
        self.lst.clear()
        for t in SC.all_tasks():
            state = ("Próxima: " + SC.when_text(t.get("next"))) if t.get("enabled", True) and t.get("next") else \
                ("Hecha" if t.get("kind") == "once" and t.get("last_run") else "En pausa")
            it = QListWidgetItem("%s\n%s · %s" % (t["name"], SC.describe(t), state))
            it.setData(Qt.UserRole, t["id"])
            self.lst.addItem(it)
            if t["id"] == select:
                self.lst.setCurrentItem(it)
        self.lst.blockSignals(False)

    def _task(self):
        return next((t for t in SC.all_tasks() if t["id"] == self.cur), None)

    def _pick(self, row):
        self.cur = self.lst.item(row).data(Qt.UserRole) if row >= 0 else None
        t = self._task()
        if not t:
            return
        self.e_name.setText(t["name"])
        self.e_prompt.setPlainText(t["prompt"])
        self.kind.setCurrentIndex(max(0, self.kind.findData(t.get("kind", "daily"))))
        h, m = SC._hm(t)
        self.time.setTime(QTime(h, m))
        try:
            d = datetime.date.fromisoformat(t.get("date") or "")
            self.date.setDate(QDate(d.year, d.month, d.day))
        except ValueError:
            self.date.setDate(QDate.currentDate())
        self.every.setValue(int(t.get("every_min") or 60))
        for i, cb in enumerate(self.days):
            cb.setChecked(i in (t.get("days") or []))
        self.mode.setCurrentIndex(max(0, self.mode.findData(t.get("mode") or "auto")))
        self.on.setChecked(t.get("enabled", True))
        last = ("Última vez: %s. " % SC.when_text(t["last_run"])) if t.get("last_run") else "Aún no se ha ejecutado. "
        self.info.setText(last + ("Próxima: %s." % SC.when_text(t["next"]) if t.get("enabled", True) and t.get("next") else ""))
        for b in (self.b_del, self.b_run):
            b.show()
        self.b_open.setVisible(bool(t.get("last_session")) and t["last_session"] in core.SESSIONS)
        self.msg.setText("")
        self._sync_kind()

    def _new(self):
        self.cur = None
        self.lst.blockSignals(True)
        self.lst.setCurrentRow(-1)
        self.lst.blockSignals(False)
        self.e_name.clear()
        self.e_prompt.clear()
        self.kind.setCurrentIndex(self.kind.findData("daily"))
        self.time.setTime(QTime(9, 0))
        self.date.setDate(QDate.currentDate())
        for cb in self.days:
            cb.setChecked(False)
        self.on.setChecked(True)
        self.info.setText("")
        for b in (self.b_del, self.b_run, self.b_open):
            b.hide()
        self._sync_kind()
        self.e_name.setFocus()

    def _sync_kind(self, *_):
        k = self.kind.currentData()
        self.date.setVisible(k == "once")
        self.every.setVisible(k == "interval")
        self.time.setVisible(k != "interval")
        self.l_at.setVisible(k != "interval")
        self.days_w.setVisible(k == "weekly")

    def _values(self):
        k = self.kind.currentData()
        d = self.date.date()
        return dict(name=self.e_name.text().strip(), prompt=self.e_prompt.toPlainText().strip(), kind=k,
                    time=self.time.time().toString("HH:mm"), date="%04d-%02d-%02d" % (d.year(), d.month(), d.day()),
                    days=[i for i, cb in enumerate(self.days) if cb.isChecked()], every_min=self.every.value(),
                    mode=self.mode.currentData(), enabled=self.on.isChecked())

    def _save(self):
        val = self._values()
        if not val["name"] or not val["prompt"]:
            return self.msg.setText("La tarea necesita un nombre y saber qué debe hacer.")
        if val["kind"] == "weekly" and not val["days"]:
            return self.msg.setText("Marca al menos un día de la semana.")
        if self.cur and self._task():
            SC.update(self.cur, **val)
        else:
            t = SC.new_task(val["name"], val["prompt"], val["kind"], val["time"], val["date"], val["days"], val["every_min"], val["mode"])
            t["enabled"] = val["enabled"]
            if val["kind"] == "once" and not t["next"]:
                return self.msg.setText("Esa fecha y hora ya han pasado.")
            SC.add(t)
            self.cur = t["id"]
        self._reload(self.cur)
        self._pick(self.lst.currentRow())
        self.msg.setText("✓ Tarea guardada.")

    def _delete(self):
        t = self._task()
        if t and QMessageBox.question(self, "Quitar tarea", "¿Quitar la tarea «%s»?" % t["name"]) == QMessageBox.StandardButton.Yes:
            SC.remove(t["id"])
            self._reload()
            if self.lst.count():
                self.lst.setCurrentRow(0)
            else:
                self._new()

    def _run_now(self):
        t = self._task()
        if not t or self.main is None:
            return
        err = self.main.run_task(t, manual=True)
        self.msg.setText(("✗ %s" % err) if err else "✓ En marcha. Te aviso cuando termine; el resultado queda en el historial.")
        self._reload(self.cur)

    def _open_last(self):
        t = self._task()
        if t and self.main is not None and t.get("last_session") in core.SESSIONS:
            self.accept()
            self.main.open_task_result(t["last_session"])
