# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Fichas para conectar servicios externos con la cuenta del usuario (Ajustes › Herramientas y tarjetas en el chat)."""
import webbrowser
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QDialog, QLineEdit, QGridLayout, QWidget,
                               QDialogButtonBox, QMessageBox)
from . import APP_NAME, conectores as CN, harness
from .i18n import tr
from .theme import C
from .wizard import btn, lbl


class ServiceTile(QFrame):
    """Un servicio: su inicial con el color de la marca, nombre, qué hace, estado y el botón que toque
    (Conectar, Cancelar, Desconectar o Configurar Google…). on_continue (en el chat) avisa al agente al terminar."""
    changed = Signal()

    def __init__(self, cid, on_continue=None, reason=""):
        super().__init__()
        self.setObjectName("docCard")
        self.cid, self.on_continue = cid, on_continue
        c = CN.find(cid)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(10)
        badge = QLabel(c["name"][:1])
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(30, 30)
        dark = c["color"].upper() in ("#D7F25C", "#EDEDED", "#FFD21E")
        badge.setStyleSheet("background:%s; color:%s; border-radius:8px; font-weight:700; font-size:11pt" % (c["color"], "#111" if dark else "#fff"))
        head.addWidget(badge, 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        name = QLabel(c["name"])
        name.setStyleSheet("font-weight:600")
        texts.addWidget(name)
        texts.addWidget(lbl(c["desc"], "faint"))
        head.addLayout(texts, 1)
        v.addLayout(head)
        if reason:
            v.addWidget(lbl(tr("Para qué: %s") % reason))
        self.state = lbl("")
        v.addWidget(self.state)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.b_setup = btn(tr("Configurar Google…"), "primary", self.setup_google)
        self.b_connect = btn(tr("Conectar"), "primary", self.start, "hub_conectar")
        self.b_cancel = btn(tr("Cancelar"), None, lambda: CN.cancel(self.cid))
        self.b_go = btn(tr("Continuar"), "primary", self._go)
        self.b_off = btn(tr("Desconectar"), None, self.stop_service)
        for b in (self.b_setup, self.b_connect, self.b_cancel, self.b_go, self.b_off):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.timer = QTimer(self, interval=400, timeout=self.refresh)
        self._was = None
        self.refresh()

    def refresh(self):
        c = CN.find(self.cid)
        job = CN.JOBS.get(self.cid)
        busy = CN.busy(self.cid)
        on = CN.connected(self.cid)
        setup = CN.needs_setup(self.cid)
        srv = harness.MCP.get(c["name"])
        if busy:
            txt = tr("Inicia sesión en la ventana del navegador que se abrió y autoriza a %s…") % APP_NAME if job["state"] == "navegador" \
                else tr("Conectando…")
        elif on and srv:
            txt = tr("✓ Conectado · %d herramientas para el agente") % len(srv.tools)
        elif on:
            txt = tr("✓ Sesión iniciada")
        elif job and job["state"] == "error":
            txt = tr("No se pudo conectar: %s") % job["error"][:220]
        elif setup:
            txt = tr("Google pide que crees una vez tu propio acceso (un «cliente OAuth») en Google Cloud. Te guío paso a paso.") \
                if self.on_continue else tr("Antes, crea tu acceso de Google (te guío paso a paso).")
        elif not self.on_continue:                       # en Ajustes, corto: lo demás ya lo explica la sección
            txt = tr("Sin conectar.")
        else:
            txt = tr("Sin conectar. Se abre la página de %s para que inicies sesión; %s no ve tu contraseña.") % (c["name"], APP_NAME) \
                if c.get("login", True) else tr("Sin conectar. No necesita cuenta.")
        self.state.setText(txt)
        failed = bool(job and job["state"] == "error" and not busy)
        self.state.setStyleSheet("color:%s" % C["bad"] if failed else ("color:%s" % C["ok"] if on else
                                                                         "color:%s" % C["mut"] if not busy else ""))
        self.b_setup.setVisible(bool(setup) and not busy and not on)
        self.b_connect.setVisible(not setup and not busy and not on)
        self.b_cancel.setVisible(busy)
        self.b_go.setVisible(bool(self.on_continue) and on and not busy)
        self.b_off.setVisible(on and not busy and not self.on_continue)
        if busy and not self.timer.isActive():
            self.timer.start()
        if not busy and self.timer.isActive():
            self.timer.stop()
        now = (busy, on)
        if now != self._was:
            if self._was is not None:
                self.changed.emit()
            self._was = now

    def start(self):
        CN.connect(self.cid)
        self.timer.start()
        self.refresh()

    def stop_service(self):
        c = CN.find(self.cid)
        r = QMessageBox.question(self, tr("Desconectar"), tr("¿Desconectar %s? %s olvidará el permiso en este equipo; puedes "
                                                              "volver a conectarlo cuando quieras.") % (c["name"], APP_NAME),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            CN.disconnect(self.cid)
            self.refresh()
            self.changed.emit()

    def setup_google(self):
        if GoogleClientDialog(self).exec():
            self.refresh()

    def _go(self):
        self.b_go.hide()
        if self.on_continue:
            self.on_continue(CN.find(self.cid)["name"])


class GoogleClientDialog(QDialog):
    """Guía para crear el «cliente OAuth» de Google que piden Gmail, Drive y Calendar (una vez para los tres)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Conectar con Google"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setSpacing(10)
        t = QLabel(tr("Conectar Gmail, Drive y Calendar"))
        t.setObjectName("h1")
        v.addWidget(t)
        v.addWidget(lbl(tr("Google no deja que las apps de escritorio se registren solas: crea una vez tu propio acceso. Son unos "
                           "minutos y sirve para los tres servicios.")))
        steps = [tr("Abre la consola de Google Cloud y crea un proyecto (o usa uno tuyo)."),
                 tr("Activa las API de MCP de Gmail, Drive y Calendar (en la guía de Google están los enlaces)."),
                 tr("En «Pantalla de consentimiento de OAuth», elige «Externo» y añade tu correo como usuario de prueba."),
                 tr("En «Credenciales», crea un «ID de cliente de OAuth» de tipo «App de escritorio»."),
                 tr("Copia aquí el ID de cliente y el secreto de cliente.")]
        v.addWidget(lbl("<br>".join("%d. %s" % (i + 1, s) for i, s in enumerate(steps))))
        r = QHBoxLayout()
        r.addWidget(btn(tr("Abrir la guía de Google"), None, lambda: webbrowser.open(CN.GOOGLE_GUIDE), "acc_abrir_externo"))
        r.addWidget(btn(tr("Abrir Google Cloud"), None, lambda: webbrowser.open("https://console.cloud.google.com/apis/credentials"),
                        "acc_abrir_externo"))
        r.addStretch(1)
        v.addLayout(r)
        g = QGridLayout()
        g.addWidget(QLabel(tr("ID de cliente")), 0, 0)
        self.cid = QLineEdit()
        self.cid.setPlaceholderText("123456789-abc….apps.googleusercontent.com")
        g.addWidget(self.cid, 0, 1)
        g.addWidget(QLabel(tr("Secreto de cliente")), 1, 0)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        g.addWidget(self.secret, 1, 1)
        v.addLayout(g)
        old = CN.google_client() or {}
        self.cid.setText(old.get("client_id", ""))
        self.secret.setText(old.get("client_secret", ""))
        v.addWidget(lbl(tr("Se guardan cifrados en este equipo. %s solo los usa para abrir la página de inicio de sesión de Google.") % APP_NAME, "faint"))
        self.err = lbl("", "faint")
        v.addWidget(self.err)
        bb = QDialogButtonBox()
        bb.addButton(btn(tr("Guardar"), "primary"), QDialogButtonBox.AcceptRole)
        bb.addButton(btn(tr("Cancelar")), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _save(self):
        cid, sec = self.cid.text().strip(), self.secret.text().strip()
        if not cid.endswith(".apps.googleusercontent.com") or not sec:
            self.err.setStyleSheet("color:%s" % C["bad"])
            return self.err.setText(tr("Revisa los dos datos: el ID termina en «.apps.googleusercontent.com» y el secreto no puede estar vacío."))
        CN.set_google_client(cid, sec)
        self.accept()


def services_grid(parent_refresh=None):
    """Fichas de todos los servicios en dos columnas (para Ajustes)."""
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(10)
    tiles = []
    for i, c in enumerate(CN.CATALOG):
        t = ServiceTile(c["id"])
        if parent_refresh:
            t.changed.connect(parent_refresh)
        g.addWidget(t, i // 2, i % 2)
        tiles.append(t)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(1, 1)
    w.tiles = tiles
    return w
