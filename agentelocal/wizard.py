"""Asistente de configuracion, gestor de modelos y ajustes (ventanas de dialogo)."""
import os, re, shutil, threading, urllib.request
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel, QPushButton, QRadioButton,
                               QButtonGroup, QStackedWidget, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QAbstractItemView,
                               QHeaderView, QCheckBox, QSpinBox, QDoubleSpinBox, QFileDialog, QProgressBar, QMessageBox, QPlainTextEdit,
                               QTabWidget, QScrollArea, QFrame)
from . import core, paths, hardware as HW, provision as P, agent as A
from .theme import C, restyle, icon
from PySide6.QtCore import QSize

# ---------------------------------------------------------------- utilidades
_bridges = []


class _Bridge(QObject):
    done = Signal(object)


def run_bg(fn, cb):
    """Ejecuta fn() en un hilo y entrega el resultado (o la excepcion) a cb en el hilo de la interfaz."""
    b = _Bridge()
    _bridges.append(b)

    def finish(r):
        _bridges.remove(b)
        cb(r)
    b.done.connect(finish)

    def work():
        try:
            r = fn()
        except Exception as e:
            r = e
        b.done.emit(r)
    threading.Thread(target=work, daemon=True).start()


def btn(text, kind=None, cb=None, ico=None):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if cb:
        b.clicked.connect(cb)
    if ico:
        set_icon(b, ico)
    return b


def set_icon(b, ico):
    dark = b.property("kind") in ("primary", "ok", "danger")
    b.setIcon(icon(ico, "#0b1020" if dark else C["tx"], 16))
    b.setIconSize(QSize(16, 16))


def lbl(text="", name=None, wrap=True):
    l = QLabel(text)
    l.setWordWrap(wrap)
    l.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if name:
        l.setObjectName(name)
    return l


def browse_row(edit, folder=False, filt="Modelos GGUF (*.gguf);;Todos (*.*)", parent=None):
    row = QHBoxLayout()
    row.addWidget(edit, 1)

    def pick():
        if folder:
            p = QFileDialog.getExistingDirectory(parent, "Elegir carpeta", edit.text() or os.path.expanduser("~"))
        else:
            p, _ = QFileDialog.getOpenFileName(parent, "Elegir archivo", os.path.dirname(edit.text()) or os.path.expanduser("~"), filt)
        if p:
            edit.setText(os.path.normpath(p))
    row.addWidget(btn("Examinar…", cb=pick))
    return row


FIT_TXT = {"ok": "✓ cabe", "tight": "⚠ muy justo", "no": "✗ no cabe"}
FIT_COL = {"ok": C["ok"], "tight": C["warn"], "no": C["bad"]}
BACKENDS = [("cpu", "Solo CPU (funciona en cualquier PC)"), ("cuda", "GPU NVIDIA (CUDA)"), ("vulkan", "GPU AMD / Intel Arc (Vulkan)")]


