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
from .i18n import tr

START = """<!doctype html><html><head><meta charset="utf-8"><title>%(title)s</title></head>
<body style="margin:0;height:100vh;display:grid;place-items:center;background:%(bg)s;color:%(mut)s;font:15px 'Segoe UI',system-ui,sans-serif">
<div style="text-align:center;max-width:420px;line-height:1.5"><div style="font-size:22px;color:%(tx)s;font-weight:600;margin-bottom:8px">
%(title)s</div>%(hint)s</div></body></html>"""

# ---------------------------------------------------------------- lo que se ejecuta dentro de la página
_COLLECT = r"""
(function () {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=link], [role=tab], ' +
              '[role=checkbox], [role=switch], [role=radio], [role=menuitem], [role=option], [role=combobox], [onclick], [contenteditable=""], [contenteditable=true], ' +
              '[tabindex]:not([tabindex="-1"])';
  const vis = el => { const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return false;
                      const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const txt = s => (s || '').replace(/\s+/g, ' ').trim();
  document.querySelectorAll('[data-jayth]').forEach(e => e.removeAttribute('data-jayth'));
  const out = []; let i = 0;
  const base = sel.slice(0, sel.lastIndexOf(', [tabindex]'));
  for (const el of document.querySelectorAll(sel)) {
    if (out.length >= 250) break;
    // un contenedor que solo es «navegable con el teclado» (un diálogo, una zona con desplazamiento) no es un control
    if (!el.matches(base) && (el.querySelector(base + ', li, [tabindex]') || (el.innerText || '').length > 200)) continue;
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    let box = el;
    if (!vis(el)) {                     // casilla nativa escondida bajo un interruptor dibujado: se pulsa su etiqueta
      const lab = (tag === 'input' && (type === 'checkbox' || type === 'radio')) ? (el.closest('label') || (el.labels && el.labels[0])) : null;
      if (!lab || !vis(lab)) continue;
      box = lab;
    }
    const field = tag === 'input' || tag === 'textarea' || tag === 'select';
    let label = el.getAttribute('aria-label') || '';
    if (!label && field) label = (el.labels && el.labels[0] ? el.labels[0].innerText : '') || el.placeholder || el.title || el.name || '';
    if (!label && tag === 'input' && (type === 'submit' || type === 'button')) label = el.value;
    if (!label) label = el.innerText || el.title || el.getAttribute('alt') || (el.querySelector('img[alt]') || {}).alt || '';
    const r = box.getBoundingClientRect();
    i++; el.setAttribute('data-jayth', String(i));
    if (box !== el) box.setAttribute('data-jayth-box', String(i));
    let value = '';
    if (tag === 'select') value = (el.options[el.selectedIndex] || {}).text || '';
    else if (field && type !== 'password' && type !== 'checkbox' && type !== 'radio') value = el.value || '';
    out.push({i: i, tag: tag, type: type, role: el.getAttribute('role') || '', label: txt(label).slice(0, 90), value: txt(value).slice(0, 80),
              href: tag === 'a' ? el.getAttribute('href') || '' : '', checked: !!el.checked || el.getAttribute('aria-checked') === 'true',
              disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true', editable: el.isContentEditable && !field,
              options: tag === 'select' ? Array.from(el.options).slice(0, 12).map(o => txt(o.text)).join(' | ') : '',
              range: type === 'range' ? [el.min || '0', el.max || '100', el.step || '1'] : null,
              view: r.bottom > 0 && r.top < innerHeight ? 0 : (r.top >= innerHeight ? 1 : -1)});
  }
  // lo que se puede pulsar aunque el HTML no lo diga (opciones de un menú hechas con <li> o <div> y un clic de
  // JavaScript): el cursor de mano. Solo el elemento de más arriba con ese cursor (los hijos lo heredan).
  let looked = 0;
  for (const el of document.querySelectorAll('li, div, span, td, th, img, svg, label, p, i, h1, h2, h3, h4, dt, dd')) {
    if (out.length >= 250 || looked > 4000) break;
    looked++;
    if (el.closest('[data-jayth]') || el.querySelector('[data-jayth]')) continue;
    const st = getComputedStyle(el);
    if (st.cursor !== 'pointer') continue;
    const par = el.parentElement;
    if (par && getComputedStyle(par).cursor === 'pointer') continue;
    if (!vis(el)) continue;
    const label = el.getAttribute('aria-label') || el.innerText || el.title || el.getAttribute('alt') || '';
    if (!txt(label)) continue;
    const r = el.getBoundingClientRect();
    i++; el.setAttribute('data-jayth', String(i));
    out.push({i: i, tag: el.tagName.toLowerCase(), type: '', role: el.getAttribute('role') || '', label: txt(label).slice(0, 90), value: '',
              href: '', checked: el.classList.contains('active') || el.classList.contains('selected') || el.getAttribute('aria-selected') === 'true',
              disabled: el.getAttribute('aria-disabled') === 'true', editable: false, options: '', range: null, generic: true,
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
  const alerts = Array.from(document.querySelectorAll('[role=alert], [role=status], [aria-live=assertive], [aria-live=polite], dialog[open]'))
                      .filter(vis).map(e => txt(e.innerText).slice(0, 300)).filter(Boolean).slice(0, 5);
  return JSON.stringify({title: document.title, url: location.href, text: text.slice(0, 200000), elements: out, seen: seen.join('\n'), alerts: alerts,
                         scroll: Math.round(scrollY), height: document.documentElement.scrollHeight, view: innerHeight});
})()
"""
_LOCATE = r"""
(function (i) {
  const el = document.querySelector('[data-jayth="' + i + '"]');
  if (!el) return null;
  const box = document.querySelector('[data-jayth-box="' + i + '"]') || el;
  box.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = box.getBoundingClientRect();
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


def page_changes(old, new):
    """Qué cambió a la vista tras una acción que no llevó a otra dirección (lo normal en una aplicación web): avisos de la
    página, texto que aparece o desaparece y elementos nuevos. Sin esto el agente tenía que volver a leer la página entera
    después de cada clic para saber si había pasado algo."""
    out = []
    alerts = [a for a in new.get("alerts") or [] if a not in (old.get("alerts") or [])]
    if alerts:
        out.append("Avisos de la página: " + " | ".join(alerts))
    was, now = (old.get("seen") or "").split("\n"), (new.get("seen") or "").split("\n")
    added = [l for l in dict.fromkeys(now) if l and l not in set(was)]
    gone = [l for l in dict.fromkeys(was) if l and l not in set(now)]
    if added:
        out.append("Aparece a la vista:\n" + "\n".join("+ " + l[:160] for l in added[:10]) + ("\n+ … (%d líneas más)" % (len(added) - 10) if len(added) > 10 else ""))
    if gone:
        out.append("Ya no se ve:\n" + "\n".join("- " + l[:160] for l in gone[:6]) + ("\n- … (%d líneas más)" % (len(gone) - 6) if len(gone) > 6 else ""))
    d = len(new.get("elements") or []) - len(old.get("elements") or [])
    if d:
        out.append("Ahora hay %d elementos para usar (%s%d): sus números han cambiado, vuelve a leerlos con browser_read antes de pulsar otro."
                   % (len(new.get("elements") or []), "+" if d > 0 else "", d))
    if not out:
        return "La página sigue en la misma dirección y no cambió nada a la vista."
    return "La página sigue en la misma dirección.\n" + "\n".join(out)


def accept_language():
    """Idiomas que el navegador pide a las páginas: el de la interfaz de Jayth primero (con la región del sistema si es
    el mismo idioma: es-MX, pt-BR…), luego el inglés. Sin esto las páginas salían en inglés aunque Jayth esté en español."""
    from . import i18n
    lang = i18n.LANG
    try:
        from PySide6.QtCore import QLocale
        sys_tag = QLocale.system().bcp47Name()          # p. ej. «es-MX»
    except Exception:
        sys_tag = ""
    region = {"es": "es-ES", "en": "en-US", "pt": "pt-BR", "fr": "fr-FR", "de": "de-DE", "it": "it-IT", "ja": "ja-JP", "zh": "zh-CN"}.get(lang, lang)
    if sys_tag.lower().startswith(lang + "-") and lang != "zh":
        region = sys_tag
    tags = [region, lang] if region != lang else [lang]
    if lang != "en":
        tags += ["en-US", "en"]
    return ",".join(t if i == 0 else "%s;q=%.1f" % (t, max(0.1, 1.0 - 0.1 * i)) for i, t in enumerate(tags))


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
    if role in ("menuitem", "option") or tag == "li":
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
    if e.get("range"):
        lo, hi, step = e["range"]
        s += " (de %s a %s, de %s en %s: pon el valor con browser_type)" % (lo, hi, step, step)
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
        self.b_back = back = _tb("ui_chevron_derecha", tr("Atrás (Alt+←)"), lambda: self.view and self.view.back(), 13)
        from PySide6.QtGui import QTransform
        back.setIcon(icon("ui_chevron_derecha", C["mut"], 13).pixmap(13, 13).transformed(QTransform().rotate(180)))
        h.addWidget(back)
        self.b_fwd = _tb("ui_chevron_derecha", tr("Adelante (Alt+→)"), lambda: self.view and self.view.forward(), 13)
        h.addWidget(self.b_fwd)
        self.b_reload = _tb("acc_refrescar", tr("Recargar (F5)"), self.reload_or_stop, 14)
        h.addWidget(self.b_reload)
        self.addr = QLineEdit()
        self.addr.setObjectName("addressBar")
        self.addr.setPlaceholderText(tr("Escribe una dirección o lo que quieras buscar"))
        self.addr.returnPressed.connect(lambda: self.view and self.view.load(to_url(self.addr.text())))
        h.addWidget(self.addr, 1)
        self.agent_lbl = QLabel(tr("● Jayth lo está usando"))
        self.agent_lbl.setStyleSheet("color:%s; font-size:9pt; padding: 0 6px" % C["acc"])
        self.agent_lbl.hide()
        h.addWidget(self.agent_lbl)
        h.addWidget(_tb("acc_buscar", tr("Buscar en la página (Ctrl+F)"), self.find_bar, 14))
        h.addWidget(_tb("acc_abrir_externo", tr("Abrir esta página en tu navegador"), self.open_external))
        self.b_menu = _tb("ui_menu_horizontal", tr("Más opciones del navegador"), self.show_menu)
        h.addWidget(self.b_menu)
        h.addWidget(_tb("ui_cerrar", tr("Cerrar el navegador"), lambda: self.closed.emit(), 13))
        v.addWidget(head)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("hline")
        v.addWidget(line)
        from PySide6.QtWidgets import QProgressBar
        self.progress = QProgressBar()                   # avance de la carga: una línea fina bajo la barra
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setStyleSheet("QProgressBar{border:0;background:transparent} QProgressBar::chunk{background:%s}" % C["acc"])
        v.addWidget(self.progress)
        self.finder = self._find_widget()                # «Buscar en la página», oculta hasta que se pide
        v.addWidget(self.finder)
        cls = _view_class()
        if not cls:
            msg = QLabel(tr("Este equipo no tiene el navegador integrado (Qt WebEngine).\nEl agente puede leer páginas con web_fetch."))
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
        self.profile.setHttpAcceptLanguage(accept_language())     # las páginas, en el idioma de la interfaz si lo ofrecen
        self.profile.downloadRequested.connect(self._download)
        self.view = cls()
        self.view.setPage(_page_class()(self.profile, self.view))
        self.view.urlChanged.connect(lambda u: self.addr.setText(u.toString() if u.scheme() not in ("data", "about") else ""))
        self.view.urlChanged.connect(lambda *_: self._sync_nav())
        self.view.loadStarted.connect(self._started)
        self.view.loadProgress.connect(self.progress.setValue)
        self.view.loadFinished.connect(self._finished)
        self.view.page().findTextFinished.connect(self._found)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)       # menú propio: en el idioma de Jayth y sin opciones que no hacen nada
        self.view.customContextMenuRequested.connect(self._context_menu)
        self.holder = _Holder(self.view)
        v.addWidget(self.holder, 1)
        from PySide6.QtGui import QShortcut, QKeySequence
        for keys, fn in (("Ctrl+F", self.find_bar), ("Ctrl+L", lambda: (self.addr.setFocus(), self.addr.selectAll())), ("F5", self.reload_or_stop),
                         ("Ctrl+R", self.reload_or_stop), ("Ctrl++", lambda: self.zoom(+0.1)), ("Ctrl+=", lambda: self.zoom(+0.1)),
                         ("Ctrl+-", lambda: self.zoom(-0.1)), ("Ctrl+0", lambda: self.zoom(0)), ("Alt+Left", self.view.back),
                         ("Alt+Right", self.view.forward), ("Ctrl+P", self.save_pdf)):
            sc = QShortcut(QKeySequence(keys), self, activated=fn)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
        self._sync_nav()
        self.view.setHtml(START % dict(C, title=tr("Navegador de Jayth"), hint=tr("Escribe una dirección arriba o pide al agente que abra una "
                          "página: la verás aquí mientras la usa, y puedes intervenir cuando quieras.")), QUrl("about:blank"))
        self.agent_t = QTimer(self, interval=300, timeout=self._agent_label)

    # ---- estado
    def _started(self):
        self._loading = True
        self.progress.setValue(5)
        self._sync_nav()

    def _finished(self, ok):
        self._loading = False
        self._last_ok = ok
        self.progress.setValue(0)
        self._sync_nav()

    def _sync_nav(self):
        """Atrás y adelante, solo si hay a dónde ir; «Recargar» es «Detener» mientras carga."""
        if self.view is None:
            return
        hist = self.view.history()
        self.b_back.setEnabled(hist.canGoBack())
        self.b_fwd.setEnabled(hist.canGoForward())
        self.b_reload.setIcon(icon("trans_detener" if self._loading else "acc_refrescar", C["mut"], 14))
        tip = tr("Detener la carga (Esc)") if self._loading else tr("Recargar (F5)")
        self.b_reload.setToolTip(tip)
        self.b_reload.setAccessibleName(tip)

    def reload_or_stop(self):
        if self.view is not None:
            self.view.stop() if self._loading else self.view.reload()

    # ---- herramientas del usuario: buscar en la página, tamaño, guardar, datos
    def _find_widget(self):
        w = QWidget()
        w.setObjectName("canvasHead")
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(4)
        self.find_edit = QLineEdit()
        self.find_edit.setObjectName("addressBar")
        self.find_edit.setPlaceholderText(tr("Buscar en la página"))
        self.find_edit.textChanged.connect(lambda *_: self.find_next())
        self.find_edit.returnPressed.connect(self.find_next)
        h.addWidget(self.find_edit, 1)
        self.find_lbl = QLabel("")
        self.find_lbl.setObjectName("muted")
        h.addWidget(self.find_lbl)
        h.addWidget(_tb("ui_chevron_arriba", tr("Anterior (Mayús+Intro)"), lambda: self.find_next(True), 13))
        h.addWidget(_tb("ui_chevron_abajo", tr("Siguiente (Intro)"), self.find_next, 13))
        h.addWidget(_tb("ui_cerrar", tr("Cerrar la búsqueda (Esc)"), lambda: self.find_bar(False), 12))
        w.hide()
        return w

    def find_bar(self, on=True):
        if self.view is None:
            return
        self.finder.setVisible(bool(on))
        if on:
            self.find_edit.setFocus()
            self.find_edit.selectAll()
            self.find_next()
        else:
            self.view.findText("")                      # quita el resaltado
            self.find_lbl.setText("")
            self.view.setFocus()

    def find_next(self, back=False):
        if self.view is None or self.finder.isHidden():
            return
        from PySide6.QtWebEngineCore import QWebEnginePage
        text = self.find_edit.text()
        if back:
            self.view.findText(text, QWebEnginePage.FindBackward)
        else:
            self.view.findText(text)
        if not text:
            self.find_lbl.setText("")

    def _found(self, res):
        if self.finder.isHidden() or not self.find_edit.text():
            return
        n = res.numberOfMatches()
        self.find_lbl.setText((tr("%d de %d") % (res.activeMatch(), n)) if n else tr("Sin resultados"))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and (not self.finder.isHidden() or self._loading):
            if not self.finder.isHidden():
                self.find_bar(False)
            elif self.view is not None:
                self.view.stop()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and (e.modifiers() & Qt.ShiftModifier) and self.find_edit.hasFocus():
            return self.find_next(True)
        super().keyPressEvent(e)

    def zoom(self, step):
        """Agranda o reduce la página (0 = tamaño normal)."""
        if self.view is None:
            return
        f = 1.0 if not step else max(0.3, min(3.0, round(self.view.zoomFactor() + step, 2)))
        self.view.setZoomFactor(f)
        if self.main is not None:
            self.main.toast(tr("Tamaño de la página: %d %%") % round(f * 100), ms=1400)

    def copy_address(self):
        if self.view is not None:
            QApplication.clipboard().setText(self.view.url().toString())
            if self.main is not None:
                self.main.toast(tr("Dirección copiada"), icon_name="acc_copiar", ms=1500)

    def save_pdf(self):
        """Guarda la página como PDF en Descargas (con el título de la página como nombre)."""
        if self.view is None or self.view.url().scheme() not in ("http", "https", "file"):
            return
        d = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
        name = re.sub(r'[\\/:*?"<>|\r\n]+', " ", self.view.title() or "pagina").strip()[:80] or "pagina"
        path, k = os.path.join(d, name + ".pdf"), 2
        while os.path.exists(path):
            path, k = os.path.join(d, "%s (%d).pdf" % (name, k)), k + 1
        self.view.page().printToPdf(path)
        if self.main is not None:
            self.main.toast(tr("Guardando la página como PDF en %s") % path, icon_name="acc_descargar")

    def clear_data(self):
        """Borra cookies, inicios de sesión y caché del navegador de Jayth (pide confirmación: cierra las sesiones)."""
        from PySide6.QtWidgets import QMessageBox
        if self.view is None or QMessageBox.question(self, tr("Borrar los datos del navegador"), tr(
                "Se borrarán las cookies, los inicios de sesión y la caché del navegador de Jayth. Tendrás que volver a "
                "iniciar sesión en los sitios. ¿Continuar?")) != QMessageBox.StandardButton.Yes:
            return
        self.profile.cookieStore().deleteAllCookies()
        self.profile.clearHttpCache()
        self.profile.clearAllVisitedLinks()
        if self.main is not None:
            self.main.toast(tr("Datos del navegador borrados"), icon_name="ui_check", color=C["ok"])

    def show_menu(self):
        from PySide6.QtWidgets import QMenu
        if self.view is None:
            return
        m = QMenu(self)
        m.addAction(icon("acc_buscar"), tr("Buscar en la página…") + "\tCtrl+F", self.find_bar)
        m.addSeparator()
        pct = round(self.view.zoomFactor() * 100)
        m.addAction(tr("Agrandar") + "\tCtrl++", lambda: self.zoom(+0.1))
        m.addAction(tr("Reducir") + "\tCtrl+-", lambda: self.zoom(-0.1))
        a = m.addAction((tr("Tamaño normal (ahora %d %%)") % pct) + "\tCtrl+0", lambda: self.zoom(0))
        a.setEnabled(pct != 100)
        m.addSeparator()
        m.addAction(icon("acc_copiar"), tr("Copiar la dirección"), self.copy_address)
        m.addAction(icon("acc_descargar"), tr("Guardar la página como PDF") + "\tCtrl+P", self.save_pdf)
        m.addAction(icon("acc_abrir_externo"), tr("Abrir esta página en tu navegador"), self.open_external)
        m.addSeparator()
        m.addAction(icon("acc_eliminar"), tr("Borrar los datos del navegador…"), self.clear_data)
        m.exec(self.b_menu.mapToGlobal(self.b_menu.rect().bottomLeft()))

    def _context_menu(self, pos):
        """Menú del botón derecho, en el idioma de Jayth: lo que toca según dónde se pulsó (enlace, imagen, texto, campo)."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtWebEngineCore import QWebEnginePage as P
        from PySide6.QtGui import QDesktopServices
        page = self.view.page()
        req = self.view.lastContextMenuRequest()
        link = req.linkUrl() if req is not None else QUrl()
        media = req.mediaUrl() if req is not None else QUrl()
        sel = (req.selectedText() if req is not None else "") or ""
        editable = bool(req is not None and req.isContentEditable())
        m = QMenu(self)
        if link.isValid() and not link.isEmpty():
            m.addAction(tr("Abrir el enlace"), lambda: self.view.load(link))
            m.addAction(icon("acc_abrir_externo"), tr("Abrir el enlace en tu navegador"), lambda: QDesktopServices.openUrl(link))
            m.addAction(icon("acc_copiar"), tr("Copiar la dirección del enlace"), lambda: QApplication.clipboard().setText(link.toString()))
            m.addAction(icon("acc_descargar"), tr("Guardar lo enlazado…"), lambda: page.triggerAction(P.DownloadLinkToDisk))
            m.addSeparator()
        if media.isValid() and not media.isEmpty() and req.mediaType() == req.MediaType.MediaTypeImage:
            m.addAction(icon("acc_copiar"), tr("Copiar la imagen"), lambda: page.triggerAction(P.CopyImageToClipboard))
            m.addAction(icon("acc_descargar"), tr("Guardar la imagen…"), lambda: page.triggerAction(P.DownloadImageToDisk))
            m.addAction(tr("Copiar la dirección de la imagen"), lambda: QApplication.clipboard().setText(media.toString()))
            m.addSeparator()
        if editable:
            m.addAction(tr("Cortar"), lambda: page.triggerAction(P.Cut)).setEnabled(bool(sel))
        if sel or editable:
            m.addAction(icon("acc_copiar"), tr("Copiar"), lambda: page.triggerAction(P.Copy)).setEnabled(bool(sel))
        if editable:
            m.addAction(tr("Pegar"), lambda: page.triggerAction(P.Paste))
        if sel and not editable:
            short = " ".join(sel.split())[:28] + ("…" if len(" ".join(sel.split())) > 28 else "")
            m.addAction(icon("acc_buscar"), tr("Buscar «%s» en internet") % short, lambda: self.view.load(to_url(" ".join(sel.split())[:300])))
        m.addAction(tr("Seleccionar todo"), lambda: page.triggerAction(P.SelectAll))
        m.addSeparator()
        m.addAction(tr("Atrás"), self.view.back).setEnabled(self.view.history().canGoBack())
        m.addAction(tr("Adelante"), self.view.forward).setEnabled(self.view.history().canGoForward())
        m.addAction(icon("acc_refrescar"), tr("Recargar"), self.view.reload)
        m.addSeparator()
        m.addAction(icon("acc_buscar"), tr("Buscar en la página…"), self.find_bar)
        m.addAction(icon("acc_descargar"), tr("Guardar la página como PDF"), self.save_pdf)
        m.exec(self.view.mapToGlobal(pos))

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
            self.main.toast(tr("Descargando «%s» en %s") % (req.downloadFileName(), d), icon_name="acc_descargar")

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
        old = self.page_info or {}                   # cómo estaba la página la última vez que se leyó (antes de la acción)

        def fin(info):
            same = lambda u: str(u or "").split("#")[0].rstrip("/")          # «…/» y «…» son la misma página
            if info and not before_url:              # recargar: la misma página, vuelta a leer
                self._done(job, self._summary(info, 1200, 40, intro=what + "\n"))
            elif info and same(info["url"]) != same(before_url):
                self._done(job, self._summary(info, 1200, 40, intro=what + "\nSe abrió otra página.\n"))
            elif info:
                self._done(job, what + "\n" + page_changes(old, info))
            else:
                self._done(job, what)
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

    def _do_click(self, job, index=None, text=None, expect=None):
        if index in (None, "") and not text:
            return self._fail(job, "Indica index (número de browser_read) o text (el texto del enlace o botón).")
        if index in (None, ""):
            return self._find(job, text, lambda i: self._do_click(job, i))
        if text and expect is None:                  # número y texto a la vez: el texto sirve de comprobación
            expect = text
        before = self.view.url().toString()

        def go(loc):
            if loc.get("disabled"):
                return self._fail(job, "Ese elemento está desactivado ahora mismo.")
            if loc["tag"] == "select":
                return self._fail(job, "Es una lista desplegable: elige la opción con browser_type (text = la opción).")
            if loc.get("type") == "range":
                return self._fail(job, "Es un deslizador: pon su valor con browser_type (text = el número).")
            info = next((e for e in (self.page_info or {}).get("elements", []) if e["i"] == int(index)), None)
            want = " ".join(str(expect or "").lower().split())
            if want and info is not None and want not in " ".join((info["label"] + " " + info["value"]).lower().split()):
                # los números cambian cada vez que la página se redibuja: mejor no pulsar que pulsar otro botón
                return self._fail(job, "El elemento %s ahora es %s%s, no «%s»: la página cambió desde que la leíste. Vuelve a leerla con "
                                       "browser_read (what=elements) o pulsa por su texto." % (index, _role(info),
                                                                                             (" «%s»" % info["label"]) if info["label"] else "", expect))
            r = self._point(loc)
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

    def _do_shot(self, job, width=0, full_page=False, from_px=0):
        """Captura la página. width: ancho en píxeles con el que se maqueta (el panel suele ser estrecho y las páginas
        muestran su versión de móvil; con 1280 se ve la de escritorio, reducida). full_page: la página entera, no solo lo
        que se ve (hasta 8 pantallas o 12 000 px; si no cabe, se dice hasta dónde llega y from_px sigue desde ahí)."""
        from PySide6.QtGui import QImage
        view = self.view
        z0 = view.zoomFactor()
        vw = max(1, view.width())
        want = max(320, min(2560, int(width or 0))) if width else 0
        zoom = max(0.25, min(5.0, vw / float(want))) if want else z0
        shots = []
        meta = {}                                    # vh y alto total de la página (píxeles de CSS)

        def finish():
            if abs(view.zoomFactor() - z0) > 0.001:
                view.setZoomFactor(z0)
            if not shots:
                return self._fail(job, "No pude capturar la página.")
            if len(shots) == 1:
                img = shots[0][1]
            else:                                    # la página entera: las pantallas, una debajo de otra
                h = min(sum(s[2] for s in shots), 12000)
                img = QImage(shots[0][1].width(), h, QImage.Format_RGB32)
                img.fill(QColor("white"))
                p = QPainter(img)
                y = 0
                for top, im, use in shots:
                    p.drawImage(0, y, im, 0, im.height() - use, im.width(), use)
                    y += use
                p.end()
            cut = ""
            if len(shots) > 1 and meta.get("vh"):     # ¿llegó hasta el final? (8 pantallas o 12 000 px como mucho)
                ratio = shots[0][1].height() / float(meta["vh"])           # píxeles de la imagen por píxel de la página
                got = min(sum(s[2] for s in shots), 12000) / max(ratio, 0.01)
                end = int(meta["from"] + got)
                if end < meta["total"] - 4:
                    cut = ("; recortada: llega hasta %d px de los %d de la página. Para el resto: full_page=true y from_px=%d"
                           % (end, meta["total"], end))
            if img.width() > 1024:
                img = img.scaledToWidth(1024, Qt.SmoothTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "PNG")
            buf.close()
            css_w = round(vw / (zoom or 1.0))
            note = "maquetada a %d px de ancho" % css_w
            if want and abs(css_w - want) > 8:
                note += " (se pidió %d: es lo más cerca que permite el zoom del panel)" % want
            if not want and css_w < 800:
                note += " (panel estrecho: muchas páginas muestran aquí su versión de móvil; con width=1280 se ve la de escritorio)"
            if img.width() < css_w - 8:                  # el panel (o el tope de 1024) es más estrecho que la maqueta
                note += "; la imagen se entrega a %d px de ancho: la página se ve reducida" % img.width()
            what = ""
            if len(shots) > 1:
                what = ", página entera" if not from_px else ", desde %d px" % from_px
            self._done(job, {"text": "Captura del navegador (%dx%d, %s%s%s): «%s»  %s" % (
                img.width(), img.height(), note, what, cut, view.title(), view.url().toString()),
                "image": bytes(ba.data())})

        def grab_one(top, use):
            im = view.grab().toImage()
            dpr = im.height() / float(max(1, view.height()))
            shots.append((top, im, int(round(use * dpr)) if use else im.height()))

        def page(info_json):
            try:
                d = json.loads(info_json or "{}")
            except ValueError:
                d = {}
            vh, total, y0 = int(d.get("vh") or 0), int(d.get("h") or 0), int(d.get("y") or 0)
            start = min(max(0, int(from_px or 0)), max(0, total - vh))
            meta.update(vh=vh, total=total, **{"from": start})
            if not full_page or vh <= 0 or (total <= vh + 4 and not start):
                grab_one(0, 0)
                return finish()
            tops = list(range(start, total, vh))[:8]

            def step(k):
                if k >= len(tops):
                    return self._js("window.scrollTo(0, %d); true" % y0, lambda _r: QTimer.singleShot(150, finish))
                top = tops[k]
                real = min(top, max(0, total - vh))         # la última pantalla no baja más allá del final
                use = vh if top == real else min(vh, total - top)
                # use: cuánto de esta pantalla es nuevo (de la última solo cuenta la franja de abajo); en píxeles de CSS × zoom
                self._js("window.scrollTo(0, %d); true" % real,
                         lambda _r: QTimer.singleShot(260, lambda: (grab_one(top, use * view.zoomFactor()), step(k + 1))))
            step(0)

        def measure():
            self._js("JSON.stringify({vh: innerHeight, h: document.documentElement.scrollHeight, y: Math.round(scrollY)})", page)
        if want and abs(zoom - z0) > 0.001:
            view.setZoomFactor(zoom)
            QTimer.singleShot(700, measure)             # que la página se vuelva a maquetar con el ancho nuevo
        else:
            QTimer.singleShot(0, measure)


