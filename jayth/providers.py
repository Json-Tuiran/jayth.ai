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

# (nombre, URL base, dónde se consigue la clave, modelos sugeridos por si el servicio no deja listar)
TEMPLATES = [
    ("OpenAI", "https://api.openai.com/v1", "platform.openai.com/api-keys", []),
    ("Claude (Anthropic)", "https://api.anthropic.com/v1", "console.anthropic.com/settings/keys", []),
    ("Gemini (Google)", "https://generativelanguage.googleapis.com/v1beta/openai", "aistudio.google.com/apikey", []),
    ("OpenRouter (muchos modelos)", "https://openrouter.ai/api/v1", "openrouter.ai/keys", []),
    ("Groq", "https://api.groq.com/openai/v1", "console.groq.com/keys", []),
    ("Mistral", "https://api.mistral.ai/v1", "console.mistral.ai/api-keys", []),
    ("DeepSeek", "https://api.deepseek.com/v1", "platform.deepseek.com/api_keys", []),
    ("xAI (Grok)", "https://api.x.ai/v1", "console.x.ai", []),
    ("Ollama (en este equipo)", "http://127.0.0.1:11434/v1", "", []),
    ("LM Studio (en este equipo)", "http://127.0.0.1:1234/v1", "", []),
    ("Otro servidor compatible con OpenAI", "", "", []),
]


def list_models(url, key, timeout=15):
    """Nombres de los modelos que ofrece el servicio (GET /models). Lanza RuntimeError con un mensaje claro."""
    url = (url or "").strip().rstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        raise RuntimeError("La dirección debe empezar por http:// o https://")
    headers = {"Authorization": "Bearer " + (key or "local"), "User-Agent": APP_NAME, "Accept": "application/json"}
    if "anthropic.com" in url:                    # Claude también acepta su cabecera propia
        headers.update({"x-api-key": key or "", "anthropic-version": "2023-06-01"})
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url + "/models", headers=headers), timeout=timeout).read(4_000_000)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("El servicio rechazó la clave (HTTP %d). Revisa que esté bien copiada y activa." % e.code)
        if e.code == 404:
            raise RuntimeError("El servicio no ofrece la lista de modelos (HTTP 404). Escribe el nombre del modelo a mano.")
        raise RuntimeError("El servicio respondió HTTP %d." % e.code)
    except Exception as e:
        raise RuntimeError("No se pudo conectar: %s" % getattr(e, "reason", e))
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise RuntimeError("La respuesta del servicio no es válida (¿la dirección termina en /v1?).")
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
        raise RuntimeError("No se pudo conectar: %s" % getattr(e, "reason", e))
    try:
        return (j["choices"][0]["message"].get("content") or "").strip() or "(respuesta vacía, pero el servicio contestó)"
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Respuesta inesperada del servicio.")


def saved(cfg=None):
    return list((cfg or core.SET.snapshot()).get("providers") or [])


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
    name = next((t[0] for t in TEMPLATES if t[1] and t[1].rstrip("/") == cfg["external_url"].rstrip("/")), "Servidor externo")
    p = {"id": uuid.uuid4().hex[:8], "name": name, "url": cfg["external_url"], "key": cfg.get("external_key", ""), "models": [cfg["external_model"]]}
    core.SET.update({"providers": [p], "external_provider": p["id"]})


class ProvidersDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modelos por API")
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
        t = QLabel("Servicios guardados")
        t.setObjectName("h1")
        lv.addWidget(t)
        self.lst = QListWidget()
        self.lst.setObjectName("history")
        self.lst.currentRowChanged.connect(self._pick)
        lv.addWidget(self.lst, 1)
        lv.addWidget(btn("Añadir servicio", None, self._new, "acc_anadir"))
        root.addWidget(left)
        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(22, 16, 22, 14)
        v.setSpacing(8)
        v.addWidget(lbl("Usa modelos de servicios en la nube o de tu propio servidor con tu clave de API. La clave se guarda solo en este "
                        "equipo. Las suscripciones de usuario (ChatGPT Plus, Claude Pro…) no sirven aquí: hace falta una clave de API.", "faint"))
        v.addWidget(QLabel("Servicio"))
        self.tpl = QComboBox()
        for n, u, where, _ in TEMPLATES:
            self.tpl.addItem(n, (u, where))
        self.tpl.activated.connect(self._template)
        v.addWidget(self.tpl)
        v.addWidget(QLabel("Nombre"))
        self.e_name = QLineEdit()
        v.addWidget(self.e_name)
        v.addWidget(QLabel("Dirección (termina en /v1)"))
        self.e_url = QLineEdit()
        self.e_url.setPlaceholderText("https://…/v1")
        v.addWidget(self.e_url)
        v.addWidget(QLabel("Clave de API"))
        self.e_key = QLineEdit()
        self.e_key.setEchoMode(QLineEdit.Password)
        v.addWidget(self.e_key)
        self.where = lbl("", "faint")
        v.addWidget(self.where)
        row = QHBoxLayout()
        row.addWidget(QLabel("Modelos que quieres usar"), 1)
        row.addWidget(btn("Ver modelos disponibles", None, self._fetch, "acc_refrescar"))
        v.addLayout(row)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrar o escribir un nombre de modelo y pulsar Enter para añadirlo…")
        self.filter.textChanged.connect(self._apply_filter)
        self.filter.returnPressed.connect(self._add_typed)
        v.addWidget(self.filter)
        self.models = QListWidget()
        self.models.setObjectName("history")
        v.addWidget(self.models, 1)
        self.msg = lbl("", "faint")
        v.addWidget(self.msg)
        foot = QHBoxLayout()
        self.b_del = btn("Quitar servicio", "danger", self._delete)
        foot.addWidget(self.b_del)
        foot.addStretch(1)
        foot.addWidget(btn("Probar", None, self._test))
        foot.addWidget(btn("Guardar", "primary", self._save))
        foot.addWidget(btn("Cerrar", None, self.accept))
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
        self.msg.setText("Elige el servicio, pega tu clave y pulsa «Ver modelos disponibles».")

    def _template(self, i):
        url, where = self.tpl.itemData(i)
        name = self.tpl.itemText(i).split(" (")[0]
        if self.cur is None or not self.e_name.text().strip():
            self.e_name.setText("" if not url else name)
        self.e_url.setText(url)
        self.where.setText(("Consigue tu clave en %s" % where) if where else ("No necesita clave." if url.startswith("http://127.") else ""))

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
        self.msg.setText("Consultando los modelos del servicio…")

        def done(r):
            if isinstance(r, Exception):
                return self.msg.setText("✗ %s" % r)
            self._set_models(r, self._checked())
            self.msg.setText("✓ %d modelos disponibles. Marca los que quieras tener en el menú." % len(r))
        run_bg(lambda: list_models(url, key), done)

    def _test(self):
        url, key = self.e_url.text().strip(), self.e_key.text().strip()
        models = self._checked()
        if not models:
            return self.msg.setText("Marca al menos un modelo para probarlo.")
        self.msg.setText("Probando %s…" % models[0])

        def done(r):
            self.msg.setText(("✗ %s" % r) if isinstance(r, Exception) else "✓ %s responde: %s" % (models[0], str(r)[:120]))
        run_bg(lambda: test_chat(url, key, models[0]), done)

    # ---- guardar / quitar
    def _save(self):
        name, url = self.e_name.text().strip(), self.e_url.text().strip().rstrip("/")
        models = self._checked()
        if not name or not url.lower().startswith(("http://", "https://")):
            return self.msg.setText("Escribe un nombre y una dirección que empiece por http:// o https://")
        if not models:
            return self.msg.setText("Marca al menos un modelo (pulsa «Ver modelos disponibles» o escribe su nombre y Enter).")
        ps = saved()
        p = next((x for x in ps if x["id"] == self.cur), None)
        if p is None:
            p = {"id": uuid.uuid4().hex[:8]}
            ps.append(p)
        p.update({"name": name, "url": url, "key": self.e_key.text().strip(), "models": models})
        core.SET.update({"providers": ps})
        self.cur = p["id"]
        cfg = core.SET.snapshot()
        if cfg.get("external_provider") == p["id"] and cfg["llm_mode"] == "external":     # el activo cambió de clave o dirección
            core.SET.update({"external_url": url, "external_key": p["key"],
                             "external_model": cfg["external_model"] if cfg["external_model"] in models else models[0]})
        self._reload(p["id"])
        self.b_del.show()
        self.msg.setText("✓ Guardado. Sus modelos ya aparecen en el menú de modelos.")

    def _delete(self):
        p = next((x for x in saved() if x["id"] == self.cur), None)
        if not p or QMessageBox.question(self, "Quitar servicio", "¿Quitar «%s» y su clave de este equipo?" % p["name"]) != QMessageBox.StandardButton.Yes:
            return
        core.SET.update({"providers": [x for x in saved() if x["id"] != p["id"]]})
        self._reload()
        if self.lst.count():
            self.lst.setCurrentRow(0)
        else:
            self._new()