# ---------------------------------------------------------------- asistente
class SetupWizard(QDialog):
    """Primera configuracion o 'Añadir modelo'. Deja todo listo: motor, modelo y ajustes."""

    def __init__(self, parent=None, start="welcome"):
        super().__init__(parent)
        self.setWindowTitle("Asistente de configuración")
        self.resize(780, 600)
        self.cfg = core.SET.snapshot()
        self.hw = None
        self.info = None
        self.job = None
        self.start_llm = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        nav = QHBoxLayout()
        self.b_cancel = btn("Cancelar", cb=self.reject)
        self.b_back = btn("Atrás", cb=self.back)
        self.b_next = btn("Siguiente", "primary", self.next)
        nav.addWidget(self.b_cancel)
        nav.addStretch(1)
        nav.addWidget(self.b_back)
        nav.addWidget(self.b_next)
        lay.addLayout(nav)
        self.p_welcome, self.p_model, self.p_engine, self.p_progress, self.p_done = (self._welcome(), self._model(), self._engine(), self._progress(), self._done())
        for p in (self.p_welcome, self.p_model, self.p_engine, self.p_progress, self.p_done):
            self.stack.addWidget(p)
        self.timer = QTimer(self, interval=300, timeout=self._tick)
        self.history = []
        self.go(self.p_model if start == "model" else self.p_welcome, push=False)
        run_bg(HW.detect, self._got_hw)

    # --- paginas
    def _page(self, title, sub=""):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        t = lbl(title, "h1")
        v.addWidget(t)
        if sub:
            v.addWidget(lbl(sub, "muted"))
        return w, v

    def _welcome(self):
        w, v = self._page("Configuremos tu agente local",
                          "Este asistente prepara todo para usar modelos de IA en tu propio equipo: descarga el motor (llama.cpp) "
                          "adecuado a tu hardware y el modelo que elijas, y lo deja configurado. Después todo funciona sin internet.")
        v.addSpacing(8)
        v.addWidget(lbl("TU EQUIPO", "section"))
        self.hw_lbl = lbl("Detectando hardware…")
        v.addWidget(self.hw_lbl)
        v.addSpacing(8)
        v.addWidget(lbl("DÓNDE SE GUARDA", "section"))
        v.addWidget(lbl("Ajustes y conversaciones: %s\nCarpeta de trabajo del agente: %s" % (paths.HOME, self.cfg["workspace"]), "muted"))
        v.addStretch(1)
        return w

    def _model(self):
        w, v = self._page("Elige el modelo", "Puedes usar cualquier modelo en formato GGUF. Luego podrás añadir más desde «Modelos».")
        self.r_hf = QRadioButton("Descargar un modelo de Hugging Face")
        self.r_file = QRadioButton("Usar un archivo .gguf que ya tengo")
        self.r_ext = QRadioButton("Conectar a un servidor externo compatible con OpenAI (Ollama, LM Studio, otro PC…)")
        grp = QButtonGroup(w)
        for r, ico in ((self.r_hf, "acc_descargar"), (self.r_file, "act_carpeta_abierta"), (self.r_ext, "hub_conectar")):
            grp.addButton(r)
            r.setIcon(icon(ico, C["acc"], 18))
            r.setIconSize(QSize(18, 18))
            v.addWidget(r)
        self.r_hf.setChecked(True)
        self.sub = QStackedWidget()
        v.addWidget(self.sub, 1)
        # -- Hugging Face
        hf = QWidget()
        hv = QVBoxLayout(hf)
        hv.setContentsMargins(22, 4, 0, 0)
        row = QHBoxLayout()
        self.repo = QComboBox()
        self.repo.setEditable(True)
        for c in P.CATALOG:
            self.repo.addItem("%s  —  %s" % (c["repo"], c["name"]), c["repo"])
        self.repo.setToolTip("Escribe cualquier repositorio GGUF, por ejemplo usuario/Modelo-GGUF")
        row.addWidget(self.repo, 1)
        row.addWidget(btn("Ver archivos", cb=self.load_repo))
        hv.addLayout(row)
        self.repo_desc = lbl("", "muted")
        hv.addWidget(self.repo_desc)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Cuantización", "Tamaño", "En tu equipo"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_disk)
        hv.addWidget(self.table, 1)
        self.chk_mm = QCheckBox("Incluir visión (permite que el modelo vea imágenes y capturas de pantalla)")
        hv.addWidget(self.chk_mm)
        self.dest = QLineEdit(self.cfg["models_dir"])
        self.dest.textChanged.connect(self._update_disk)
        hv.addWidget(lbl("Carpeta donde guardar los modelos:", "muted"))
        hv.addLayout(browse_row(self.dest, folder=True, parent=self))
        self.disk_lbl = lbl("", "muted")
        hv.addWidget(self.disk_lbl)
        self.sub.addWidget(hf)
        # -- archivo local
        lf = QWidget()
        fv = QFormLayout(lf)
        fv.setContentsMargins(22, 4, 0, 0)
        self.f_model = QLineEdit()
        self.f_mm = QLineEdit()
        self.f_mm.setPlaceholderText("opcional")
        fv.addRow("Modelo (.gguf):", browse_row(self.f_model, parent=self))
        fv.addRow("Proyector de visión (mmproj):", browse_row(self.f_mm, parent=self))
        fv.addRow(lbl("Si el modelo está dividido en varias partes, elige la primera (…-00001-of-…).", "muted"))
        self.sub.addWidget(lf)
        # -- servidor externo
        ex = QWidget()
        ev = QFormLayout(ex)
        ev.setContentsMargins(22, 4, 0, 0)
        self.e_url = QLineEdit(self.cfg["external_url"])
        self.e_model = QLineEdit(self.cfg["external_model"])
        self.e_model.setPlaceholderText("nombre del modelo en ese servidor, p. ej. qwen3:8b")
        self.e_key = QLineEdit(self.cfg["external_key"])
        self.e_key.setEchoMode(QLineEdit.Password)
        self.e_key.setPlaceholderText("vacío si no hace falta")
        self.e_res = lbl("", "muted")
        ev.addRow("URL base (/v1):", self.e_url)
        ev.addRow("Modelo:", self.e_model)
        ev.addRow("Clave API:", self.e_key)
        ev.addRow(btn("Probar conexión", cb=self.test_ext), self.e_res)
        self.sub.addWidget(ex)
        for i, r in enumerate((self.r_hf, self.r_file, self.r_ext)):
            r.toggled.connect(lambda on, i=i: on and self.sub.setCurrentIndex(i))
        return w

    def _engine(self):
        w, v = self._page("Motor de inferencia", "llama.cpp ejecuta el modelo. Se descarga la compilación oficial adecuada a tu equipo.")
        f = QFormLayout()
        self.backend = QComboBox()
        for k, t in BACKENDS:
            self.backend.addItem(t, k)
        f.addRow("Usar:", self.backend)
        self.eng_state = lbl("", "muted")
        f.addRow("", self.eng_state)
        self.chk_own = QCheckBox("Usar un llama-server.exe que ya tengo")
        self.own_exe = QLineEdit(self.cfg["llama_exe"])
        f.addRow(self.chk_own)
        own_row = QWidget()
        own_row.setLayout(browse_row(self.own_exe, filt="llama-server.exe (llama-server.exe)", parent=self))
        own_row.layout().setContentsMargins(0, 0, 0, 0)
        own_row.setEnabled(False)
        self.chk_own.toggled.connect(own_row.setEnabled)
        f.addRow("Ruta:", own_row)
        self.threads = QSpinBox()
        self.threads.setRange(1, 256)
        self.threads.setValue(self.cfg["threads"])
        f.addRow("Hilos de CPU:", self.threads)
        self.ctx = QComboBox()
        for n in (4096, 8192, 16384, 32768, 65536, 131072):
            self.ctx.addItem("%d tokens" % n, n)
        self.ctx.setCurrentIndex(max(0, self.ctx.findData(self.cfg["n_ctx"])))
        f.addRow("Contexto:", self.ctx)
        v.addLayout(f)
        v.addWidget(lbl("Más contexto permite tareas más largas, pero usa más memoria. Para agentes se recomiendan 16 000 o más.", "muted"))
        v.addStretch(1)
        self.backend.currentIndexChanged.connect(self._eng_state)
        self.chk_own.toggled.connect(self._eng_state)
        return w

    def _progress(self):
        w, v = self._page("Descargando e instalando", "Puedes cancelar: lo descargado se conserva y se reanuda después.")
        self.prog_box = QVBoxLayout()
        v.addLayout(self.prog_box)
        self.prog_err = lbl("", "err")
        self.prog_err.hide()
        v.addWidget(self.prog_err)
        v.addStretch(1)
        return w

    def _done(self):
        w, v = self._page("¡Listo!")
        self.done_lbl = lbl("")
        v.addWidget(self.done_lbl)
        self.chk_start = QCheckBox("Encender el modelo ahora")
        self.chk_start.setChecked(True)
        v.addWidget(self.chk_start)
        v.addStretch(1)
        return w

    # --- navegacion
    def go(self, page, push=True):
        if push:
            self.history.append(self.stack.currentWidget())
        self.stack.setCurrentWidget(page)
        self.b_back.setVisible(bool(self.history) and page not in (self.p_progress, self.p_done))
        self.b_next.setText({self.p_done: "Empezar"}.get(page, "Instalar" if page is self.p_engine else "Siguiente"))
        self.b_next.setEnabled(page is not self.p_progress)
        self.b_cancel.setText("Cancelar descarga" if page is self.p_progress else "Cancelar")
        self.b_cancel.setVisible(page is not self.p_done)
        if page is self.p_model and self.info is None and self.repo.count():
            self.load_repo()
        if page is self.p_engine:
            self._eng_state()

    def back(self):
        if self.history:
            self.go(self.history.pop(), push=False)

    def reject(self):
        if self.job and not self.job.finished:
            self.job.cancel()
            return
        super().reject()

    def next(self):
        page = self.stack.currentWidget()
        if page is self.p_welcome:
            self.go(self.p_model)
        elif page is self.p_model:
            self._after_model()
        elif page is self.p_engine:
            self._install()
        elif page is self.p_done:
            self.start_llm = self.chk_start.isChecked() and self.chk_start.isVisible()
            self.accept()

    # --- hardware
    def _got_hw(self, hw):
        if isinstance(hw, Exception):
            self.hw_lbl.setText("No pude detectar el hardware: %s" % hw)
            return
        self.hw = hw
        b = HW.recommend_backend(hw)
        self.hw_lbl.setText(HW.summary(hw) + "\n\nMemoria disponible para el modelo: ~%s · Motor recomendado: %s" % (
            HW.human(HW.memory_budget(hw)), dict(BACKENDS)[b]))
        if not self.cfg["setup_done"]:
            self.backend.setCurrentIndex(self.backend.findData(b))
            self.threads.setValue(hw["cores"])
        else:
            self.backend.setCurrentIndex(max(0, self.backend.findData(self.cfg["backend"])))
        if self.info:
            self._fill_table()

    # --- Hugging Face
    def _repo_text(self):
        i = self.repo.currentIndex()
        if i >= 0 and self.repo.itemText(i) == self.repo.currentText():
            return self.repo.itemData(i)
        return self.repo.currentText().split()[0].strip() if self.repo.currentText().strip() else ""

    def load_repo(self):
        repo = self._repo_text()
        if not repo:
            return
        self.repo_desc.setText("Consultando %s…" % repo)
        self.table.setRowCount(0)
        cat = next((c for c in P.CATALOG if c["repo"] == repo), None)
        run_bg(lambda: P.hf_files(repo), lambda r: self._got_repo(r, cat))

    def _got_repo(self, r, cat):
        if isinstance(r, Exception):
            self.repo_desc.setText("No pude leer el repositorio (¿sin internet o nombre incorrecto?): %s" % r)
            self.info = None
            return
        if not r["quants"]:
            self.repo_desc.setText("Ese repositorio no contiene archivos GGUF.")
            self.info = None
            return
        self.info = r
        self.repo_desc.setText((cat["desc"] + "  " if cat else "") + "%d variantes disponibles." % len(r["quants"]))
        self.chk_mm.setEnabled(bool(r["mmproj"]))
        self.chk_mm.setChecked(bool(r["mmproj"]))
        if not r["mmproj"]:
            self.chk_mm.setText("Este modelo no trae proyector de visión (solo texto)")
        else:
            self.chk_mm.setText("Incluir visión (+%s): permite que vea imágenes y capturas" % HW.human(r["mmproj"][0]["size"]))
        self._fill_table()

    def _fill_table(self):
        qs = self.info["quants"]
        rec = HW.recommend_quant(qs, self.hw) if self.hw else None
        self.table.setRowCount(len(qs))
        sel = 0
        for i, q in enumerate(qs):
            name = q["label"] + ("   ★ recomendada" if rec is q else "")
            it = QTableWidgetItem(name)
            it.setData(Qt.UserRole, i)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(HW.human(q["size"])))
            if self.hw:
                fit = HW.classify(q["size"], self.hw, self.chk_mm.isChecked())
                fi = QTableWidgetItem(FIT_TXT[fit])
                from PySide6.QtGui import QColor
                fi.setForeground(QColor(FIT_COL[fit]))
                self.table.setItem(i, 2, fi)
            if rec is q:
                sel = i
        self.table.selectRow(sel)
        self.table.scrollToItem(self.table.item(sel, 0))
        self._update_disk()

    def _selected_quant(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or not self.info:
            return None
        return self.info["quants"][rows[0].row()]

    def _update_disk(self):
        q = self._selected_quant()
        free = HW.disk_free(self.dest.text() or paths.MODELS_DEFAULT)
        need = (q["size"] if q else 0) + (self.info["mmproj"][0]["size"] if self.info and self.info["mmproj"] and self.chk_mm.isChecked() else 0)
        warn = "  ⚠ no hay espacio suficiente" if q and need > free else ""
        self.disk_lbl.setText("Necesita %s · libre en esa unidad: %s%s" % (HW.human(need), HW.human(free), warn))

    # --- externo
    def test_ext(self):
        url, key = self.e_url.text().strip().rstrip("/"), self.e_key.text().strip()
        self.e_res.setText("Probando…")

        def probe():
            import json
            req = urllib.request.Request(url + "/models", headers={"Authorization": "Bearer " + (key or "local")})
            d = json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))
            return [m.get("id") for m in d.get("data", [])]

        def done(r):
            if isinstance(r, Exception):
                self.e_res.setText("✗ No responde: %s" % r)
            else:
                self.e_res.setText("✓ Conectado. Modelos: %s" % (", ".join(r[:8]) or "(ninguno listado)"))
                if r and not self.e_model.text().strip():
                    self.e_model.setText(r[0])
        run_bg(probe, done)

    # --- tras elegir modelo
    def _after_model(self):
        if self.r_ext.isChecked():
            if not self.e_url.text().strip():
                return QMessageBox.warning(self, "Falta la URL", "Escribe la URL del servidor.")
            core.SET.update({"llm_mode": "external", "external_url": self.e_url.text().strip(), "external_model": self.e_model.text().strip(),
                             "external_key": self.e_key.text().strip(), "setup_done": True})
            self.done_lbl.setText("Usarás el servidor %s. Asegúrate de que esté encendido antes de chatear." % self.e_url.text().strip())
            self.chk_start.hide()
            return self.go(self.p_done)
        if self.r_file.isChecked():
            if not os.path.isfile(self.f_model.text()):
                return QMessageBox.warning(self, "Archivo no encontrado", "Elige un archivo .gguf existente.")
            if self.f_mm.text() and not os.path.isfile(self.f_mm.text()):
                return QMessageBox.warning(self, "Archivo no encontrado", "El proyector de visión indicado no existe.")
        elif self._selected_quant() is None:
            return QMessageBox.warning(self, "Elige una variante", "Pulsa «Ver archivos» y elige una cuantización de la lista.")
        self.go(self.p_engine)

    def _llama_ok(self):
        b = self.backend.currentData()
        return os.path.isfile(self.cfg["llama_exe"]) and self.cfg["backend"] == b

    def _eng_state(self):
        if self.chk_own.isChecked():
            self.eng_state.setText("Se usará tu llama-server.exe.")
        elif self._llama_ok():
            self.eng_state.setText("✓ Ya instalado (%s). No hace falta descargarlo." % (self.cfg["llama_tag"] or "versión local"))
        else:
            self.eng_state.setText("Se descargará la última versión oficial desde GitHub (ggml-org/llama.cpp).")

    # --- instalacion
    def _install(self):
        backend = self.backend.currentData()
        if self.chk_own.isChecked() and not os.path.isfile(self.own_exe.text()):
            return QMessageBox.warning(self, "Archivo no encontrado", "Elige un llama-server.exe existente.")
        job = P.Job()
        if self.chk_own.isChecked():
            exe = self.own_exe.text()
            job.add("Motor: usar llama-server existente", lambda pr, st, res: res.update(llama_exe=exe, llama_tag="propio"))
        elif self._llama_ok():
            job.add("Motor: ya instalado", lambda pr, st, res: res.update(llama_exe=self.cfg["llama_exe"], llama_tag=self.cfg["llama_tag"]))
        else:
            job.add("Motor llama.cpp (%s)" % dict(BACKENDS)[backend], lambda pr, st, res: self._job_llama(backend, pr, st, res))
        if self.r_hf.isChecked():
            q, info = self._selected_quant(), self.info
            folder = os.path.join(self.dest.text() or paths.MODELS_DEFAULT, info["repo"].replace("/", "__"))
            for k, part in enumerate(q["parts"]):
                job.add("Modelo %s%s" % (q["label"], " parte %d/%d" % (k + 1, len(q["parts"])) if len(q["parts"]) > 1 else ""),
                        lambda pr, st, res, part=part: P.download(P.hf_url(info["repo"], part["file"]), os.path.join(folder, os.path.basename(part["file"])),
                                                                  part["size"], part["sha256"], pr, st))
            mm = info["mmproj"][0] if info["mmproj"] and self.chk_mm.isChecked() else None
            if mm:
                job.add("Proyector de visión", lambda pr, st, res: P.download(P.hf_url(info["repo"], mm["file"]), os.path.join(folder, os.path.basename(mm["file"])),
                                                                               mm["size"], mm["sha256"], pr, st))
            name = re.sub(r"-GGUF$", "", info["repo"].split("/")[-1], flags=re.I)
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", info["repo"] + "_" + q["label"]), "name": "%s · %s" % (name, quant_short(q["label"])),
                                  "path": os.path.join(folder, os.path.basename(q["parts"][0]["file"])),
                                  "mmproj": os.path.join(folder, os.path.basename(mm["file"])) if mm else "",
                                  "repo": info["repo"], "file": q["file"], "size": q["size"]}
        else:
            p = os.path.normpath(self.f_model.text())
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", "local_" + os.path.basename(p)), "name": os.path.splitext(os.path.basename(p))[0],
                                  "path": p, "mmproj": os.path.normpath(self.f_mm.text()) if self.f_mm.text() else "", "repo": "", "file": "",
                                  "size": os.path.getsize(p)}
        self.pending_cfg = {"backend": "cpu" if self.chk_own.isChecked() and backend == "cpu" else backend, "threads": self.threads.value(),
                            "n_ctx": self.ctx.currentData(), "models_dir": self.dest.text() or paths.MODELS_DEFAULT}
        self._start_job(job)

    def _job_llama(self, backend, pr, st, res):
        rel = P.llama_release(backend)
        dl = os.path.join(paths.RUNTIME_DIR, "downloads")
        target = os.path.join(paths.RUNTIME_DIR, "llama-%s-%s" % (rel["tag"], backend))
        total = sum(a["size"] for a in rel["assets"])
        base = 0
        for a in rel["assets"]:
            z = os.path.join(dl, a["name"])
            P.download(a["url"], z, a["size"], a["sha256"], lambda d, t, ph, b=base: pr(b + d, total, ph), st)
            base += a["size"]
            pr(base, total, "descomprimiendo")
            P.extract_zip(z, target)
        exe = P.find_server(target)
        if not exe:
            raise RuntimeError("El paquete de llama.cpp no contiene llama-server.exe")
        res.update(llama_exe=exe, llama_tag=rel["tag"])
        try:
            shutil.rmtree(dl)
        except OSError:
            pass

    def _start_job(self, job):
        self.job = job
        while self.prog_box.count():
            it = self.prog_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.rows = []
        for st in job.steps:
            w = QWidget()
            g = QGridLayout(w)
            g.setContentsMargins(0, 4, 0, 4)
            name = lbl(st["label"])
            bar = QProgressBar()
            bar.setRange(0, 1000)
            det = lbl("en espera", "muted")
            g.addWidget(name, 0, 0)
            g.addWidget(det, 0, 1, Qt.AlignRight)
            g.addWidget(bar, 1, 0, 1, 2)
            self.prog_box.addWidget(w)
            self.rows.append((bar, det))
        self.prog_err.hide()
        self.go(self.p_progress)
        job.start()
        self.timer.start()

    def _tick(self):
        j = self.job
        for st, (bar, det) in zip(j.steps, self.rows):
            if st["total"]:
                bar.setValue(int(1000 * st["done"] / max(1, st["total"])))
            if st["status"] == "done":
                bar.setValue(1000)
                det.setText("✓ listo")
            elif st["status"] == "running":
                sp = st["speed"]
                eta = ""
                if sp > 0 and st["total"]:
                    s = (st["total"] - st["done"]) / sp
                    eta = " · quedan %dm %02ds" % (s // 60, s % 60)
                det.setText("%s %s / %s%s%s" % (st["phase"], HW.human(st["done"]), HW.human(st["total"]),
                                                 (" · %s/s" % HW.human(sp)) if sp else "", eta))
            elif st["status"] in ("error", "cancelled"):
                det.setText("✗ " + ("cancelado" if st["status"] == "cancelled" else "error"))
        if j.finished:
            self.timer.stop()
            if j.error:
                self.prog_err.setText(j.error)
                self.prog_err.show()
                self.b_next.setText("Reintentar")
                self.b_next.setEnabled(True)
                self.b_next.clicked.disconnect()
                self.b_next.clicked.connect(self._retry)
                self.b_cancel.setText("Cerrar")
                self.job = None
            else:
                self._finish(j.result)

    def _retry(self):
        self.b_next.clicked.disconnect()
        self.b_next.clicked.connect(self.next)
        self._install()

    def _finish(self, res):
        core.SET.update(dict(self.pending_cfg, llama_exe=res["llama_exe"], llama_tag=res.get("llama_tag", ""), llm_mode="local", setup_done=True))
        core.SET.add_model(self.pending_model, activate=True)
        self.done_lbl.setText("Modelo «%s» instalado y activo.\n\nArchivo: %s%s\nMotor: %s (%s)" % (
            self.pending_model["name"], self.pending_model["path"],
            ("\nVisión: " + self.pending_model["mmproj"]) if self.pending_model["mmproj"] else "",
            dict(BACKENDS)[self.pending_cfg["backend"]], res.get("llama_tag") or "local"))
        self.history.clear()
        self.go(self.p_done, push=False)


def quant_short(label):
    return label.replace("   ★ recomendada", "")


# ---------------------------------------------------------------- gestor de modelos
class ModelsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modelos")
        self.resize(760, 420)
        v = QVBoxLayout(self)
        v.addWidget(lbl("Modelos instalados", "h1"))
        v.addWidget(lbl("El modelo activo es el que usa el agente. Cambiarlo apaga el modelo actual.", "muted"))
        self.t = QTableWidget(0, 4)
        self.t.setHorizontalHeaderLabels(["", "Nombre", "Tamaño", "Archivo"])
        self.t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.t.verticalHeader().setVisible(False)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t.setSelectionMode(QAbstractItemView.SingleSelection)
        self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t.doubleClicked.connect(self.activate)
        v.addWidget(self.t, 1)
        row = QHBoxLayout()
        row.addWidget(btn("Usar este", "primary", self.activate, "ui_check"))
        row.addWidget(btn("Añadir modelo…", cb=self.add, ico="acc_anadir"))
        row.addWidget(btn("Abrir carpeta", cb=self.open_folder, ico="act_carpeta_abierta"))
        row.addStretch(1)
        row.addWidget(btn("Quitar de la lista", cb=lambda: self.remove(False), ico="ui_cerrar"))
        row.addWidget(btn("Borrar archivos…", "danger", lambda: self.remove(True), "acc_eliminar"))
        row.addWidget(btn("Cerrar", cb=self.accept))
        v.addLayout(row)
        self.changed = False
        self.refresh()

    def refresh(self):
        cfg = core.SET.snapshot()
        ms = cfg["models"]
        self.t.setRowCount(len(ms))
        for i, m in enumerate(ms):
            ok = os.path.isfile(m.get("path", ""))
            self.t.setItem(i, 0, QTableWidgetItem("●" if m["id"] == cfg["active_model"] else ""))
            self.t.setItem(i, 1, QTableWidgetItem(m["name"] + ("" if ok else "  (archivo no encontrado)")))
            self.t.setItem(i, 2, QTableWidgetItem(HW.human(m.get("size", 0))))
            self.t.setItem(i, 3, QTableWidgetItem(m.get("path", "")))
        self.t.resizeColumnToContents(0)
        self.t.resizeColumnToContents(1)

    def _sel(self):
        rows = self.t.selectionModel().selectedRows()
        ms = core.SET.snapshot()["models"]
        return ms[rows[0].row()] if rows and rows[0].row() < len(ms) else None

    def activate(self):
        m = self._sel()
        if m:
            core.LLM_MGR.stop()
            core.SET.update({"active_model": m["id"], "llm_mode": "local"})
            self.changed = True
            self.refresh()

    def add(self):
        w = SetupWizard(self, start="model")
        if w.exec():
            self.changed = True
            if w.start_llm:
                core.LLM_MGR.stop()
                core.LLM_MGR.start()
        self.refresh()

    def open_folder(self):
        m = self._sel()
        p = os.path.dirname(m["path"]) if m else core.SET.snapshot()["models_dir"]
        if os.path.isdir(p):
            os.startfile(p)

    def remove(self, delete_files):
        m = self._sel()
        if not m:
            return
        if delete_files:
            files = [f for f in (m.get("path"), m.get("mmproj")) if f and os.path.isfile(f)]
            folder = os.path.dirname(m.get("path", ""))
            if m.get("path") and re.search(r"-00001-of-\d{5}\.gguf$", m["path"]):
                pre = re.sub(r"-00001-of-(\d{5})\.gguf$", "", os.path.basename(m["path"]))
                files = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith(pre)] + files[1:]
            if not files:
                return QMessageBox.information(self, "Sin archivos", "No hay archivos que borrar; solo se quitará de la lista.")
            txt = "Se borrarán permanentemente %d archivo(s) (%s):\n\n%s\n\nNo se puede deshacer. ¿Continuar?" % (
                len(files), HW.human(sum(os.path.getsize(f) for f in files)), "\n".join(files))
            if QMessageBox.question(self, "Borrar archivos del modelo", txt) != QMessageBox.StandardButton.Yes:
                return
            if m["id"] == core.SET.snapshot()["active_model"]:
                core.LLM_MGR.stop()
            for f in files:
                try:
                    os.remove(f)
                except OSError as e:
                    QMessageBox.warning(self, "No se pudo borrar", str(e))
        core.SET.remove_model(m["id"])
        self.changed = True
        self.refresh()


