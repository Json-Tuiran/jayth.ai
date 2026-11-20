"""Asistente de configuracion, gestor de modelos y ajustes (ventanas de dialogo)."""
import os, re, time, shutil, threading, urllib.request
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel, QPushButton, QRadioButton,
                               QButtonGroup, QStackedWidget, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QAbstractItemView,
                               QHeaderView, QCheckBox, QSpinBox, QDoubleSpinBox, QFileDialog, QProgressBar, QMessageBox, QPlainTextEdit,
                               QTabWidget, QScrollArea, QFrame)
from . import core, paths, osys, hardware as HW, provision as P, agent as A, convert as CV
from .theme import C, restyle, icon
from .widgets import fit_to_screen, scrollable
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
        if b in _bridges:
            _bridges.remove(b)
        try:
            cb(r)
        except RuntimeError:          # la ventana que esperaba el resultado ya se cerró
            pass
    b.done.connect(finish)

    def work():
        try:
            r = fn()
        except Exception as e:
            r = e
        try:
            b.done.emit(r)
        except RuntimeError:          # la aplicación se está cerrando
            pass
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
_BACKEND_NAMES = {"cpu": "Solo CPU (funciona en cualquier equipo)", "cuda": "GPU NVIDIA (CUDA)", "vulkan": "GPU AMD / Intel Arc (Vulkan)",
                  "metal": "GPU de Apple (Metal)"}
BACKENDS = [(k, _BACKEND_NAMES[k]) for k in ("metal", "cuda", "vulkan", "cpu") if k in P.LLAMA_PATTERNS]
SERVER_EXE = osys.exe("llama-server")


