# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Navegador integrado: un panel de Jayth (Qt WebEngine) que pueden usar el usuario y el agente.

- El agente lo maneja con herramientas (browser_open, browser_read, browser_click, browser_type, browser_nav,
  browser_screenshot). Llegan desde su hilo y BrowserBridge las pasa al de la interfaz y espera la respuesta.
- La página se lee como texto más una lista numerada de lo que se puede usar (enlaces, botones, campos, casillas,
  listas). El agente pulsa y escribe por número: el clic es real (eventos de ratón en la página), no simulado con JS.
- Mientras el agente actúa, la página brilla en los bordes, su puntero «Jayth» se desliza hasta el elemento, lo
  resalta y deja una onda al pulsar; arriba se ve «Jayth lo está usando». El usuario puede intervenir cuando quiera.
- Sesiones y cookies en un perfil propio de Jayth (los inicios de sesión se conservan). Las contraseñas no las
  escribe el agente: las escribe el usuario.
"""
import os, re, json, math, time, threading, urllib.parse
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QUrl, QPointF, QRectF, QEvent, QStandardPaths, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient, QPainterPath, QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QApplication, QFrame
from . import paths, osys
from .theme import C, icon
from .canvas import web_view_class, _tb

START = """<!doctype html><html><head><meta charset="utf-8"><title>Navegador de Jayth</title></head>
<body style="margin:0;height:100vh;display:grid;place-items:center;background:%(bg)s;color:%(mut)s;font:15px 'Segoe UI',system-ui,sans-serif">
<div style="text-align:center;max-width:420px;line-height:1.5"><div style="font-size:22px;color:%(tx)s;font-weight:600;margin-bottom:8px">
Navegador de Jayth</div>Escribe una dirección arriba o pide al agente que abra una página: la verás aquí mientras la usa,
y puedes intervenir cuando quieras.</div></body></html>"""

# ---------------------------------------------------------------- lo que se ejecuta dentro de la página
_COLLECT = r"""
(function () {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=link], [role=tab], ' +
              '[role=checkbox], [role=switch], [role=radio], [role=menuitem], [role=option], [role=combobox], [onclick], [contenteditable=""], [contenteditable=true]';
  const vis = el => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false;
                      const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const txt = s => (s || '').replace(/\s+/g, ' ').trim();
  document.querySelectorAll('[data-jayth]').forEach(e => e.removeAttribute('data-jayth'));
  const out = []; let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (out.length >= 250) break;
    if (!vis(el)) continue;
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    const field = tag === 'input' || tag === 'textarea' || tag === 'select';
    let label = el.getAttribute('aria-label') || '';
    if (!label && field) label = (el.labels && el.labels[0] ? el.labels[0].innerText : '') || el.placeholder || el.title || el.name || '';
    if (!label && tag === 'input' && (type === 'submit' || type === 'button')) label = el.value;
    if (!label) label = el.innerText || el.title || el.getAttribute('alt') || (el.querySelector('img[alt]') || {}).alt || '';
    const r = el.getBoundingClientRect();
    i++; el.setAttribute('data-jayth', String(i));
    let value = '';
    if (tag === 'select') value = (el.options[el.selectedIndex] || {}).text || '';
    else if (field && type !== 'password' && type !== 'checkbox' && type !== 'radio') value = el.value || '';
    out.push({i: i, tag: tag, type: type, role: el.getAttribute('role') || '', label: txt(label).slice(0, 90), value: txt(value).slice(0, 80),
              href: tag === 'a' ? el.getAttribute('href') || '' : '', checked: !!el.checked || el.getAttribute('aria-checked') === 'true',
              disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true', editable: el.isContentEditable && !field,
              options: tag === 'select' ? Array.from(el.options).slice(0, 12).map(o => txt(o.text)).join(' | ') : '',
              view: r.bottom > 0 && r.top < innerHeight ? 0 : (r.top >= innerHeight ? 1 : -1)});
  }
  const text = (document.body ? document.body.innerText : '').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n\n').trim();
  const seen = []; let total = 0, nodes = 0;                 // el texto que se ve ahora mismo en pantalla
  if (document.body) {
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode()) && total < 2500 && nodes < 4000) {
      nodes++;
      const t = txt(n.textContent), p = n.parentElement;
      if (!t || !p || p.closest('script,style,noscript')) continue;
      const r = p.getBoundingClientRect();
      if (r.width === 0 || r.bottom <= 0 || r.top >= innerHeight) continue;
      seen.push(t); total += t.length + 1;
    }
  }
  return JSON.stringify({title: document.title, url: location.href, text: text.slice(0, 200000), elements: out, seen: seen.join('\n'),
                         scroll: Math.round(scrollY), height: document.documentElement.scrollHeight, view: innerHeight});
})()
"""
_LOCATE = r"""
(function (i) {
  const el = document.querySelector('[data-jayth="' + i + '"]');
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = el.getBoundingClientRect();
  return JSON.stringify({x: r.left, y: r.top, w: r.width, h: r.height, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(),
                         disabled: !!el.disabled});
})(%d)
"""
_TYPE = r"""
(function (i, text, clear) {
  const el = document.querySelector('[data-jayth="' + i + '"]');
  if (!el) return JSON.stringify({err: 'gone'});
  const tag = el.tagName.toLowerCase();
  if (tag === 'select') {
    const want = text.trim().toLowerCase();
    let k = Array.from(el.options).findIndex(o => o.text.trim().toLowerCase() === want || o.value.toLowerCase() === want);
    if (k < 0) k = Array.from(el.options).findIndex(o => o.text.toLowerCase().includes(want));
    if (k < 0) return JSON.stringify({err: 'option', options: Array.from(el.options).map(o => o.text.trim()).slice(0, 30)});
    el.selectedIndex = k;
    el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true}));
    return JSON.stringify({value: el.options[k].text});
  }
  el.focus();
  if (clear) { if (typeof el.select === 'function') el.select(); else document.execCommand('selectAll', false, null); }
  let ok = text ? document.execCommand('insertText', false, text) : (clear ? document.execCommand('delete', false, null) : true);
  const val = () => (el.value !== undefined ? el.value : el.innerText) || '';
  if (!ok || (text && !val().includes(text))) {          // si el campo no acepta la escritura «real», se pone el valor directamente
    const proto = tag === 'textarea' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value');
    if (setter && el.value !== undefined) setter.set.call(el, (clear ? '' : el.value) + text); else el.innerText = text;
    el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return JSON.stringify({value: val().slice(0, 200)});
})(%d, %s, %s)
"""


def to_url(s):
    """Lo que se escribe en la barra: dirección, ruta de archivo o búsqueda."""
    s = (s or "").strip()
    if not s:
        return QUrl()
    if re.match(r"^[a-z][a-z0-9+.-]*:", s, re.I) and not re.match(r"^[a-z]:[\\/]", s, re.I):
        return QUrl(s)
    if os.path.exists(s):
        return QUrl.fromLocalFile(os.path.abspath(s))
    if " " not in s and re.match(r"^(localhost|127\.|\d+\.\d+\.\d+\.\d+)", s):
        return QUrl("http://" + s)
    if " " not in s and "." in s:
        return QUrl("https://" + s)
    return QUrl("https://duckduckgo.com/?q=" + urllib.parse.quote(s))


def _role(e):
    tag, typ, role = e["tag"], e["type"], e["role"]
    if tag == "a" or role == "link":
        return "enlace"
    if tag == "select" or (role == "combobox" and tag not in ("input", "textarea")):     # un buscador con sugerencias es un campo
        return "lista"
    if tag == "textarea":
        return "campo de texto"
    if tag == "input":
        return {"checkbox": "casilla", "radio": "opción", "submit": "botón", "button": "botón", "reset": "botón", "image": "botón",
                "search": "campo de búsqueda", "password": "contraseña", "email": "campo de correo", "file": "selector de archivo",
                "range": "deslizador", "number": "campo numérico", "date": "fecha", "tel": "campo de teléfono", "url": "campo de dirección"}.get(typ, "campo de texto")
    if role in ("checkbox", "switch"):
        return "casilla"
    if role == "radio":
        return "opción"
    if role == "tab":
        return "pestaña"
    if role in ("menuitem", "option"):
        return "opción de menú"
    if e.get("editable"):
        return "zona editable"
    return "botón"


def _line(e):
    s = "[%d] %s" % (e["i"], _role(e))
    if e["label"]:
        s += " «%s»" % e["label"]
    if e["value"] and e["value"] != e["label"]:
        s += " = «%s»" % e["value"]
    if e.get("options"):
        s += " (opciones: %s)" % e["options"][:160]
    if e["checked"]:
        s += " (marcada)"
    if e["disabled"]:
        s += " (desactivado)"
    if e["href"] and not e["href"].startswith(("javascript:", "#")):
        h = e["href"]
        s += " → " + (h if len(h) <= 60 else h[:57] + "…")
    return s


def _acc(a, key="acc"):
    c = QColor(C[key])
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


# ---------------------------------------------------------------- el agente, a la vista
class _AgentLayer(QWidget):
    """Encima de la página: brillo en los bordes mientras el agente la usa, el elemento que va a tocar resaltado, su
    puntero «Jayth» que se desliza hasta él y una onda al pulsar."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.until, self.fade, self.t0 = 0.0, 0.0, time.time()
        self.cur, self.anim, self.target, self.ripples = None, None, None, []
        self.timer = QTimer(self, interval=33, timeout=self._frame)
        self.hide()

    def poke(self, secs=3.2):
        self.until = max(self.until, time.time() + secs)
        if not self.timer.isActive():
            self.t0 = time.time()
            self.timer.start()
        self.show()
        self.raise_()

    def point(self, rect):
        self.poke()
        to = rect.center()
        if self.cur is None:
            self.cur = QPointF(self.width() * 0.5, self.height() - 40)
        self.anim = (QPointF(self.cur), to, time.time(), 0.38)
        self.target = QRectF(rect)

    def click(self):
        self.poke()
        self.ripples.append(time.time())

    def active(self):
        return self.timer.isActive() and time.time() < self.until

    def _frame(self):
        now = time.time()
        target = 1.0 if now < self.until else 0.0
        self.fade += (target - self.fade) * (0.2 if target > self.fade else 0.1)
        if target == 0.0 and self.fade < 0.02:
            self.fade = 0.0
            self.timer.stop()
            self.cur, self.target = None, None
            self.hide()
            return
        if self.anim:
            a, b, t0, d = self.anim
            t = min(1.0, (now - t0) / d)
            e = 1 - (1 - t) ** 3
            self.cur = QPointF(a.x() + (b.x() - a.x()) * e, a.y() + (b.y() - a.y()) * e)
            if t >= 1:
                self.anim = None
        self.ripples = [r for r in self.ripples if now - r < 0.6]
        self.update()

    def paintEvent(self, e):
        k = self.fade
        if k <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        t = time.time() - self.t0
        pulse = 0.8 + 0.2 * math.sin(t * 2.6)
        for i in range(12):                                    # resplandor de los bordes
            p.setPen(QPen(_acc(k * pulse * 0.6 * (1 - i / 12.0) ** 2), 1.0))
            p.drawRect(r.adjusted(0.5 + i, 0.5 + i, -0.5 - i, -0.5 - i))
        W, H = r.width(), r.height()                            # destello que recorre el contorno
        P = 2 * (W + H)
        s = (t * 650) % P
        x, y = (s, 0) if s < W else (W, s - W) if s < W + H else (W - (s - W - H), H) if s < 2 * W + H else (0, H - (s - 2 * W - H))
        rg = QRadialGradient(QPointF(x, y), 110)
        rg.setColorAt(0, _acc(0.75 * k, "acc_hi"))
        rg.setColorAt(1, _acc(0))
        p.setPen(QPen(QBrush(rg), 3))
        p.drawRect(r.adjusted(1.5, 1.5, -1.5, -1.5))
        if self.target is not None and self.anim is None:     # el elemento que toca
            p.setPen(QPen(_acc(0.95 * k), 2))
            p.setBrush(_acc(0.12 * k))
            p.drawRoundedRect(self.target.adjusted(-3, -3, 3, 3), 6, 6)
        if self.cur is not None:
            c = self.cur
            now = time.time()
            for rp in self.ripples:
                q = (now - rp) / 0.6
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(_acc((1 - q) * 0.9 * k), 2))
                p.drawEllipse(c, 6 + 22 * q, 6 + 22 * q)
            halo = QRadialGradient(c, 20)
            halo.setColorAt(0, _acc(0.35 * k))
            halo.setColorAt(1, _acc(0))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(c, 20, 20)
            arrow = QPainterPath()                              # puntero de flecha con borde blanco
            pts = [(0, 0), (0, 17), (4.6, 13.2), (7.8, 20.2), (10.6, 19), (7.5, 12.2), (13, 12.2)]
            arrow.moveTo(c.x() + pts[0][0], c.y() + pts[0][1])
            for px, py in pts[1:]:
                arrow.lineTo(c.x() + px, c.y() + py)
            arrow.closeSubpath()
            p.setPen(QPen(QColor(255, 255, 255, int(235 * k)), 1.4))
            p.setBrush(_acc(k))
            p.drawPath(arrow)
            f = p.font()
            f.setPointSizeF(8.5)
            f.setBold(True)
            p.setFont(f)
            fm = p.fontMetrics()
            box = QRectF(c.x() + 15, c.y() + 18, fm.horizontalAdvance("Jayth") + 16, fm.height() + 6)
            p.setBrush(_acc(0.95 * k))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(box, box.height() / 2, box.height() / 2)
            tc = QColor(C["on_acc"])
            tc.setAlphaF(k)
            p.setPen(tc)
            p.drawText(box, Qt.AlignCenter, "Jayth")
        p.end()