# ---------------------------------------------------------------- ajustes
class SettingsDialog(QDialog):
    FIELDS = {
        "General": [("user_name", "Tu nombre", "text"), ("theme", "Tema", "theme"), ("workspace", "Carpeta de trabajo", "dir"),
                    ("custom_instructions", "Instrucciones personalizadas", "area"),
                    ("brave_key", "Clave de Brave Search (búsqueda web completa)", "secret"), ("vision", "Enviar capturas e imágenes al modelo", "bool")],
        "Modelo": [("llm_mode", "Proveedor", "provider"), ("external_url", "URL externa (/v1)", "text"), ("external_model", "Modelo externo", "text"),
                   ("external_key", "Clave API externa", "secret"), ("threads", "Hilos de CPU", "int"), ("n_ctx", "Contexto (tokens)", "int"),
                   ("llm_port", "Puerto local", "int"), ("llama_exe", "llama-server.exe", "file")],
        "Avanzado": [("max_tokens", "Máx. tokens por respuesta", "int"), ("max_steps", "Máx. pasos por tarea", "int"), ("temperature", "Temperatura", "float"),
                     ("top_p", "Top-p", "float"), ("top_k", "Top-k", "int"), ("keep_images", "Imágenes recientes enviadas al modelo", "int"),
                     ("max_tool_output", "Máx. caracteres de salida por herramienta", "int")],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.resize(680, 560)
        cfg = core.SET.snapshot()
        v = QVBoxLayout(self)
        tabs = QTabWidget()
        v.addWidget(tabs, 1)
        self.w = {}
        for tab, fields in self.FIELDS.items():
            page = QWidget()
            f = QFormLayout(page)
            for k, label, kind in fields:
                val = cfg[k]
                if kind == "bool":
                    e = QCheckBox(label)
                    e.setChecked(bool(val))
                    f.addRow(e)
                elif kind == "area":
                    e = QPlainTextEdit(str(val))
                    e.setFixedHeight(110)
                    f.addRow(label + ":", e)
                elif kind == "int":
                    e = QSpinBox()
                    e.setRange(0, 10_000_000)
                    e.setValue(int(val))
                    f.addRow(label + ":", e)
                elif kind == "float":
                    e = QDoubleSpinBox()
                    e.setRange(0, 2)
                    e.setSingleStep(0.05)
                    e.setValue(float(val))
                    f.addRow(label + ":", e)
                elif kind in ("provider", "theme"):
                    e = QComboBox()
                    opts = ([("Local (llama.cpp en este equipo)", "local"), ("Servidor externo compatible con OpenAI", "external")] if kind == "provider"
                            else [("Según el sistema", "system"), ("Oscuro", "dark"), ("Claro", "light")])
                    for t, d in opts:
                        e.addItem(t, d)
                    e.setCurrentIndex(max(0, e.findData(val)))
                    f.addRow(label + ":", e)
                else:
                    e = QLineEdit(str(val))
                    if kind == "secret":
                        e.setEchoMode(QLineEdit.Password)
                    if kind in ("dir", "file"):
                        f.addRow(label + ":", browse_row(e, folder=kind == "dir", filt="llama-server.exe (llama-server.exe)", parent=self))
                    else:
                        f.addRow(label + ":", e)
                self.w[k] = (e, kind)
            if tab == "Modelo":
                f.addRow(lbl("Motor actual: %s · %s" % (dict(BACKENDS).get(cfg["backend"], cfg["backend"]), cfg["llama_tag"] or "—"), "muted"))
                f.addRow(btn("Asistente de configuración…", cb=self.wizard, ico="vfx_magia"))
            tabs.addTab(page, icon({"General": "acc_ajustes", "Modelo": "ia_controlador", "Avanzado": "acc_preajustes"}[tab], C["mut"], 16), tab)
        log = QWidget()
        lv = QVBoxLayout(log)
        self.log = QPlainTextEdit(core.LLM_MGR.tail(200) or "(vacío)")
        self.log.setReadOnly(True)
        self.log.setObjectName("mono")
        lv.addWidget(self.log)
        lv.addWidget(lbl("Comando: " + " ".join(core.LLM_MGR.command()), "muted"))
        tabs.addTab(log, icon("pan_consola", C["mut"], 16), "Registro del modelo")
        row = QHBoxLayout()
        row.addWidget(lbl("Datos en: " + paths.HOME, "muted"))
        row.addStretch(1)
        row.addWidget(btn("Cancelar", cb=self.reject))
        row.addWidget(btn("Guardar", "primary", self.save))
        v.addLayout(row)
        self.ran_wizard = False

    def wizard(self):
        w = SetupWizard(self, start="welcome")
        if w.exec():
            self.ran_wizard = True
            if w.start_llm:
                core.LLM_MGR.stop()
                core.LLM_MGR.start()
            self.accept()

    def save(self):
        out = {}
        for k, (e, kind) in self.w.items():
            if kind == "bool":
                out[k] = e.isChecked()
            elif kind == "area":
                out[k] = e.toPlainText()
            elif kind in ("int", "float"):
                out[k] = e.value()
            elif kind in ("provider", "theme"):
                out[k] = e.currentData()
            else:
                out[k] = e.text()
        core.SET.update(out)
        self.accept()