# ---------------------------------------------------------------- asistente
class SetupWizard(QDialog):
    """Primera configuracion o 'Añadir modelo'. Deja todo listo: motor, modelo y ajustes."""

    def __init__(self, parent=None, start="welcome", repo=None):
        super().__init__(parent)
        self.preset_repo = repo           # p. ej. al pulsar «Ver» en el aviso de un modelo nuevo
        self.setWindowTitle("Asistente de configuración")
        fit_to_screen(self, 940, 720, parent)
        self.cfg = core.SET.snapshot()
        self.hw = None
        self.info = None
        self.job = None
        self.start_llm = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        self.stack = QStackedWidget()
        # las páginas se desplazan si no caben (pantallas de poca altura); los botones de abajo siempre quedan a la vista
        lay.addWidget(scrollable(self.stack), 1)
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
        self.r_file = QRadioButton("Usar un modelo que ya tengo (GGUF, original de Hugging Face, Ollama o LM Studio)")
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
        hv.setSpacing(6)
        # catalogo: modelos abiertos de todos los laboratorios, marcados segun este equipo
        frow = QHBoxLayout()
        self.cat_search = QLineEdit()
        self.cat_search.setPlaceholderText("Buscar modelo o laboratorio (Gemma, DeepSeek, Mistral, Llama…)")
        self.cat_search.setClearButtonEnabled(True)
        self.cat_search.textChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_search, 1)
        # tipo de modelo (qué sabe hacer) y si va bien en este equipo: dos filtros independientes
        self.cat_kind = QComboBox()
        for t, k, tip in (("Todos los tipos", "all", ""),
                          ("Agéntico (usa herramientas)", "agent", "Sabe llamar a herramientas: lo que necesita el agente de Jayth para trabajar con archivos, comandos y la web."),
                          ("Multimodal (ve imágenes)", "multi", "Entiende imágenes (y algunos también audio): capturas, fotos, documentos escaneados…"),
                          ("Uso general", "general", "Para conversar, escribir, resumir y responder (sin los modelos solo de programación)."),
                          ("Programación", "code", "Especializados en escribir y revisar código."),
                          ("Razonamiento", "reason", "Piensan antes de responder: mejores en problemas de varios pasos, algo más lentos.")):
            self.cat_kind.addItem(t, k)
            if tip:
                self.cat_kind.setItemData(self.cat_kind.count() - 1, tip, Qt.ToolTipRole)
        self.cat_kind.setToolTip("Qué sabe hacer el modelo")
        self.cat_kind.currentIndexChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_kind)
        self.cat_filter = QComboBox()
        for t, k in (("Todos (caben o no)", "all"), ("Caben en tu equipo", "fit"), ("Rápidos en tu equipo", "fast")):
            self.cat_filter.addItem(t, k)
        self.cat_filter.setToolTip("Según la memoria y la velocidad de tu equipo")
        self.cat_filter.currentIndexChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_filter)
        self.cat_lab = QComboBox()
        self.cat_lab.addItem("Todos los laboratorios", "")
        self.cat_lab.currentIndexChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_lab)
        hv.addLayout(frow)
        self.cat_table = QTableWidget(0, 6)
        self.cat_table.setHorizontalHeaderLabels(["Modelo", "Tipo", "Laboratorio", "Descarga", "Velocidad aprox.", "En tu equipo"])
        self.cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            self.cat_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.cat_table.verticalHeader().setVisible(False)
        self.cat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cat_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cat_table.setMinimumHeight(190)
        self.cat_table.itemSelectionChanged.connect(self._cat_selected)
        hv.addWidget(self.cat_table, 2)
        orow = QHBoxLayout()
        orow.addWidget(lbl("¿Otro? Repositorio de Hugging Face:", "muted"))
        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText("usuario/Modelo-GGUF")
        self.repo_edit.returnPressed.connect(lambda: self.load_repo(self.repo_edit.text().strip()))
        orow.addWidget(self.repo_edit, 1)
        orow.addWidget(btn("Ver", cb=lambda: self.load_repo(self.repo_edit.text().strip())))
        hv.addLayout(orow)
        self.repo_desc = lbl("", "muted")
        hv.addWidget(self.repo_desc)
        self.catalog, self.cur_repo = None, ""
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Cuantización", "Tamaño", "En tu equipo"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_disk)
        self.table.setMinimumHeight(120)
        hv.addWidget(lbl("Variante (versión más ligera o más fiel del modelo):", "muted"))
        hv.addWidget(self.table, 1)
        self.chk_orig = QCheckBox()
        self.chk_orig.hide()
        self.chk_orig.toggled.connect(self._toggle_original)
        self.base_repo = None
        hv.addWidget(self.chk_orig)
        self.chk_del_orig = QCheckBox("Borrar el original descargado al terminar la conversión (libera espacio)")
        self.chk_del_orig.setChecked(True)
        self.chk_del_orig.hide()
        hv.addWidget(self.chk_del_orig)
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
        self.f_model.setPlaceholderText("archivo .gguf, o carpeta del modelo original (config.json + .safetensors)")
        self.f_model.textChanged.connect(self._detect_local)
        self.f_mm = QLineEdit()
        self.f_mm.setPlaceholderText("opcional")
        mrow = QHBoxLayout()
        mrow.addWidget(self.f_model, 1)
        mrow.addWidget(btn("Archivo…", cb=self._pick_file))
        mrow.addWidget(btn("Carpeta…", cb=self._pick_folder))
        self.found = QComboBox()
        self.found.addItem("Buscando modelos de Ollama y LM Studio…", None)
        self.found.activated.connect(self._use_found)
        fv.addRow("Encontrados:", self.found)
        fv.addRow("Modelo:", mrow)
        self.f_info = lbl("", "muted")
        fv.addRow("", self.f_info)
        self.f_quant = QComboBox()
        self.f_quant.currentIndexChanged.connect(self._local_space)
        self.f_quant_row = QWidget()
        qr = QHBoxLayout(self.f_quant_row)
        qr.setContentsMargins(0, 0, 0, 0)
        qr.addWidget(self.f_quant, 1)
        fv.addRow("Convertir a:", self.f_quant_row)
        self.f_quant_row.setVisible(False)
        self.f_mm_row = QWidget()
        mmr = browse_row(self.f_mm, parent=self)
        mmr.setContentsMargins(0, 0, 0, 0)
        self.f_mm_row.setLayout(mmr)
        fv.addRow("Proyector de visión (mmproj):", self.f_mm_row)
        fv.addRow(lbl("Un modelo original se convierte a GGUF en tu equipo con las herramientas oficiales de llama.cpp "
                      "(se preparan una sola vez). Tu carpeta original no se modifica.", "muted"))
        self.local = {}
        self.sub.addWidget(lf)
        run_bg(CV.other_apps_models, self._got_found)
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
        self.chk_own = QCheckBox("Usar un %s que ya tengo" % SERVER_EXE)
        self.own_exe = QLineEdit(self.cfg["llama_exe"])
        f.addRow(self.chk_own)
        own_row = QWidget()
        own_row.setLayout(browse_row(self.own_exe, filt=("%s (%s)" % (SERVER_EXE, SERVER_EXE)) if osys.WIN else "", parent=self))
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
        if page is self.p_model and self.catalog is None:
            self.load_catalog()
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
        if self.catalog:
            self._rate_catalog()

    # --- catalogo de modelos (todos los laboratorios)
    def load_catalog(self, refresh=False):
        self.catalog = []
        self.repo_desc.setText("Buscando modelos abiertos publicados en Hugging Face…")
        run_bg(lambda: P.catalog(os.path.join(paths.DATA, "catalog.json"), refresh=refresh), self._got_catalog)

    def _got_catalog(self, cat):
        if isinstance(cat, Exception) or not cat:
            self.repo_desc.setText("No pude leer el catálogo (¿sin internet?). Escribe un repositorio a mano.")
            return
        self.catalog = cat
        labs = sorted({e["lab"] for e in cat}, key=lambda l: (l == "Otros", l.lower()))
        self.cat_lab.blockSignals(True)
        for l in labs:
            self.cat_lab.addItem(l, l)
        self.cat_lab.blockSignals(False)
        self._rate_catalog(select=True)

    def _rate_catalog(self, select=False):
        if not self.catalog:
            return
        hw = self.hw or {"ram": 16 * HW.GB, "vram": 0, "unified": False}
        self.rated = HW.rate_models(self.catalog, hw, vision=True)
        self.rec_model = HW.recommend_model(self.rated) if self.hw else None
        self._fill_catalog()
        if select or not self.cur_repo:
            want = self.preset_repo or (self.rec_model["repo"] if self.rec_model else None)
            if want and not self._select_repo(want):
                self.repo_edit.setText(want)
                self.load_repo(want)

    def _select_repo(self, repo):
        for i in range(self.cat_table.rowCount()):
            it = self.cat_table.item(i, 0)
            if it and it.data(Qt.UserRole) == repo:
                self.cat_table.selectRow(i)
                self.cat_table.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                return True
        return False

    def _fill_catalog(self):
        if not getattr(self, "rated", None):
            return
        q = self.cat_search.text().strip().lower()
        flt, lab, kind = self.cat_filter.currentData(), self.cat_lab.currentData(), self.cat_kind.currentData()
        rec = self.rec_model
        order = {"ok": 0, "tight": 1, "no": 2}
        rows = []
        for e in self.rated:
            if q and q not in (e["name"] + " " + e["lab"] + " " + e["repo"]).lower():
                continue
            if lab and e["lab"] != lab:
                continue
            if (flt == "fit" and e["fit"] == "no") or (flt == "fast" and (e["fit"] == "no" or e["speed"] < 3)) or not P.matches_kind(e, kind):
                continue
            rows.append(e)
        rows.sort(key=lambda e: (e is not rec, order[e["fit"]], -HW.capability(e)))
        from PySide6.QtGui import QColor
        self.cat_table.blockSignals(True)
        self.cat_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            name = e["name"] + ("   ★ recomendado" if e is rec else "")
            it = QTableWidgetItem(name)
            it.setData(Qt.UserRole, e["repo"])
            tip = ["%s · %s" % (e["repo"], e["lab"]), "%.1f mil millones de parámetros" % (e["params"] / 1e9)]
            if e["active"] < e["params"] * 0.6:
                tip.append("MoE: usa ~%.1f mil millones por palabra (por eso va más rápido de lo que su tamaño sugiere)" % (e["active"] / 1e9))
            if e.get("ctx"):
                tip.append("Contexto máximo: %s tokens" % format(int(e["ctx"]), ",").replace(",", "."))
            if e.get("tools"):
                tip.append("Agéntico: sabe usar herramientas (archivos, comandos, web…), como necesita el agente de Jayth")
            elif "tools" in e:
                tip.append("No usa herramientas: sirve para conversar, pero el agente no podrá actuar con él")
            if e["tags"]:
                tip.append("Destaca en: " + ", ".join(e["tags"]))
            it.setToolTip("\n".join(tip))
            self.cat_table.setItem(i, 0, it)
            ki = QTableWidgetItem(P.kind_text(e))
            ki.setForeground(QColor(C["acc"] if e.get("tools") else C["mut"]))
            ki.setToolTip("Agente = usa herramientas · Visión = entiende imágenes · Razona = piensa antes de responder")
            self.cat_table.setItem(i, 1, ki)
            self.cat_table.setItem(i, 2, QTableWidgetItem(e["lab"]))
            self.cat_table.setItem(i, 3, QTableWidgetItem(HW.human(e["size"])))
            sp = e["speed"]
            st = QTableWidgetItem(("~%.0f tok/s" % sp) if sp >= 10 else ("~%.1f tok/s" % sp) if sp >= 0.1 else "—")
            st.setToolTip("Velocidad aproximada al escribir la respuesta en este equipo (estimación).")
            self.cat_table.setItem(i, 4, st)
            if self.hw:
                fi = QTableWidgetItem(FIT_TXT[e["fit"]])
                fi.setForeground(QColor(FIT_COL[e["fit"]]))
                self.cat_table.setItem(i, 5, fi)
        self.cat_table.blockSignals(False)
        if self.cur_repo:
            self.cat_table.blockSignals(True)
            self._select_repo(self.cur_repo)
            self.cat_table.blockSignals(False)
        n_ok = sum(e["fit"] == "ok" for e in self.rated)
        if not self.cur_repo:
            self.repo_desc.setText("%d modelos de %d laboratorios · %d caben en tu equipo." % (len(self.rated), len({e["lab"] for e in self.rated}), n_ok))

    def _cat_selected(self):
        rows = self.cat_table.selectionModel().selectedRows()
        if rows:
            repo = self.cat_table.item(rows[0].row(), 0).data(Qt.UserRole)
            if repo and repo != self.cur_repo:
                self.load_repo(repo)

    # --- Hugging Face
    def _repo_text(self):
        return self.cur_repo

    def load_repo(self, repo=None, keep_choice=False):
        repo = (repo or self.cur_repo or "").strip()
        if not repo:
            return
        if repo.startswith("https://huggingface.co/"):
            repo = "/".join(repo.split("/")[3:5])
        if not keep_choice:                       # otro modelo: se vuelve al GGUF preparado
            self.base_repo = None
            self.chk_orig.hide()
            self.chk_orig.blockSignals(True)
            self.chk_orig.setChecked(False)
            self.chk_orig.blockSignals(False)
        self.cur_repo = repo
        self.info = None
        self.repo_desc.setText("Consultando las variantes de %s…" % repo)
        self.table.setRowCount(0)
        cat = next((e for e in (getattr(self, "rated", None) or []) if e["repo"] == repo), None)
        run_bg(lambda: P.hf_files(repo), lambda r: repo == self.cur_repo and self._got_repo(r, cat))

    def _got_repo(self, r, cat):
        if isinstance(r, Exception):
            self.repo_desc.setText("No pude leer el repositorio (¿sin internet o nombre incorrecto?): %s" % r)
            self.info = None
            return
        orig = r.get("original")
        if not r["quants"] and orig:              # formato original: se descarga y se convierte a GGUF en este equipo
            ci = CV.describe_config(orig.get("config") or {}, orig["size"])
            if ci.get("why_not"):
                self.repo_desc.setText("✗ " + ci["why_not"])
                self.info = None
                return
            r["orig_info"] = ci
            r["quants"], _ = self._targets(ci["params"])
            r["mmproj"] = []
            self.info = r
            self.repo_desc.setText("Formato original de Hugging Face (%s, %d archivos) · %s · ~%.1f mil millones de parámetros%s. "
                                   "Jayth lo descarga y lo convierte a GGUF en tu equipo con las herramientas oficiales de llama.cpp." % (
                                       HW.human(orig["size"]), len(orig["files"]), ci["arch"], ci["params"] / 1e9, " · con visión" if ci["vision"] else ""))
            self.chk_mm.setEnabled(ci["vision"])
            self.chk_mm.setChecked(ci["vision"])
            self.chk_mm.setText("Incluir visión (se convierte también el proyector de imágenes)" if ci["vision"] else "Este modelo no tiene visión (solo texto)")
            self.chk_del_orig.show()
            self._fill_table()
            return
        self.chk_del_orig.hide()
        if not r["quants"]:
            self.repo_desc.setText("Ese repositorio no contiene archivos GGUF ni el modelo en formato original.")
            self.info = None
            return
        self.info = r
        if self.base_repo is None and not self.chk_orig.isChecked():
            run_bg(lambda repo=r["repo"]: P.base_model(repo), lambda b, repo=r["repo"]: self._got_base(repo, b))
        desc = ""
        if cat:
            desc = "%s · %s · %.1f mil millones de parámetros%s. " % (cat["name"], cat["lab"], cat["params"] / 1e9,
                                                                      (" (MoE, ~%.1f activos)" % (cat["active"] / 1e9)) if cat["active"] < cat["params"] * 0.6 else "")
            if cat is getattr(self, "rec_model", None):
                desc += "Recomendado para tu equipo: el más capaz que cabe y va fluido. "
        self.repo_desc.setText(desc + "%d variantes disponibles." % len(r["quants"]))
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
            name = q["label"] + (" · se crea al convertir" if q.get("convert") else "") + ("   ★ recomendada" if rec is q else "")
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

    # --- modelo que ya tengo: GGUF, carpeta original de Hugging Face, Ollama o LM Studio
    def _pick_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Elegir modelo", os.path.dirname(self.f_model.text()) or os.path.expanduser("~"),
                                           "Modelos (*.gguf *.safetensors config.json);;Todos (*.*)")
        if p:
            self.f_model.setText(os.path.normpath(p))

    def _pick_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Elegir la carpeta del modelo", self.f_model.text() or os.path.expanduser("~"))
        if p:
            self.f_model.setText(os.path.normpath(p))

    def _got_found(self, items):
        self.found.clear()
        if isinstance(items, Exception) or not items:
            self.found.addItem("No hay modelos de Ollama ni de LM Studio en este equipo", None)
            self.found.setEnabled(False)
            return
        self.found.addItem("Elige uno (%d encontrados)…" % len(items), None)
        for it in items:
            self.found.addItem("%s · %s (%s)" % (it["source"], it["name"], HW.human(it["size"])), it)

    def _use_found(self, i):
        it = self.found.itemData(i)
        if it:
            self.f_model.setText(it["path"])
            self.f_mm.setText(it.get("mmproj") or "")
            self.local["name"] = it["name"]

    def _detect_local(self):
        path = self.f_model.text().strip()
        self.local = {} if not path else CV.detect(path)
        fmt = self.local.get("format")
        self.f_quant_row.setVisible(fmt == "hf" and not self.local.get("why_not"))
        self.f_mm_row.setVisible(fmt != "hf")
        if not path:
            return self.f_info.setText("")
        if fmt == "missing":
            return self.f_info.setText("No existe.")
        if fmt == "gguf":
            if self.local.get("mmproj") and not self.f_mm.text():
                self.f_mm.setText(self.local["mmproj"])
            return self.f_info.setText("✓ GGUF listo para usar · %s" % HW.human(self.local["size"]))
        if fmt == "other" or self.local.get("why_not"):
            return self.f_info.setText("✗ " + self.local.get("why_not", "Formato no compatible."))
        info = self.local
        self.f_info.setText("Formato original de Hugging Face (%s, %s) · %s · ~%.1f mil millones de parámetros%s." % (
            info["weights"], HW.human(info["size"]), info["arch"], info["params"] / 1e9, " · con visión" if info["vision"] else ""))
        self._fill_targets(self.f_quant, info["params"])
        self._local_space()

    def _targets(self, params):
        """Variantes a las que se puede convertir un original, con su tamaño estimado y si cabe en este equipo."""
        qs = [{"label": q, "file": q, "size": CV.target_size(params, q), "desc": d, "convert": True} for q, b, d in CV.QUANT_TARGETS]
        rec = HW.recommend_quant(qs, self.hw) if self.hw else qs[0]
        return qs, rec

    def _fill_targets(self, combo, params):
        qs, rec = self._targets(params)
        combo.blockSignals(True)
        combo.clear()
        for q in sorted(qs, key=lambda q: q["size"]):
            fit = HW.classify(q["size"], self.hw) if self.hw else "ok"
            combo.addItem("%s · ~%s · %s · %s%s" % (q["label"], HW.human(q["size"]), FIT_TXT[fit], q["desc"], "   ★ recomendada" if q is rec else ""), q)
        combo.setCurrentIndex(max(0, next((i for i in range(combo.count()) if combo.itemData(i) is rec), 0)))
        combo.blockSignals(False)

    def _local_space(self):
        q = self.f_quant.currentData()
        if not q or self.local.get("format") != "hf":
            return
        need, final = CV.plan_space(self.local, q["label"])
        dest = self.cfg["models_dir"] or paths.MODELS_DEFAULT
        free = HW.disk_free(dest)
        self.f_info.setText(self.f_info.text().split("\n")[0] + "\nResultado ~%s en %s · durante la conversión hacen falta ~%s libres (hay %s)%s." % (
            HW.human(final), dest, HW.human(need), HW.human(free), "  ⚠ no hay espacio suficiente" if need > free else ""))

    # --- formato original en vez del GGUF ya preparado
    def _toggle_original(self, on):
        if on and self.base_repo:
            self.gguf_repo = self.cur_repo
            self.load_repo(self.base_repo, keep_choice=True)
        elif not on and getattr(self, "gguf_repo", None):
            self.load_repo(self.gguf_repo, keep_choice=True)

    def _got_base(self, repo, base):
        if repo != self.cur_repo or isinstance(base, Exception) or not base:
            return
        self.base_repo = base
        self.chk_orig.blockSignals(True)
        self.chk_orig.setChecked(False)
        self.chk_orig.blockSignals(False)
        self.chk_orig.setText("Prefiero el formato original (%s) y convertirlo en mi equipo (descarga más grande)" % base)
        self.chk_orig.show()

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
            fmt = (self.local or {}).get("format")
            if fmt not in ("gguf", "hf"):
                return QMessageBox.warning(self, "Modelo no válido", "Elige un archivo .gguf o la carpeta de un modelo original de Hugging Face.")
            if self.local.get("why_not"):
                return QMessageBox.warning(self, "Formato no compatible", self.local["why_not"])
            if fmt == "hf" and self.f_quant.currentData():
                need, _ = CV.plan_space(self.local, self.f_quant.currentData()["label"])
                if need > HW.disk_free(self.cfg["models_dir"] or paths.MODELS_DEFAULT):
                    return QMessageBox.warning(self, "Falta espacio", "Para convertir hacen falta ~%s libres en %s." % (
                        HW.human(need), self.cfg["models_dir"] or paths.MODELS_DEFAULT))
            if fmt == "gguf" and self.f_mm.text() and not os.path.isfile(self.f_mm.text()):
                return QMessageBox.warning(self, "Archivo no encontrado", "El proyector de visión indicado no existe.")
        elif self._selected_quant() is None:
            return QMessageBox.warning(self, "Elige una variante", "Elige un modelo de la lista y espera a que aparezcan sus variantes.")
        self.go(self.p_engine)

    def _llama_ok(self):
        b = self.backend.currentData()
        return os.path.isfile(self.cfg["llama_exe"]) and self.cfg["backend"] == b

    def _eng_state(self):
        if self.chk_own.isChecked():
            self.eng_state.setText("Se usará tu %s." % SERVER_EXE)
        elif self._llama_ok():
            self.eng_state.setText("✓ Ya instalado (%s). No hace falta descargarlo." % (self.cfg["llama_tag"] or "versión local"))
        else:
            self.eng_state.setText("Se descargará la última versión oficial desde GitHub (ggml-org/llama.cpp).")

    # --- instalacion
    def _install(self):
        backend = self.backend.currentData()
        if self.chk_own.isChecked() and not os.path.isfile(self.own_exe.text()):
            return QMessageBox.warning(self, "Archivo no encontrado", "Elige un %s existente." % SERVER_EXE)
        job = P.Job()
        if self.chk_own.isChecked():
            exe = self.own_exe.text()
            job.add("Motor: usar llama-server existente", lambda pr, st, res: res.update(llama_exe=exe, llama_tag="propio"))
        elif self._llama_ok():
            job.add("Motor: ya instalado", lambda pr, st, res: res.update(llama_exe=self.cfg["llama_exe"], llama_tag=self.cfg["llama_tag"]))
        else:
            job.add("Motor llama.cpp (%s)" % dict(BACKENDS)[backend], lambda pr, st, res: self._job_llama(backend, pr, st, res))
        threads = self.threads.value()
        if self.r_hf.isChecked() and self._selected_quant() and self._selected_quant().get("convert"):
            # formato original: descargar sus archivos, preparar el convertidor y crear el GGUF en este equipo
            q, info = self._selected_quant(), self.info
            models = self.dest.text() or paths.MODELS_DEFAULT
            src = os.path.join(models, info["repo"].replace("/", "__") + "__original")
            out = os.path.join(models, info["repo"].replace("/", "__") + "__gguf")
            files = info["original"]["files"]
            big = [f for f in files if f["size"] > 50_000_000]
            small = [f for f in files if f not in big]
            job.add("Archivos de configuración del original", lambda pr, st, res: [
                P.download(P.hf_url(info["repo"], f["file"]), os.path.join(src, f["file"]), f["size"], "", pr, st) for f in small])
            for k, f in enumerate(big):
                job.add("Original · parte %d de %d" % (k + 1, len(big)) if len(big) > 1 else "Modelo original",
                        lambda pr, st, res, f=f: P.download(P.hf_url(info["repo"], f["file"]), os.path.join(src, f["file"]), f["size"], f["sha256"], pr, st),
                        size=f["size"])
            self._conversion_steps(job, src, out, q["label"], self.chk_mm.isChecked(), threads, delete_src=self.chk_del_orig.isChecked(),
                                   name=P.pretty_name(info["repo"]))
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", info["repo"] + "_" + q["label"]), "name": P.pretty_name(info["repo"]),
                                  "quant": q["label"], "path": "", "mmproj": "", "repo": info["repo"], "file": "", "size": int(q["size"]),
                                  "added": time.time(), "converted_from": "original"}
        elif self.r_file.isChecked() and (self.local or {}).get("format") == "hf":
            q = self.f_quant.currentData()
            info = self.local
            out = os.path.join(self.dest.text() or paths.MODELS_DEFAULT, re.sub(r"[^\w.-]+", "_", info["name"]) + "__gguf")
            self._conversion_steps(job, info["path"], out, q["label"], info.get("vision"), threads, delete_src=False, name=info["name"])
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", "local_" + info["name"] + "_" + q["label"]), "name": info["name"],
                                  "quant": q["label"], "path": "", "mmproj": "", "repo": "", "file": "", "size": int(q["size"]),
                                  "added": time.time(), "converted_from": info["path"]}
        elif self.r_hf.isChecked():
            q, info = self._selected_quant(), self.info
            folder = os.path.join(self.dest.text() or paths.MODELS_DEFAULT, info["repo"].replace("/", "__"))
            for k, part in enumerate(q["parts"]):
                job.add("Modelo %s%s" % (q["label"], " parte %d/%d" % (k + 1, len(q["parts"])) if len(q["parts"]) > 1 else ""),
                        lambda pr, st, res, part=part: P.download(P.hf_url(info["repo"], part["file"]), os.path.join(folder, os.path.basename(part["file"])),
                                                                  part["size"], part["sha256"], pr, st), size=part["size"])
            mm = info["mmproj"][0] if info["mmproj"] and self.chk_mm.isChecked() else None
            if mm:
                job.add("Proyector de visión", lambda pr, st, res: P.download(P.hf_url(info["repo"], mm["file"]), os.path.join(folder, os.path.basename(mm["file"])),
                                                                               mm["size"], mm["sha256"], pr, st), size=mm["size"])
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", info["repo"] + "_" + q["label"]), "name": P.pretty_name(info["repo"]),
                                  "quant": quant_short(q["label"]), "path": os.path.join(folder, os.path.basename(q["parts"][0]["file"])),
                                  "mmproj": os.path.join(folder, os.path.basename(mm["file"])) if mm else "",
                                  "repo": info["repo"], "file": q["file"], "size": q["size"], "added": time.time()}
        else:
            p = os.path.normpath((self.local or {}).get("path") or self.f_model.text())
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", "local_" + os.path.basename(p)),
                                  "name": (self.local or {}).get("name") or P.pretty_name(os.path.basename(p)),
                                  "quant": P.quant_label(os.path.basename(p)), "path": p, "mmproj": os.path.normpath(self.f_mm.text()) if self.f_mm.text() else "",
                                  "repo": "", "file": os.path.basename(p), "size": os.path.getsize(p), "added": time.time()}
        self.pending_cfg = {"backend": "cpu" if self.chk_own.isChecked() and backend == "cpu" else backend, "threads": self.threads.value(),
                            "n_ctx": self.ctx.currentData(), "models_dir": self.dest.text() or paths.MODELS_DEFAULT}
        self._start_job(job)

    def _conversion_steps(self, job, src, out, quant, vision, threads, delete_src=False, name=""):
        """Pasos para pasar un original de Hugging Face a GGUF: herramientas (una vez), conversion y reduccion, vision."""
        def tools(pr, st, res):
            exe = res.get("llama_exe") or self.cfg["llama_exe"]
            if CV.tools_ready(CV.llama_build(exe)):
                pr(1, 1, "ya preparadas")
                return
            CV.ensure_tools(exe, pr, st)

        def conv(pr, st, res):
            exe = res.get("llama_exe") or self.cfg["llama_exe"]
            model, mm = CV.convert_model(src, out, quant, exe, vision=vision, threads=threads, progress=pr, stop=st, name=name)
            res.update(model_path=model, mmproj_path=mm)
            if delete_src:
                shutil.rmtree(src, ignore_errors=True)
        job.add("Herramientas de conversión (solo la primera vez)", tools)
        job.add("Convertir a GGUF y crear la variante %s%s" % (quant, " + visión" if vision else ""), conv)

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
            P.extract_archive(z, target)
        exe = P.find_server(target)
        if not exe:
            raise RuntimeError("El paquete de llama.cpp no contiene %s" % SERVER_EXE)
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
        # resumen de todo el trabajo arriba, y una fila por paso con su barra y su estado debajo
        head = QFrame()
        head.setObjectName("noteBox")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(14, 10, 14, 10)
        self.ov_pct = QLabel("0 %")
        self.ov_pct.setStyleSheet("font-size:20pt; font-weight:700")
        self.ov_bar = QProgressBar()
        self.ov_bar.setRange(0, 1000)
        self.ov_bar.setTextVisible(False)
        self.ov_det = lbl("Preparando…", "muted")
        hv.addWidget(self.ov_pct)
        hv.addWidget(self.ov_bar)
        hv.addWidget(self.ov_det)
        self.prog_box.addWidget(head)
        self.rows = []
        for st in job.steps:
            w = QWidget()
            g = QVBoxLayout(w)
            g.setContentsMargins(0, 8, 0, 2)
            g.setSpacing(3)
            name = lbl(st["label"])
            name.setStyleSheet("font-weight:600")
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            det = lbl(P.describe_step(st), "muted")
            det.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(name)
            g.addWidget(bar)
            g.addWidget(det)
            self.prog_box.addWidget(w)
            self.rows.append((bar, det))
        self.prog_err.hide()
        self.go(self.p_progress)
        job.start()
        self.timer.start()
        self._tick()

    def _tick(self):
        j = self.job
        for st, (bar, det) in zip(j.steps, self.rows):
            if st["status"] == "done":
                bar.setValue(1000)
            elif st["total"]:
                bar.setValue(int(1000 * st["done"] / max(1, st["total"])))
            det.setText(P.describe_step(st))
        o = j.overall()
        frac = o["got"] / o["total"] if o["total"] else (o["done_steps"] / max(1, o["steps"]))
        if j.finished and not j.error:
            frac = 1.0
        self.ov_bar.setValue(int(1000 * frac))
        self.ov_pct.setText("%d %%" % int(100 * frac))
        self.ov_det.setText(P.describe_overall(o))
        self.setWindowTitle("%d %% · Descargando · Asistente de configuración" % int(100 * frac) if not j.finished else "Asistente de configuración")
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
        if res.get("model_path"):                 # modelo convertido desde el formato original
            self.pending_model.update(path=res["model_path"], mmproj=res.get("mmproj_path") or "", file=os.path.basename(res["model_path"]),
                                      size=os.path.getsize(res["model_path"]))
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
        self.t = QTableWidget(0, 5)
        self.t.setHorizontalHeaderLabels(["", "Modelo", "Variante", "Tamaño", "Archivo"])
        self.t.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
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
            self.t.setItem(i, 1, QTableWidgetItem(core.model_title(m) + ("" if ok else "  (archivo no encontrado)")))
            self.t.setItem(i, 2, QTableWidgetItem(core.model_quant(m)))
            self.t.setItem(i, 3, QTableWidgetItem(HW.human(m.get("size", 0))))
            self.t.setItem(i, 4, QTableWidgetItem(m.get("path", "")))
            self.t.item(i, 4).setToolTip(m.get("path", ""))
        for c in (0, 1, 2, 3):
            self.t.resizeColumnToContents(c)

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
            osys.open_path(p)

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