class _Holder(QWidget):
    """La página y, encima, la capa del agente (siempre del mismo tamaño)."""

    def __init__(self, view):
        super().__init__()
        self.view = view
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(view)
        self.layer = _AgentLayer(self)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.layer.setGeometry(self.rect())
        self.layer.raise_()


_PAGE = [None]


def _page_class():
    """Página en la que lo que se abriría «en otra pestaña o ventana» se carga en la misma, conservando el historial
    (el agente no pierde la página y «atrás» sigue funcionando)."""
    if _PAGE[0] is None:
        from PySide6.QtWebEngineCore import QWebEnginePage

        class Page(QWebEnginePage):
            def createWindow(self, kind):
                tmp = QWebEnginePage(self.profile(), self)

                def go(u, tmp=tmp):
                    if u.isValid() and not u.isEmpty() and u.scheme() != "about":
                        tmp.urlChanged.disconnect()
                        self.load(u)
                        tmp.deleteLater()
                tmp.urlChanged.connect(go)
                return tmp
        _PAGE[0] = Page
    return _PAGE[0]


def _view_class():
    return web_view_class()


# ---------------------------------------------------------------- el panel
class BrowserPanel(QWidget):
    closed = Signal()

    def __init__(self, main=None):
        super().__init__()
        self.main = main
        self.setObjectName("canvas")
        self.setMinimumWidth(340)
        self.setProperty("foldable", True)
        self.view, self.page_info, self._loading, self._last_ok = None, None, False, True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QWidget()
        head.setObjectName("canvasHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(2)
        back = _tb("ui_chevron_derecha", "Atrás", lambda: self.view and self.view.back(), 13)
        from PySide6.QtGui import QTransform
        back.setIcon(icon("ui_chevron_derecha", C["mut"], 13).pixmap(13, 13).transformed(QTransform().rotate(180)))
        h.addWidget(back)
        h.addWidget(_tb("ui_chevron_derecha", "Adelante", lambda: self.view and self.view.forward(), 13))
        h.addWidget(_tb("acc_refrescar", "Recargar", lambda: self.view and self.view.reload(), 14))
        self.addr = QLineEdit()
        self.addr.setObjectName("addressBar")
        self.addr.setPlaceholderText("Escribe una dirección o lo que quieras buscar")
        self.addr.returnPressed.connect(lambda: self.view and self.view.load(to_url(self.addr.text())))
        h.addWidget(self.addr, 1)
        self.agent_lbl = QLabel("● Jayth lo está usando")
        self.agent_lbl.setStyleSheet("color:%s; font-size:9pt; padding: 0 6px" % C["acc"])
        self.agent_lbl.hide()
        h.addWidget(self.agent_lbl)
        h.addWidget(_tb("acc_abrir_externo", "Abrir esta página en tu navegador", self.open_external))
        h.addWidget(_tb("ui_cerrar", "Cerrar el navegador", lambda: self.closed.emit(), 13))
        v.addWidget(head)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("hline")
        v.addWidget(line)
        cls = _view_class()
        if not cls:
            msg = QLabel("Este equipo no tiene el navegador integrado (Qt WebEngine).\nEl agente puede leer páginas con web_fetch.")
            msg.setObjectName("muted")
            msg.setAlignment(Qt.AlignCenter)
            v.addWidget(msg, 1)
            return
        from PySide6.QtWebEngineCore import QWebEngineProfile
        base = os.path.join(paths.DATA, "navegador")
        self.profile = QWebEngineProfile("jayth", self)               # perfil propio y persistente: cookies e inicios de sesión
        self.profile.setPersistentStoragePath(os.path.join(base, "datos"))
        self.profile.setCachePath(os.path.join(base, "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
        self.profile.downloadRequested.connect(self._download)
        self.view = cls()
        self.view.setPage(_page_class()(self.profile, self.view))
        self.view.urlChanged.connect(lambda u: self.addr.setText(u.toString() if u.scheme() not in ("data", "about") else ""))
        self.view.loadStarted.connect(self._started)
        self.view.loadFinished.connect(self._finished)
        self.holder = _Holder(self.view)
        v.addWidget(self.holder, 1)
        self.view.setHtml(START % C, QUrl("about:blank"))
        self.agent_t = QTimer(self, interval=300, timeout=self._agent_label)

    # ---- estado
    def _started(self):
        self._loading = True

    def _finished(self, ok):
        self._loading = False
        self._last_ok = ok

    def _agent_label(self):
        on = self.holder.layer.active()
        self.agent_lbl.setVisible(on)
        if not on:
            self.agent_t.stop()

    def _poke(self):
        self.holder.layer.poke()
        self.agent_lbl.show()
        self.agent_t.start()

    def open_external(self):
        if self.view is not None and self.view.url().scheme() in ("http", "https", "file"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(self.view.url())

    def _download(self, req):
        d = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        req.setDownloadDirectory(d)
        req.accept()
        if self.main is not None:
            self.main.toast("Descargando «%s» en %s" % (req.downloadFileName(), d), icon_name="acc_descargar")

    # ---- órdenes del agente (en el hilo de la interfaz; cada una termina llamando a _done o _fail)
    def do(self, job):
        if self.view is None:
            return self._fail(job, "Este equipo no tiene el navegador integrado (Qt WebEngine). Usa web_fetch para leer páginas.")
        fn = getattr(self, "_do_" + job["action"], None)
        if fn is None:
            return self._fail(job, "Acción desconocida del navegador: %s" % job["action"])
        self._poke()
        try:
            fn(job, **job["args"])
        except TypeError as e:
            self._fail(job, "Parámetros no válidos: %s" % e)
        except Exception as e:
            self._fail(job, "%s: %s" % (type(e).__name__, e))

    @staticmethod
    def _done(job, res):
        job["res"] = res
        job["ev"].set()

    @staticmethod
    def _fail(job, err):
        job["err"] = err
        job["ev"].set()

    def _js(self, code, cb):
        from PySide6.QtWebEngineCore import QWebEngineScript
        self.view.page().runJavaScript(code, QWebEngineScript.ApplicationWorld, cb)

    def _settle(self, then, first=0.6, limit=25.0):
        """Espera a que termine lo que haya provocado la acción (una página nueva que carga) y sigue."""
        t0 = time.time()

        def check():
            if self._loading and time.time() - t0 < limit:
                return QTimer.singleShot(250, check)
            QTimer.singleShot(350, then)                  # un momento para que la página pinte y ejecute sus scripts
        QTimer.singleShot(int(first * 1000), check)

    def _collect(self, cb):
        def got(r):
            try:
                self.page_info = json.loads(r) if r else None
            except (TypeError, ValueError):
                self.page_info = None
            cb(self.page_info)
        self._js(_COLLECT, got)

    def _summary(self, info, text_chars=1500, max_el=45, intro=""):
        """Texto para el modelo: título, dirección, el principio del texto y lo que se puede usar a la vista."""
        if not info:
            return intro + "No pude leer la página (puede que siga cargando: prueba browser_read en un momento)."
        els = info["elements"]
        near = [e for e in els if e["view"] == 0][:max_el]
        txt = info["text"][:text_chars]
        more = len(info["text"]) > text_chars
        lines = [intro + "Página «%s»  %s" % (info["title"] or "sin título", info["url"]), "",
                 "Texto%s:" % (" (principio)" if more else ""), txt or "(sin texto)"]
        if more:
            lines.append("… (%d caracteres en total: browser_read con what=text y offset=%d para seguir)" % (len(info["text"]), text_chars))
        lines += ["", "Para usar (a la vista; número para browser_click / browser_type):"] + [_line(e) for e in near]
        rest = len(els) - len(near)
        if rest > 0:
            lines.append("… y %d más fuera de la vista o al final (browser_read con what=elements, o browser_nav down)." % rest)
        if not els:
            lines.append("(nada que pulsar)")
        return "\n".join(lines)

    def _point(self, rect_css):
        z = self.view.zoomFactor() or 1.0
        top_left = self.view.mapTo(self.holder, self.view.rect().topLeft())
        r = QRectF(top_left.x() + rect_css["x"] * z, top_left.y() + rect_css["y"] * z, rect_css["w"] * z, rect_css["h"] * z)
        self.holder.layer.point(r)
        return r

    def _target(self):
        return self.view.focusProxy() or self.view

    def _real_click(self, r):
        """Clic de verdad en la página (eventos de ratón del sistema, como los de una persona)."""
        tgt = self._target()
        c = r.center()
        local = QPointF(tgt.mapFrom(self.holder, c.toPoint()))
        glob = QPointF(tgt.mapToGlobal(local.toPoint()))
        for typ, btn, btns in ((QEvent.MouseMove, Qt.NoButton, Qt.NoButton), (QEvent.MouseButtonPress, Qt.LeftButton, Qt.LeftButton),
                               (QEvent.MouseButtonRelease, Qt.LeftButton, Qt.NoButton)):
            QApplication.sendEvent(tgt, QMouseEvent(typ, local, glob, btn, btns, Qt.NoModifier))
        self.holder.layer.click()

    def _key(self, key, text=""):
        tgt = self._target()
        for typ in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(tgt, QKeyEvent(typ, key, Qt.NoModifier, text))

    def _locate(self, job, index, then):
        def got(r):
            if not r:
                return self._fail(job, "El elemento %s ya no está en la página (cambió o se recargó). Vuelve a leerla con browser_read." % index)
            then(json.loads(r))
        self._js(_LOCATE % int(index), got)

    def _find(self, job, text, then):
        """Número del elemento cuyo texto encaja con «text» (igual, empieza por, contiene)."""
        def got(info):
            q = " ".join(str(text).split()).lower()
            els = (info or {}).get("elements") or []
            for test in (lambda l: l == q, lambda l: l.startswith(q), lambda l: q in l):
                for e in els:
                    if test(e["label"].lower()):
                        return then(e["i"])
            self._fail(job, "No encuentro «%s» en la página. Mira la lista con browser_read (what=elements)." % text)
        self._collect(got)

    def _after(self, job, before_url, what):
        """Resultado de una acción: qué se hizo y, si cambió de página, dónde está ahora (con su resumen)."""
        def fin(info):
            if info and info["url"] != before_url:
                self._done(job, self._summary(info, 1200, 40, intro=what + "\nSe abrió otra página.\n"))
            else:
                self._done(job, what + ("\nLa página no cambió de dirección; si algo cambió dentro, léela con browser_read." if info else ""))
        self._settle(lambda: self._collect(fin))

    # ---- las acciones
    def _do_open(self, job, url=""):
        u = to_url(url)
        if not u.isValid() or u.isEmpty():
            return self._fail(job, "Dirección no válida: %s" % url)
        self._loading = True
        self.view.load(u)

        def fin(info):
            warn = "" if self._last_ok else "(La página no terminó de cargar bien.)\n"
            self._done(job, self._summary(info, intro=warn))
        self._settle(lambda: self._collect(fin), first=0.4, limit=30)

    def _do_read(self, job, what="all", filter="", offset=0):
        def fin(info):
            if not info:
                return self._fail(job, "No pude leer la página.")
            w = str(what or "all").lower()
            if w == "text":
                o = max(0, int(offset or 0))
                t = info["text"][o:o + 4000]
                tail = ("\n… (sigue: offset=%d de %d)" % (o + 4000, len(info["text"]))) if len(info["text"]) > o + 4000 else ""
                return self._done(job, "Página «%s»  %s\nTexto desde %d:\n%s%s" % (info["title"], info["url"], o, t or "(nada)", tail))
            if w == "elements":
                els = info["elements"]
                f = str(filter or "").strip().lower()
                if f:
                    by_href = "/" in f or "." in f                     # la dirección solo cuenta si se busca una dirección
                    els = [e for e in els if f in e["label"].lower() or f in e["value"].lower() or (by_href and f in e["href"].lower())]
                lines = ["Página «%s»: %d elementos%s (número para browser_click / browser_type):" % (info["title"], len(els),
                                                                                                      (" con «%s»" % filter) if f else "")]
                lines += [_line(e) + ("" if e["view"] == 0 else " (más abajo)" if e["view"] > 0 else " (más arriba)") for e in els[:150]]
                return self._done(job, "\n".join(lines))
            self._done(job, self._summary(info, 2500, 60))
        self._collect(fin)

    def _do_click(self, job, index=None, text=None):
        if index in (None, "") and not text:
            return self._fail(job, "Indica index (número de browser_read) o text (el texto del enlace o botón).")
        if index in (None, ""):
            return self._find(job, text, lambda i: self._do_click(job, i))
        before = self.view.url().toString()

        def go(loc):
            if loc.get("disabled"):
                return self._fail(job, "Ese elemento está desactivado ahora mismo.")
            if loc["tag"] == "select":
                return self._fail(job, "Es una lista desplegable: elige la opción con browser_type (text = la opción).")
            r = self._point(loc)
            info = next((e for e in (self.page_info or {}).get("elements", []) if e["i"] == int(index)), None)
            what = "Pulsé %s" % ((_role(info) + (" «%s»" % info["label"] if info["label"] else "")) if info else "el elemento %s" % index)
            QTimer.singleShot(420, lambda: (self._real_click(r), self._after(job, before, what + ".")))
        self._locate(job, index, go)

    def _do_type(self, job, index=None, text="", submit=False, clear=True, field=None):
        if index in (None, "") and field:
            return self._find(job, field, lambda i: self._do_type(job, i, text, submit, clear))
        if index in (None, ""):
            return self._fail(job, "Indica index (número del campo en browser_read) o field (su nombre).")
        before = self.view.url().toString()

        def go(loc):
            if loc["type"] == "password":
                return self._fail(job, "Por seguridad, las contraseñas no las escribe el agente: pídele al usuario que la escriba él en el navegador "
                                       "de Jayth (lo tiene a la vista) y luego continúa.")
            if loc.get("disabled"):
                return self._fail(job, "Ese campo está desactivado ahora mismo.")
            r = self._point(loc)

            def typed(res):
                d = json.loads(res) if res else {}
                if d.get("err") == "gone":
                    return self._fail(job, "El campo ya no está en la página. Vuelve a leerla con browser_read.")
                if d.get("err") == "option":
                    return self._fail(job, "Esa lista no tiene la opción «%s». Opciones: %s" % (text, " | ".join(d.get("options") or [])))
                what = "Escribí «%s»%s" % (str(text)[:80], " y pulsé Intro" if submit else "")
                if loc["tag"] == "select":
                    what = "Elegí «%s» en la lista" % d.get("value", text)
                if submit:
                    self._key(Qt.Key_Return, "\r")
                    self._after(job, before, what + ".")
                else:
                    self._done(job, what + ". Ahora vale: «%s»" % d.get("value", "")[:120])

            def write():
                self.holder.layer.click()
                self._js(_TYPE % (int(index), json.dumps(str(text)), "true" if clear not in (False, "false", 0) else "false"), typed)
            QTimer.singleShot(420, write)
        self._locate(job, index, go)

    def _do_nav(self, job, action="back"):
        a = str(action or "").lower()
        before = self.view.url().toString()
        if a in ("back", "forward", "reload"):
            if a == "back" and not self.view.history().canGoBack():
                return self._fail(job, "No hay página anterior.")
            {"back": self.view.back, "forward": self.view.forward, "reload": self.view.reload}[a]()
            self._loading = True
            return self._after(job, before if a != "reload" else "", {"back": "Volví atrás.", "forward": "Fui adelante.", "reload": "Recargué la página."}[a])
        js = {"down": "window.scrollBy(0, innerHeight * 0.8)", "up": "window.scrollBy(0, -innerHeight * 0.8)", "top": "window.scrollTo(0, 0)",
              "bottom": "window.scrollTo(0, document.documentElement.scrollHeight)"}.get(a)
        if not js:
            return self._fail(job, "action debe ser back, forward, reload, down, up, top o bottom.")

        def fin(info):
            if not info:
                return self._fail(job, "No pude leer la página.")
            pos = "%d%%" % min(100, round(100 * (info["scroll"] + info["view"]) / max(1, info["height"])))
            near = [e for e in info["elements"] if e["view"] == 0][:40]
            self._done(job, "Página «%s», vista hasta el %s.\nSe ve:\n%s\n\nPara usar (a la vista):\n%s" % (
                info["title"], pos, (info.get("seen") or "(sin texto)")[:1800], "\n".join(_line(e) for e in near) or "(nada que pulsar)"))
        self._js(js + "; true", lambda _r: QTimer.singleShot(300, lambda: self._collect(fin)))

    def _do_shot(self, job):
        pm = self.view.grab()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img = pm.toImage()
        if img.width() > 1024:
            img = img.scaledToWidth(1024, Qt.SmoothTransformation)
        img.save(buf, "PNG")
        buf.close()
        self._done(job, {"text": "Captura del navegador (%dx%d): «%s»  %s" % (img.width(), img.height(), self.view.title(), self.view.url().toString()),
                         "image": bytes(ba.data())})


# ---------------------------------------------------------------- puente entre el hilo del agente y la interfaz
class BrowserBridge(QObject):
    sig = Signal(object)

    def __init__(self, get_panel):
        super().__init__()
        self.get_panel = get_panel                    # función (en el hilo de la interfaz) que muestra el panel y lo devuelve
        self.sig.connect(self._run, Qt.QueuedConnection)

    def call(self, action, args=None, stop=None, timeout=45):
        """Desde cualquier hilo: pide una acción al navegador y espera el resultado."""
        job = {"action": action, "args": dict(args or {}), "ev": threading.Event(), "res": None, "err": None}
        self.sig.emit(job)
        end = time.time() + timeout
        while not job["ev"].wait(0.2):
            if stop is not None and stop.is_set():
                raise RuntimeError("Detenido.")
            if time.time() > end:
                raise RuntimeError("El navegador no respondió a tiempo (la página puede seguir cargando: prueba browser_read).")
        if job["err"]:
            raise RuntimeError(job["err"])
        return job["res"]

    def _run(self, job):
        try:
            panel = self.get_panel()
        except Exception as e:
            job["err"] = "No pude abrir el navegador integrado: %s" % e
            job["ev"].set()
            return
        panel.do(job)
