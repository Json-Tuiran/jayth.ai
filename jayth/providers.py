# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Proveedores de modelos por API: servicios en la nube (OpenAI, Claude, Gemini, OpenRouter…) o servidores propios
(Ollama, LM Studio, uno de la empresa) con formato compatible con OpenAI. Se pueden guardar varios y elegir sus
modelos desde el mismo menú que los modelos locales. Las claves se guardan solo en este equipo."""
import json, uuid, urllib.request, urllib.error
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QListWidget, QListWidgetItem, QFrame,
                               QMessageBox, QWidget, QScrollArea)
from . import APP_NAME, core
from .theme import C
from .wizard import btn, lbl, run_bg
from .i18n import tr

# (nombre, URL base, dónde se consigue la clave, modelos sugeridos por si el servicio no deja listar)
TEMPLATES = [
    ("OpenAI", "https://api.openai.com/v1", "platform.openai.com/api-keys", []),
    ("Claude (Anthropic)", "https://api.anthropic.com/v1", "console.anthropic.com/settings/keys", []),
    ("Gemini (Google)", "https://generativelanguage.googleapis.com/v1beta/openai", "aistudio.google.com/apikey", []),
    (tr("OpenRouter (muchos modelos)"), "https://openrouter.ai/api/v1", "openrouter.ai/keys", []),
    ("Groq", "https://api.groq.com/openai/v1", "console.groq.com/keys", []),
    ("Mistral", "https://api.mistral.ai/v1", "console.mistral.ai/api-keys", []),
    ("DeepSeek", "https://api.deepseek.com/v1", "platform.deepseek.com/api_keys", []),
    ("xAI (Grok)", "https://api.x.ai/v1", "console.x.ai", []),
    (tr("Ollama (en este equipo)"), "http://127.0.0.1:11434/v1", "", []),
    (tr("LM Studio (en este equipo)"), "http://127.0.0.1:1234/v1", "", []),
    (tr("Otro servidor compatible con OpenAI"), "", "", []),
]


def list_models(url, key, timeout=15):
    """Nombres de los modelos que ofrece el servicio (GET /models). Lanza RuntimeError con un mensaje claro."""
    url = (url or "").strip().rstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        raise RuntimeError(tr("La dirección debe empezar por http:// o https://"))
    headers = {"Authorization": "Bearer " + (key or "local"), "User-Agent": APP_NAME, "Accept": "application/json"}
    if "anthropic.com" in url:                    # Claude también acepta su cabecera propia
        headers.update({"x-api-key": key or "", "anthropic-version": "2023-06-01"})
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url + "/models", headers=headers), timeout=timeout).read(4_000_000)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError(tr("El servicio rechazó la clave (HTTP %d). Revisa que esté bien copiada y activa.") % e.code)
        if e.code == 404:
            raise RuntimeError(tr("El servicio no ofrece la lista de modelos (HTTP 404). Escribe el nombre del modelo a mano."))
        raise RuntimeError(tr("El servicio respondió HTTP %d.") % e.code)
    except Exception as e:
        raise RuntimeError(tr("No se pudo conectar: %s") % getattr(e, "reason", e))
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise RuntimeError(tr("La respuesta del servicio no es válida (¿la dirección termina en /v1?)."))
    data = j.get("data") if isinstance(j, dict) else j
    if data is None and isinstance(j, dict):
        data = j.get("models") or []
    names = []
    for it in data or []:
        n = (it.get("id") or it.get("name") or "") if isinstance(it, dict) else str(it)
        n = n[7:] if n.startswith("models/") else n          # Gemini antepone «models/»
        if n:
            names.append(n)
    # fuera lo que no sirve para conversar (voz, imágenes, incrustaciones, moderación…)
    skip = ("embed", "whisper", "tts", "dall-e", "moderation", "image", "audio", "realtime", "rerank", "transcribe", "babbage", "davinci", "imagen", "veo")
    chat = [n for n in names if not any(s in n.lower() for s in skip)]
    return sorted(chat or names, key=str.lower)


def test_chat(url, key, model, timeout=40):
    """Envía «hola» al modelo para comprobar que la clave y el nombre funcionan. Devuelve la respuesta o lanza RuntimeError."""
    payload = {"model": model, "messages": [{"role": "user", "content": "Responde solo: hola"}], "max_tokens": 300}
    req = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + (key or "local"), "User-Agent": APP_NAME})
    try:
        j = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read(600).decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("error")
            body = msg.get("message") if isinstance(msg, dict) else str(msg or body)
        except ValueError:
            pass
        raise RuntimeError("HTTP %d: %s" % (e.code, str(body)[:300]))
    except Exception as e:
        raise RuntimeError(tr("No se pudo conectar: %s") % getattr(e, "reason", e))
    try:
        return (j["choices"][0]["message"].get("content") or "").strip() or tr("(respuesta vacía, pero el servicio contestó)")
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(tr("Respuesta inesperada del servicio."))


def saved(cfg=None):
    return list((cfg or core.SET.snapshot()).get("providers") or [])


# ---------------------------------------------------------------- consumo y novedades (textos para el diálogo y el chat)
def tok_short(n):
    """Tokens en corto: 950, 12,3 k, 5,8 M."""
    from . import i18n
    n = int(n or 0)

    def short(v, dec):                               # sin ceros de adorno: «50 k», no «50.0 k»
        s = i18n.number(v, dec)
        return s.rstrip("0").rstrip(".,") if dec and ("." in s or "," in s) else s
    if n >= 1_000_000:
        return short(n / 1e6, 2 if n < 10_000_000 else 1) + " M"
    if n >= 10_000:
        return short(n / 1e3, 0 if n >= 100_000 else 1) + " k"
    return i18n.number(n, 0)


def money(usd):
    """Un importe en dólares: «≈ 4,85 US$», «< 0,01 US$»."""
    from . import i18n
    if usd is None:
        return ""
    if 0 < usd < 0.01:
        return "< %s US$" % i18n.number(0.01, 2)
    return "%s US$" % i18n.number(usd, 2)


def spent_text(t):
    """«12 peticiones · 345 k tokens de entrada · 12 k de salida · ≈ 1,43 US$» a partir de un total de consumo."""
    if not t or not t.get("n"):
        return tr("nada")
    s = (tr("%d petición") if t["n"] == 1 else tr("%d peticiones")) % t["n"]
    s += " · " + tr("%s tokens de entrada · %s de salida") % (tok_short(t["i"]), tok_short(t["o"]))
    if t["sin_precio"] < t["n"]:
        s += " · " + ("≈ " if t.get("estimado") else "") + money(t["usd"])
        if t["sin_precio"]:
            s += " " + tr("(sin contar %d de precio desconocido)") % t["sin_precio"]
    return s


def usage_html(url, models=(), saldo=None):
    """El bloque de consumo de un servicio para el diálogo «Modelos por API»."""
    import html, time
    from . import consumo as U, i18n
    sm = U.summary(url)
    esc = html.escape
    out = ["<b>%s</b>" % esc(tr("Consumo desde este equipo"))]
    if not sm["todo"]["n"]:
        out.append(esc(tr("Todavía no has usado este servicio desde Jayth.")))
    else:
        out.append(esc(tr("Hoy: %s") % spent_text(sm["hoy"])))
        out.append(esc(tr("Últimos 30 días: %s") % spent_text(sm["30d"])))
        since = time.strftime("%d/%m/%Y", time.localtime(sm["desde"])) if sm["desde"] else ""
        out.append(esc(tr("Total desde el %s: %s") % (since, spent_text(sm["todo"]))))
        for m, t in sm["modelos"][:4]:
            pr = U.price(url, m)
            src = {"tuyo": tr("precio que escribiste"), "servicio": tr("precio que publica el servicio"),
                   "lista": tr("precio de lista del %s") % U.PRICES_DATE}.get(pr[2], "") if pr else tr("precio desconocido: escríbelo con «Precio de un modelo…»")
            out.append("&nbsp;&nbsp;" + esc("%s: %s (%s)" % (m, spent_text(t), src)))
    lim = U.LIMITS.get(url.rstrip("/"))
    if lim:
        parts = []
        for kind, name in (("requests", tr("peticiones")), ("tokens", tr("tokens"))):
            if kind in lim:
                left, top, _reset = lim[kind]
                parts.append((tr("%s de %s %s") % (i18n.number(left, 0), i18n.number(top, 0), name)) if top else "%s %s" % (i18n.number(left, 0), name))
        if parts:
            mins = max(0, int((time.time() - lim["t"]) / 60))
            out.append(esc(tr("Límites de tu cuenta (según la última respuesta, hace %d min): te quedan %s en la ventana actual.") % (mins, tr(" y ").join(parts))))
    if isinstance(saldo, dict):
        if saldo.get("queda") is not None and saldo.get("moneda"):
            out.append(esc(tr("Saldo de la cuenta: %s %s") % (i18n.number(float(saldo["queda"]), 2), saldo["moneda"])))
        elif saldo.get("usado") is not None:
            line = tr("Gastado en la cuenta según el servicio: %s") % money(float(saldo["usado"]))
            if saldo.get("queda") is not None:
                line += " · " + tr("te quedan %s de tu tope") % money(float(saldo["queda"]))
            out.append(esc(line))
    out.append("<span style='color:%s'>%s</span>" % (C["faint"], esc(tr(
        "Jayth cuenta solo lo que se envió desde este equipo; la cifra oficial y tu plan están en la página del servicio."))))
    return "<br>".join(out)


def model_news(p, names):
    """Compara la lista de modelos del servicio con la que se vio la última vez. Devuelve (aviso o '', lista para guardar)."""
    names = list(names or [])
    seen = p.get("seen")
    if not names or not isinstance(seen, list) or not seen:
        return "", names or (seen or [])
    new = [n for n in names if n not in seen]
    gone = [n for n in (p.get("models") or []) if n not in names]
    parts = []
    if new:
        parts.append(((tr("%d modelo nuevo: %s") if len(new) == 1 else tr("%d modelos nuevos: %s")) % (len(new), ", ".join(new[:6]) + (" …" if len(new) > 6 else ""))))
    if gone:
        parts.append(tr("ya no ofrece %s, que tienes marcado: elige otro") % ", ".join(gone[:4]))
    return (tr("Novedades de este servicio: %s.") % "; ".join(parts)) if parts else "", names


def use(provider, model):
    """Activa un modelo de un proveedor guardado (apaga el modelo local para liberar memoria)."""
    core.LLM_MGR.stop()
    core.SET.update({"llm_mode": "external", "external_url": provider["url"], "external_key": provider.get("key", ""),
                     "external_model": model, "external_provider": provider["id"], "setup_done": True})


def migrate():
    """El antiguo «servidor externo» único pasa a ser el primer proveedor guardado."""
    cfg = core.SET.snapshot()
    if cfg.get("providers") or not cfg.get("external_model") or not cfg.get("external_url"):
        return
    name = next((t[0] for t in TEMPLATES if t[1] and t[1].rstrip("/") == cfg["external_url"].rstrip("/")), tr("Servidor externo"))
    p = {"id": uuid.uuid4().hex[:8], "name": name, "url": cfg["external_url"], "key": cfg.get("external_key", ""), "models": [cfg["external_model"]]}
    core.SET.update({"providers": [p], "external_provider": p["id"]})


class ProvidersDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Modelos por API"))
        self.resize(860, 620)
        self.cur = None                       # proveedor que se está editando (None = nuevo)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        left = QWidget()
        left.setObjectName("sidebar")
        left.setFixedWidth(250)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 14, 10, 10)
        t = QLabel(tr("Servicios guardados"))
        t.setObjectName("h1")
        lv.addWidget(t)
        self.lst = QListWidget()
        self.lst.setObjectName("history")
        self.lst.currentRowChanged.connect(self._pick)
        lv.addWidget(self.lst, 1)
        lv.addWidget(btn(tr("Añadir servicio"), None, self._new, "acc_anadir"))
        root.addWidget(left)
        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(22, 16, 22, 14)
        v.setSpacing(8)
        v.addWidget(lbl(tr("Usa modelos de servicios en la nube o de tu propio servidor con tu clave de API. La clave se guarda solo en este "
                           "equipo. Las suscripciones de usuario (ChatGPT Plus, Claude Pro…) no sirven aquí: hace falta una clave de API."), "faint"))
        v.addWidget(QLabel(tr("Servicio")))
        self.tpl = QComboBox()
        for n, u, where, _ in TEMPLATES:
            self.tpl.addItem(n, (u, where))
        self.tpl.activated.connect(self._template)
        v.addWidget(self.tpl)
        v.addWidget(QLabel(tr("Nombre")))
        self.e_name = QLineEdit()
        v.addWidget(self.e_name)
        v.addWidget(QLabel(tr("Dirección (termina en /v1)")))
        self.e_url = QLineEdit()
        self.e_url.setPlaceholderText("https://…/v1")
        v.addWidget(self.e_url)
        v.addWidget(QLabel(tr("Clave de API")))
        self.e_key = QLineEdit()
        self.e_key.setEchoMode(QLineEdit.Password)
        v.addWidget(self.e_key)
        self.where = lbl("", "faint")
        v.addWidget(self.where)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Modelos que quieres usar")), 1)
        row.addWidget(btn(tr("Ver modelos disponibles"), None, self._fetch, "acc_refrescar"))
        v.addLayout(row)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filtrar o escribir un nombre de modelo y pulsar Enter para añadirlo…"))
        self.filter.textChanged.connect(self._apply_filter)
        self.filter.returnPressed.connect(self._add_typed)
        v.addWidget(self.filter)
        self.models = QListWidget()
        self.models.setObjectName("history")
        v.addWidget(self.models, 1)
        self.msg = lbl("", "faint")
        self.msg.setWordWrap(True)
        v.addWidget(self.msg)
        # consumo de este servicio: lo que Jayth envió desde este equipo, los límites de la cuenta y, si el servicio lo da, el saldo
        self.usage = QLabel("")
        self.usage.setObjectName("faint")
        self.usage.setWordWrap(True)
        self.usage.setTextFormat(Qt.RichText)
        self.usage.hide()
        v.addWidget(self.usage)
        foot = QHBoxLayout()
        self.b_del = btn(tr("Quitar servicio"), "danger", self._delete)
        foot.addWidget(self.b_del)
        self.b_usage = btn(tr("Consumo oficial"), None, self._open_usage, "acc_abrir_externo")
        self.b_usage.setToolTip(tr("Abre en tu navegador la página del servicio con tu consumo y tu facturación reales"))
        self.b_usage.hide()
        foot.addWidget(self.b_usage)
        self.b_price = btn(tr("Precio de un modelo…"), None, self._set_price)
        self.b_price.setToolTip(tr("Para que Jayth calcule lo que gastas con un modelo del que no conoce el precio"))
        self.b_price.hide()
        foot.addWidget(self.b_price)
        foot.addStretch(1)
        foot.addWidget(btn(tr("Probar"), None, self._test))
        foot.addWidget(btn(tr("Guardar"), "primary", self._save))
        foot.addWidget(btn(tr("Cerrar"), None, self.accept))
        v.addLayout(foot)
        root.addWidget(right, 1)
        self._reload()
        if self.lst.count():
            self.lst.setCurrentRow(0)
        else:
            self._new()

    # ---- lista de servicios
    def _reload(self, select=None):
        self.lst.blockSignals(True)
        self.lst.clear()
        for p in saved():
            it = QListWidgetItem("%s  ·  %d" % (p["name"], len(p.get("models") or [])))
            it.setData(Qt.UserRole, p["id"])
            it.setToolTip(p["url"])
            self.lst.addItem(it)
            if p["id"] == select:
                self.lst.setCurrentItem(it)
        self.lst.blockSignals(False)

    def _pick(self, row):
        pid = self.lst.item(row).data(Qt.UserRole) if row >= 0 else None
        p = next((x for x in saved() if x["id"] == pid), None)
        if not p:
            return
        self.cur = p["id"]
        i = next((k for k in range(self.tpl.count()) if self.tpl.itemData(k)[0] and self.tpl.itemData(k)[0].rstrip("/") == p["url"].rstrip("/")), self.tpl.count() - 1)
        self.tpl.setCurrentIndex(i)
        self.e_name.setText(p["name"])
        self.e_url.setText(p["url"])
        self.e_key.setText(p.get("key", ""))
        self.where.setText("")
        self._set_models(p.get("models") or [], p.get("models") or [])
        self.b_del.show()
        self.msg.setText("")
        self._show_usage(p)
        self._check_news(p)

    def _new(self):
        self.cur = None
        self.lst.blockSignals(True)
        self.lst.clearSelection()
        self.lst.setCurrentRow(-1)
        self.lst.blockSignals(False)
        self.tpl.setCurrentIndex(0)
        self.e_key.clear()
        self._template(0)
        self._set_models([], [])
        self.b_del.hide()
        for w in (self.usage, self.b_usage, self.b_price):
            w.hide()
        self.msg.setText(tr("Elige el servicio, pega tu clave y pulsa «Ver modelos disponibles»."))

    def _template(self, i):
        url, where = self.tpl.itemData(i)
        name = self.tpl.itemText(i).split(" (")[0]
        if self.cur is None or not self.e_name.text().strip():
            self.e_name.setText("" if not url else name)
        self.e_url.setText(url)
        self.where.setText((tr("Consigue tu clave en %s") % where) if where else (tr("No necesita clave.") if url.startswith("http://127.") else ""))

    # ---- modelos
    def _set_models(self, names, checked):
        self.models.clear()
        chk = set(checked)
        for n in list(dict.fromkeys(list(checked) + list(names))):
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n in chk else Qt.Unchecked)
            self.models.addItem(it)
        self._apply_filter()

    def _checked(self):
        return [self.models.item(i).text() for i in range(self.models.count()) if self.models.item(i).checkState() == Qt.Checked]

    def _apply_filter(self, *_):
        q = self.filter.text().strip().lower()
        for i in range(self.models.count()):
            it = self.models.item(i)
            it.setHidden(bool(q) and q not in it.text().lower())

    def _add_typed(self):
        n = self.filter.text().strip()
        if not n:
            return
        cur = self._checked()
        allm = [self.models.item(i).text() for i in range(self.models.count())]
        self.filter.clear()
        self._set_models(allm, list(dict.fromkeys(cur + [n])))

    def _fetch(self):
        url, key = self.e_url.text().strip(), self.e_key.text().strip()
        self.msg.setText(tr("Consultando los modelos del servicio…"))

        def done(r):
            if isinstance(r, Exception):
                return self.msg.setText("✗ %s" % r)
            self._set_models(r, self._checked())
            self.msg.setText(tr("✓ %d modelos disponibles. Marca los que quieras tener en el menú.") % len(r))
        run_bg(lambda: list_models(url, key), done)

    def _test(self):
        url, key = self.e_url.text().strip(), self.e_key.text().strip()
        models = self._checked()
        if not models:
            return self.msg.setText(tr("Marca al menos un modelo para probarlo."))
        self.msg.setText(tr("Probando %s…") % models[0])

        def done(r):
            self.msg.setText(("✗ %s" % r) if isinstance(r, Exception) else tr("✓ %s responde: %s") % (models[0], str(r)[:120]))
        run_bg(lambda: test_chat(url, key, models[0]), done)

    # ---- consumo, límites, saldo y novedades del servicio
    def _show_usage(self, p):
        """Lo gastado con este servicio desde este equipo, los límites de la cuenta y (si el servicio lo dice) el saldo."""
        from . import consumo as U
        url = p["url"]
        self.usage.setText(usage_html(url, p.get("models") or []))
        self.usage.show()
        self.b_usage.setVisible(bool(U.usage_page(url)))
        self.b_price.show()
        pid = p["id"]

        def done(r):                                   # el saldo llega después (hay que pedírselo al servicio)
            if isinstance(r, dict) and self.cur == pid:
                self.usage.setText(usage_html(url, p.get("models") or [], saldo=r))
        if p.get("key"):
            run_bg(lambda: U.balance(url, p.get("key")), done)

    def _open_usage(self):
        from . import consumo as U
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        page = U.usage_page(self.e_url.text().strip())
        if page:
            QDesktopServices.openUrl(QUrl(page))

    def _set_price(self):
        """El usuario escribe el precio de un modelo (US$ por millón de tokens) para que Jayth pueda calcular su gasto."""
        from PySide6.QtWidgets import QInputDialog
        from . import consumo as U
        p = next((x for x in saved() if x["id"] == self.cur), None)
        models = self._checked() or (p or {}).get("models") or []
        if not p or not models:
            return self.msg.setText(tr("Guarda primero el servicio con algún modelo marcado."))
        model, ok = QInputDialog.getItem(self, tr("Precio de un modelo"), tr("Modelo:"), models, 0, False)
        if not ok or not model:
            return
        known = U.price(p["url"], model)
        text, ok = QInputDialog.getText(self, tr("Precio de un modelo"), tr(
            "Precio de %s en US$ por millón de tokens: entrada y salida, separados por un espacio (por ejemplo «3 15»). "
            "Déjalo vacío para quitar tu precio.") % model, text=("%g %g" % known[:2]) if known else "")
        if not ok:
            return
        nums = [x for x in text.replace(",", ".").replace(";", " ").split() if x]
        ps = saved()
        mine = next(x for x in ps if x["id"] == p["id"])
        prices = dict(mine.get("prices") or {})
        if not nums:
            prices.pop(model, None)
        else:
            try:
                a, b = float(nums[0]), float(nums[1] if len(nums) > 1 else nums[0])
            except ValueError:
                return self.msg.setText(tr("No entiendo ese precio: escribe dos números, entrada y salida."))
            prices[model] = [a, b]
        mine["prices"] = prices
        core.SET.update({"providers": ps})
        self._show_usage(mine)
        self.msg.setText(tr("✓ Precio guardado. Se aplica a lo que gastes desde ahora."))

    def _check_news(self, p):
        """Al abrir un servicio guardado se mira su lista de modelos: avisa de los nuevos y de los que ya no ofrece."""
        pid, url, key = p["id"], p["url"], p.get("key", "")

        def done(r):
            if isinstance(r, Exception) or self.cur != pid:
                return
            text, seen = model_news(p, r)
            ps = saved()
            mine = next((x for x in ps if x["id"] == pid), None)
            if mine is not None and mine.get("seen") != seen:
                mine["seen"] = seen
                core.SET.update({"providers": ps})
            if text:
                self.msg.setText(text)
                self._set_models(r, self._checked())
        run_bg(lambda: list_models(url, key), done)

    # ---- guardar / quitar
    def _save(self):
        name, url = self.e_name.text().strip(), self.e_url.text().strip().rstrip("/")
        models = self._checked()
        if not name or not url.lower().startswith(("http://", "https://")):
            return self.msg.setText(tr("Escribe un nombre y una dirección que empiece por http:// o https://"))
        if not models:
            return self.msg.setText(tr("Marca al menos un modelo (pulsa «Ver modelos disponibles» o escribe su nombre y Enter)."))
        ps = saved()
        p = next((x for x in ps if x["id"] == self.cur), None)
        if p is None:
            p = {"id": uuid.uuid4().hex[:8]}
            ps.append(p)
        p.update({"name": name, "url": url, "key": self.e_key.text().strip(), "models": models})
        listed = [self.models.item(i).text() for i in range(self.models.count())]
        if len(listed) > len(models):                  # la lista del servicio tal como se vio: para avisar de novedades la próxima vez
            p["seen"] = listed
        core.SET.update({"providers": ps})
        self.cur = p["id"]
        cfg = core.SET.snapshot()
        if cfg.get("external_provider") == p["id"] and cfg["llm_mode"] == "external":     # el activo cambió de clave o dirección
            core.SET.update({"external_url": url, "external_key": p["key"],
                             "external_model": cfg["external_model"] if cfg["external_model"] in models else models[0]})
        self._reload(p["id"])
        self.b_del.show()
        self.msg.setText(tr("✓ Guardado. Sus modelos ya aparecen en el menú de modelos."))
        self._show_usage(p)

    def _delete(self):
        p = next((x for x in saved() if x["id"] == self.cur), None)
        if not p or QMessageBox.question(self, tr("Quitar servicio"), tr("¿Quitar «%s» y su clave de este equipo?") % p["name"]) != QMessageBox.StandardButton.Yes:
            return
        core.SET.update({"providers": [x for x in saved() if x["id"] != p["id"]]})
        self._reload()
        if self.lst.count():
            self.lst.setCurrentRow(0)
        else:
            self._new()