# ---------------------------------------------------------------- puente entre el hilo del agente y la interfaz
# ---------------------------------------------------------------- búsquedas con el motor del navegador (sin mostrarlo)
_SEARCH = {
    "ddg": ("https://html.duckduckgo.com/html/?q={q}",
            "document.querySelectorAll('.result').forEach(function(r){var a=r.querySelector('a.result__a');if(!a)return;"
            "var s=r.querySelector('.result__snippet');o.push({t:a.innerText,u:a.href,s:s?s.innerText:''});});"),
    "bing": ("https://www.bing.com/search?q={q}&setlang={lang}",
             "document.querySelectorAll('li.b_algo').forEach(function(r){var a=r.querySelector('h2 a');if(!a)return;"
             "var s=r.querySelector('.b_caption p, p.b_lineclamp2, p.b_lineclamp3, p.b_lineclamp4, .b_snippet');"
             "o.push({t:a.innerText,u:a.href,s:s?s.innerText:''});});"),
}


class HiddenSearch(QObject):
    """Busca en la web con el motor del navegador integrado (Chromium), en una página que no se muestra: la página de
    resultados se abre como en cualquier navegador. Si el buscador pide verificación (captcha), no se toca: se devuelve
    None y la búsqueda prueba otra fuente. Perfil propio y persistente (sus cookies), aparte del navegador visible."""
    sig = Signal(object)

    def __init__(self):
        super().__init__()
        self.page = self.profile = None
        self.sig.connect(self._run, Qt.QueuedConnection)

    def search(self, engine, query, stop=None, timeout=25):
        """Desde cualquier hilo: [{'t', 'u', 's'}] con los resultados, o None si pidió verificación o no cargó."""
        from . import i18n
        url = _SEARCH[engine][0].format(q=urllib.parse.quote_plus(query), lang=i18n.LANG)
        job = {"url": url, "js": _SEARCH[engine][1], "ev": threading.Event(), "res": None, "err": None}
        self.sig.emit(job)
        end = time.time() + timeout
        while not job["ev"].wait(0.2):
            if (stop is not None and stop.is_set()) or time.time() > end:
                return None
        if job["err"] or not isinstance(job["res"], dict):
            return None
        res = job["res"].get("res") or []
        if not res:
            low = (job["res"].get("title", "") + " " + job["res"].get("body", "")).lower()
            return None if any(w in low for w in ("captcha", "anomaly", "unusual traffic", "verify", "robot", "challenge",
                                                  "bots use", "are you human", "not a robot")) else []
        return res

    def _run(self, job):
        try:
            if self.page is None:
                from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
                base = os.path.join(paths.DATA, "navegador", "busqueda")
                self.profile = QWebEngineProfile("jayth-busqueda", self)
                self.profile.setPersistentStoragePath(os.path.join(base, "datos"))
                self.profile.setCachePath(os.path.join(base, "cache"))
                self.profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
                self.profile.setHttpAcceptLanguage(accept_language())
                self.page = QWebEnginePage(self.profile, self)
            page = self.page
            code = ("(function(){var o=[];" + job["js"] + "return JSON.stringify({title:document.title,res:o,"
                    "body:document.body?document.body.innerText.slice(0,400):''});})()")

            def got(r, again=True):
                try:
                    job["res"] = json.loads(r) if r else None
                except ValueError:
                    job["res"] = None
                if again and not (job["res"] or {}).get("res"):          # aún pintando (p. ej. la tarjeta del tiempo): otra vez
                    from PySide6.QtWebEngineCore import QWebEngineScript
                    return QTimer.singleShot(1500, lambda: page.runJavaScript(code, QWebEngineScript.ApplicationWorld,
                                                                             lambda r2: got(r2, False)))
                job["ev"].set()

            def finished(ok):
                try:
                    page.loadFinished.disconnect(finished)
                except (RuntimeError, TypeError):
                    pass
                from PySide6.QtWebEngineCore import QWebEngineScript
                QTimer.singleShot(600, lambda: page.runJavaScript(code, QWebEngineScript.ApplicationWorld, got))
            page.loadFinished.connect(finished)
            page.load(QUrl(job["url"]))
        except Exception as e:
            job["err"] = "%s: %s" % (type(e).__name__, e)
            job["ev"].set()


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
