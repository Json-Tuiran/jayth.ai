# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
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
from . import i18n
from .i18n import tr
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

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
    """Icono del color del texto del botón: el de sobre el verde en los principales (oscuro o blanco según el tema) y rojo
    en los de peligro, que van con borde y fondo transparente."""
    kind = b.property("kind")
    b.setIcon(icon(ico, C["on_acc"] if kind in ("primary", "ok") else C["bad"] if kind == "danger" else C["tx"], 16))
    b.setIconSize(QSize(16, 16))


def lbl(text="", name=None, wrap=True):
    l = QLabel(text)
    l.setWordWrap(wrap)
    l.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if name:
        l.setObjectName(name)
    return l


def browse_row(edit, folder=False, filt=tr("Modelos GGUF (*.gguf);;Todos (*.*)"), parent=None):
    row = QHBoxLayout()
    row.addWidget(edit, 1)

    def pick():
        if folder:
            p = QFileDialog.getExistingDirectory(parent, tr("Elegir carpeta"), edit.text() or os.path.expanduser("~"))
        else:
            p, _ = QFileDialog.getOpenFileName(parent, tr("Elegir archivo"), os.path.dirname(edit.text()) or os.path.expanduser("~"), filt)
        if p:
            edit.setText(os.path.normpath(p))
    row.addWidget(btn(tr("Examinar…"), cb=pick))
    return row


FIT_TXT = {"ok": tr("✓ cabe"), "tight": tr("⚠ muy justo"), "no": tr("✗ no cabe")}
FIT_COL = {"ok": C["ok"], "tight": C["warn"], "no": C["bad"]}
_BACKEND_NAMES = {"cpu": tr("Solo CPU (funciona en cualquier equipo)"), "cuda": tr("GPU NVIDIA (CUDA)"),
                  "vulkan": tr("GPU AMD / Intel Arc (Vulkan)"), "metal": tr("GPU de Apple (Metal)")}
BACKENDS = [(k, _BACKEND_NAMES[k]) for k in ("metal", "cuda", "vulkan", "cpu") if k in P.LLAMA_PATTERNS]
SERVER_EXE = osys.exe("llama-server")
# etiquetas internas del catálogo (provision._entry; se comparan): su texto en pantalla
_TAG_TXT = {"agente": tr("agente"), "visión": tr("visión"), "audio": tr("audio"), "código": tr("código"), "razonamiento": tr("razonamiento")}


def _lab_txt(lab):
    """Laboratorio en pantalla: «Otros» es el valor interno de provision.lab_of (se compara al ordenar)."""
    return tr("Otros") if lab == "Otros" else lab


# ---------------------------------------------------------------- asistente
class SetupWizard(QDialog):
    """Primera configuracion o 'Añadir modelo'. Deja todo listo: motor, modelo y ajustes."""

    def __init__(self, parent=None, start="welcome", repo=None):
        super().__init__(parent)
        self.preset_repo = repo           # p. ej. al pulsar «Ver» en el aviso de un modelo nuevo
        self.setWindowTitle(tr("Asistente de configuración"))
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
        self.b_cancel = btn(tr("Cancelar"), cb=self.reject)
        self.b_back = btn(tr("Atrás"), cb=self.back)
        self.b_next = btn(tr("Siguiente"), "primary", self.next)
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
        w, v = self._page(tr("Configuremos tu agente local"),
                          tr("Este asistente prepara todo para usar modelos de IA en tu propio equipo: descarga el motor (llama.cpp) "
                             "adecuado a tu hardware y el modelo que elijas, y lo deja configurado. Después todo funciona sin internet."))
        v.addSpacing(8)
        v.addWidget(lbl(tr("TU EQUIPO"), "section"))
        self.hw_lbl = lbl(tr("Detectando hardware…"))
        v.addWidget(self.hw_lbl)
        v.addWidget(lbl(tr("La rapidez del agente depende de este equipo: con una tarjeta gráfica o un Mac con chip Apple responde "
                           "varias veces más rápido. Sin gráfica también funciona, con modelos pequeños y más despacio (la primera "
                           "respuesta de cada conversación puede tardar unos minutos). En el paso siguiente verás qué modelos caben "
                           "y su velocidad aproximada."), "faint"))
        v.addSpacing(8)
        v.addWidget(lbl(tr("DÓNDE SE GUARDA"), "section"))
        v.addWidget(lbl(tr("Ajustes y conversaciones: %s\nCarpeta de trabajo del agente: %s") % (paths.HOME, self.cfg["workspace"]), "muted"))
        v.addStretch(1)
        return w

    def _model(self):
        w, v = self._page(tr("Elige el modelo"), tr("Puedes usar cualquier modelo en formato GGUF. Luego podrás añadir más desde «Modelos»."))
        self.r_hf = QRadioButton(tr("Descargar un modelo de Hugging Face"))
        self.r_file = QRadioButton(tr("Usar un modelo que ya tengo (GGUF, original de Hugging Face, Ollama o LM Studio)"))
        self.r_ext = QRadioButton(tr("Conectar a un servidor externo compatible con OpenAI (Ollama, LM Studio, otro PC…)"))
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
        self.cat_search.setPlaceholderText(tr("Buscar modelo o laboratorio (Gemma, DeepSeek, Mistral, Llama…)"))
        self.cat_search.setClearButtonEnabled(True)
        self.cat_search.textChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_search, 1)
        # tipo de modelo (qué sabe hacer) y si va bien en este equipo: dos filtros independientes
        self.cat_kind = QComboBox()
        for t, k, tip in ((tr("Todos los tipos"), "all", ""),
                          (tr("Agéntico (usa herramientas)"), "agent", tr("Sabe llamar a herramientas: lo que necesita el agente de Jayth para trabajar con archivos, comandos y la web.")),
                          (tr("Multimodal (ve imágenes)"), "multi", tr("Entiende imágenes (y algunos también audio): capturas, fotos, documentos escaneados…")),
                          (tr("Uso general"), "general", tr("Para conversar, escribir, resumir y responder (sin los modelos solo de programación).")),
                          (tr("Programación"), "code", tr("Especializados en escribir y revisar código.")),
                          (tr("Razonamiento"), "reason", tr("Piensan antes de responder: mejores en problemas de varios pasos, algo más lentos."))):
            self.cat_kind.addItem(t, k)
            if tip:
                self.cat_kind.setItemData(self.cat_kind.count() - 1, tip, Qt.ToolTipRole)
        self.cat_kind.setToolTip(tr("Qué sabe hacer el modelo"))
        self.cat_kind.currentIndexChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_kind)
        self.cat_filter = QComboBox()
        for t, k in ((tr("Todos (caben o no)"), "all"), (tr("Caben en tu equipo"), "fit"), (tr("Rápidos en tu equipo"), "fast")):
            self.cat_filter.addItem(t, k)
        self.cat_filter.setToolTip(tr("Según la memoria y la velocidad de tu equipo"))
        self.cat_filter.currentIndexChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_filter)
        self.cat_lab = QComboBox()
        self.cat_lab.addItem(tr("Todos los laboratorios"), "")
        self.cat_lab.currentIndexChanged.connect(self._fill_catalog)
        frow.addWidget(self.cat_lab)
        hv.addLayout(frow)
        self.cat_table = QTableWidget(0, 6)
        self.cat_table.setHorizontalHeaderLabels([tr("Modelo"), tr("Tipo"), tr("Laboratorio"), tr("Descarga"), tr("Velocidad aprox."), tr("En tu equipo")])
        self.cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # las demás columnas se ajustan UNA vez tras rellenar la tabla (_fit_catalog_columns): en modo «ajustar al
        # contenido» Qt volvía a medir todas las filas con cada celda escrita y el asistente se congelaba ~35 s
        for c in range(1, 6):
            self.cat_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
        self.cat_table.verticalHeader().setVisible(False)
        self.cat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cat_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cat_table.setMinimumHeight(190)
        self.cat_table.itemSelectionChanged.connect(self._cat_selected)
        hv.addWidget(self.cat_table, 2)
        orow = QHBoxLayout()
        orow.addWidget(lbl(tr("¿Otro? Repositorio de Hugging Face:"), "muted"))
        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText(tr("usuario/Modelo-GGUF"))
        self.repo_edit.returnPressed.connect(lambda: self.load_repo(self.repo_edit.text().strip()))
        orow.addWidget(self.repo_edit, 1)
        orow.addWidget(btn(tr("Ver"), cb=lambda: self.load_repo(self.repo_edit.text().strip())))
        hv.addLayout(orow)
        self.repo_desc = lbl("", "muted")
        hv.addWidget(self.repo_desc)
        self.catalog, self.cur_repo = None, ""
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Cuantización"), tr("Tamaño"), tr("En tu equipo")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_disk)
        self.table.setMinimumHeight(120)
        hv.addWidget(lbl(tr("Variante (versión más ligera o más fiel del modelo):"), "muted"))
        hv.addWidget(self.table, 1)
        self.chk_orig = QCheckBox()
        self.chk_orig.hide()
        self.chk_orig.toggled.connect(self._toggle_original)
        self.base_repo = None
        hv.addWidget(self.chk_orig)
        self.chk_del_orig = QCheckBox(tr("Borrar el original descargado al terminar la conversión (libera espacio)"))
        self.chk_del_orig.setChecked(True)
        self.chk_del_orig.hide()
        hv.addWidget(self.chk_del_orig)
        self.chk_mm = QCheckBox(tr("Incluir visión (permite que el modelo vea imágenes y capturas de pantalla)"))
        hv.addWidget(self.chk_mm)
        self.dest = QLineEdit(core.models_dir(self.cfg))
        self.dest.textChanged.connect(self._update_disk)
        hv.addWidget(lbl(tr("Carpeta donde guardar los modelos:"), "muted"))
        hv.addLayout(browse_row(self.dest, folder=True, parent=self))
        self.disk_lbl = lbl("", "muted")
        hv.addWidget(self.disk_lbl)
        self.sub.addWidget(hf)
        # -- archivo local
        lf = QWidget()
        fv = QFormLayout(lf)
        fv.setContentsMargins(22, 4, 0, 0)
        self.f_model = QLineEdit()
        self.f_model.setPlaceholderText(tr("archivo .gguf, o carpeta del modelo original (config.json + .safetensors)"))
        self.f_model.textChanged.connect(self._detect_local)
        self.f_mm = QLineEdit()
        self.f_mm.setPlaceholderText(tr("opcional"))
        mrow = QHBoxLayout()
        mrow.addWidget(self.f_model, 1)
        mrow.addWidget(btn(tr("Archivo…"), cb=self._pick_file))
        mrow.addWidget(btn(tr("Carpeta…"), cb=self._pick_folder))
        self.found = QComboBox()
        self.found.addItem(tr("Buscando modelos de Ollama y LM Studio…"), None)
        self.found.activated.connect(self._use_found)
        fv.addRow(tr("Encontrados:"), self.found)
        fv.addRow(tr("Modelo:"), mrow)
        self.f_info = lbl("", "muted")
        fv.addRow("", self.f_info)
        self.f_quant = QComboBox()
        self.f_quant.currentIndexChanged.connect(self._local_space)
        self.f_quant_row = QWidget()
        qr = QHBoxLayout(self.f_quant_row)
        qr.setContentsMargins(0, 0, 0, 0)
        qr.addWidget(self.f_quant, 1)
        fv.addRow(tr("Convertir a:"), self.f_quant_row)
        self.f_quant_row.setVisible(False)
        self.f_mm_row = QWidget()
        mmr = browse_row(self.f_mm, parent=self)
        mmr.setContentsMargins(0, 0, 0, 0)
        self.f_mm_row.setLayout(mmr)
        fv.addRow(tr("Proyector de visión (mmproj):"), self.f_mm_row)
        fv.addRow(lbl(tr("Un modelo original se convierte a GGUF en tu equipo con las herramientas oficiales de llama.cpp "
                         "(se preparan una sola vez). Tu carpeta original no se modifica."), "muted"))
        self.local = {}
        self.sub.addWidget(lf)
        run_bg(CV.other_apps_models, self._got_found)
        # -- servidor externo
        ex = QWidget()
        ev = QFormLayout(ex)
        ev.setContentsMargins(22, 4, 0, 0)
        self.e_url = QLineEdit(self.cfg["external_url"])
        self.e_model = QLineEdit(self.cfg["external_model"])
        self.e_model.setPlaceholderText(tr("nombre del modelo en ese servidor, p. ej. qwen3:8b"))
        self.e_key = QLineEdit(self.cfg["external_key"])
        self.e_key.setEchoMode(QLineEdit.Password)
        self.e_key.setPlaceholderText(tr("vacío si no hace falta"))
        self.e_res = lbl("", "muted")
        ev.addRow(tr("URL base (/v1):"), self.e_url)
        ev.addRow(tr("Modelo:"), self.e_model)
        ev.addRow(tr("Clave API:"), self.e_key)
        ev.addRow(btn(tr("Probar conexión"), cb=self.test_ext), self.e_res)
        self.sub.addWidget(ex)
        for i, r in enumerate((self.r_hf, self.r_file, self.r_ext)):
            r.toggled.connect(lambda on, i=i: on and self.sub.setCurrentIndex(i))
        return w

    def _engine(self):
        w, v = self._page(tr("Motor de inferencia"), tr("llama.cpp ejecuta el modelo. Se descarga la compilación oficial adecuada a tu equipo."))
        f = QFormLayout()
        self.backend = QComboBox()
        for k, t in BACKENDS:
            self.backend.addItem(t, k)
        f.addRow(tr("Usar:"), self.backend)
        self.eng_state = lbl("", "muted")
        f.addRow("", self.eng_state)
        # con el mismo motor ya instalado no se descargaba nada: «Cambiar o actualizar» no podía actualizar
        self.chk_update = QCheckBox(tr("Actualizar a la última versión aunque ya esté instalado"))
        self.chk_update.setVisible(bool(self.cfg["llama_exe"]) and self.cfg.get("llama_tag") != "propio")
        f.addRow("", self.chk_update)
        self.chk_own = QCheckBox(tr("Usar un %s que ya tengo") % SERVER_EXE)
        self.own_exe = QLineEdit(self.cfg["llama_exe"])
        f.addRow(self.chk_own)
        own_row = QWidget()
        own_row.setLayout(browse_row(self.own_exe, filt=("%s (%s)" % (SERVER_EXE, SERVER_EXE)) if osys.WIN else "", parent=self))
        own_row.layout().setContentsMargins(0, 0, 0, 0)
        own_row.setEnabled(False)
        self.chk_own.toggled.connect(own_row.setEnabled)
        f.addRow(tr("Ruta:"), own_row)
        self.threads = QSpinBox()
        self.threads.setRange(1, 256)
        self.threads.setValue(self.cfg["threads"])
        f.addRow(tr("Hilos de CPU:"), self.threads)
        self.ctx = QComboBox()
        self.ctx.addItem(tr("Automático: lo que admita el modelo (recomendado)"), 0)
        for n in (4096, 8192, 16384, 32768, 65536, 131072, 262144):
            self.ctx.addItem("%d tokens" % n, n)
        self.ctx.setCurrentIndex(max(0, self.ctx.findData(self.cfg["n_ctx"])))
        f.addRow(tr("Contexto:"), self.ctx)
        v.addLayout(f)
        v.addWidget(lbl(tr("Automático usa todo el contexto que admite el modelo de fábrica, reducido si no cabe en la memoria de tu "
                           "equipo. Más contexto permite tareas más largas, pero usa más memoria."), "muted"))
        v.addStretch(1)
        self.backend.currentIndexChanged.connect(self._eng_state)
        self.chk_own.toggled.connect(self._eng_state)
        self.chk_update.toggled.connect(self._eng_state)
        return w

    def _progress(self):
        w, v = self._page(tr("Descargando e instalando"), tr("Puedes cancelar: lo descargado se conserva y se reanuda después."))
        self.prog_box = QVBoxLayout()
        v.addLayout(self.prog_box)
        self.prog_err = lbl("", "err")
        self.prog_err.hide()
        v.addWidget(self.prog_err)
        v.addStretch(1)
        return w

    def _done(self):
        w, v = self._page(tr("¡Listo!"))
        self.done_lbl = lbl("")
        v.addWidget(self.done_lbl)
        self.chk_start = QCheckBox(tr("Encender el modelo ahora"))
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
        self.b_next.setText({self.p_done: tr("Empezar")}.get(page, tr("Instalar") if page is self.p_engine else tr("Siguiente")))
        self.b_next.setEnabled(page is not self.p_progress)
        self.b_cancel.setText(tr("Cancelar descarga") if page is self.p_progress else tr("Cancelar"))
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
            self.hw_lbl.setText(tr("No pude detectar el hardware: %s") % hw)
            return
        self.hw = hw
        b = HW.recommend_backend(hw)
        self.hw_lbl.setText(tr("%s\n\nMemoria disponible para el modelo: ~%s · Motor recomendado: %s") % (
            HW.summary(hw), HW.human(HW.memory_budget(hw)), dict(BACKENDS)[b]))
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
        self.repo_desc.setText(tr("Buscando modelos abiertos publicados en Hugging Face…"))
        run_bg(lambda: P.catalog(os.path.join(paths.DATA, "catalog.json"), refresh=refresh), self._got_catalog)

    def _got_catalog(self, cat):
        if isinstance(cat, Exception) or not cat:
            self.repo_desc.setText(tr("No pude leer el catálogo (¿sin internet?). Escribe un repositorio a mano."))
            return
        self.catalog = cat
        labs = sorted({e["lab"] for e in cat}, key=lambda l: (l == "Otros", l.lower()))
        self.cat_lab.blockSignals(True)
        for l in labs:
            self.cat_lab.addItem(_lab_txt(l), l)
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
        have = {}                                   # repositorio -> modelos de tu lista que salen de él (con sus archivos)
        for m in self._installed():
            if m.get("repo"):
                have.setdefault(m["repo"].lower(), []).append(m)
        self.cat_table.blockSignals(True)
        self.cat_table.setUpdatesEnabled(False)
        self.cat_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            mine = have.get(e["repo"].lower(), [])
            name = e["name"] + (("   ★ " + tr("recomendado")) if e is rec else "") + (("   ✓ " + tr("descargado")) if mine else "")
            it = QTableWidgetItem(name)
            it.setData(Qt.UserRole, e["repo"])
            tip = ["%s · %s" % (e["repo"], _lab_txt(e["lab"])), tr("%s mil millones de parámetros") % i18n.number(e["params"] / 1e9)]
            if mine:
                it.setForeground(QColor(C["ok"]))
                tip.insert(0, tr("Ya lo tienes descargado: %s") % ", ".join(core.model_quant(m) or os.path.basename(m["path"]) for m in mine))
            if e["active"] < e["params"] * 0.6:
                tip.append(tr("MoE: usa ~%s mil millones por palabra (por eso va más rápido de lo que su tamaño sugiere)") % i18n.number(e["active"] / 1e9))
            if e.get("ctx"):
                tip.append(tr("Contexto máximo: %s tokens") % format(int(e["ctx"]), ",").replace(",", "."))
            if e.get("tools"):
                tip.append(tr("Agéntico: sabe usar herramientas (archivos, comandos, web…), como necesita el agente de Jayth"))
            elif "tools" in e:
                tip.append(tr("No usa herramientas: sirve para conversar, pero el agente no podrá actuar con él"))
            if e["tags"]:
                tip.append(tr("Destaca en: %s") % ", ".join(_TAG_TXT.get(t, t) for t in e["tags"]))
            it.setToolTip("\n".join(tip))
            self.cat_table.setItem(i, 0, it)
            ki = QTableWidgetItem(P.kind_text(e))
            ki.setForeground(QColor(C["acc"] if e.get("tools") else C["mut"]))
            ki.setToolTip(tr("Agente = usa herramientas · Visión = entiende imágenes · Razona = piensa antes de responder"))
            self.cat_table.setItem(i, 1, ki)
            self.cat_table.setItem(i, 2, QTableWidgetItem(_lab_txt(e["lab"])))
            self.cat_table.setItem(i, 3, QTableWidgetItem(HW.human(e["size"])))
            sp = e["speed"]
            st = QTableWidgetItem(("~%.0f tok/s" % sp) if sp >= 10 else ("~%.1f tok/s" % sp) if sp >= 0.1 else "—")
            st.setToolTip(tr("Velocidad aproximada al escribir la respuesta en este equipo (estimación)."))
            self.cat_table.setItem(i, 4, st)
            if self.hw:
                fi = QTableWidgetItem(FIT_TXT[e["fit"]])
                fi.setForeground(QColor(FIT_COL[e["fit"]]))
                self.cat_table.setItem(i, 5, fi)
        self._fit_catalog_columns()
        self.cat_table.setUpdatesEnabled(True)
        self.cat_table.blockSignals(False)
        if self.cur_repo:
            self.cat_table.blockSignals(True)
            self._select_repo(self.cur_repo)
            self.cat_table.blockSignals(False)
        n_ok = sum(e["fit"] == "ok" for e in self.rated)
        if not self.cur_repo:
            self.repo_desc.setText(tr("%d modelos de %d laboratorios · %d caben en tu equipo.") % (len(self.rated), len({e["lab"] for e in self.rated}), n_ok))

    def _fit_catalog_columns(self):
        """Ancho de las columnas según su contenido, medido una sola vez (con un texto por valor distinto, no por fila)."""
        fm = self.cat_table.fontMetrics()
        hh = self.cat_table.horizontalHeader()
        for c in range(1, 6):
            texts = {self.cat_table.horizontalHeaderItem(c).text()}
            for i in range(self.cat_table.rowCount()):
                it = self.cat_table.item(i, c)
                if it:
                    texts.add(it.text())
            hh.resizeSection(c, max(fm.horizontalAdvance(t) for t in texts) + 26)

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
        self.repo_desc.setText(tr("Consultando las variantes de %s…") % repo)
        self.table.setRowCount(0)
        cat = next((e for e in (getattr(self, "rated", None) or []) if e["repo"] == repo), None)
        run_bg(lambda: P.hf_files(repo), lambda r: repo == self.cur_repo and self._got_repo(r, cat))

    def _got_repo(self, r, cat):
        if isinstance(r, Exception):
            self.repo_desc.setText(tr("No pude leer el repositorio (¿sin internet o nombre incorrecto?): %s") % r)
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
            self.repo_desc.setText(tr("Formato original de Hugging Face (%s, %d archivos) · %s · ~%s mil millones de parámetros%s. "
                                      "Jayth lo descarga y lo convierte a GGUF en tu equipo con las herramientas oficiales de llama.cpp.") % (
                                       HW.human(orig["size"]), len(orig["files"]), ci["arch"], i18n.number(ci["params"] / 1e9),
                                       (" · " + tr("con visión")) if ci["vision"] else ""))
            self.chk_mm.setEnabled(ci["vision"])
            self.chk_mm.setChecked(ci["vision"])
            self.chk_mm.setText(tr("Incluir visión (se convierte también el proyector de imágenes)") if ci["vision"] else tr("Este modelo no tiene visión (solo texto)"))
            self.chk_del_orig.show()
            self._fill_table()
            return
        self.chk_del_orig.hide()
        if not r["quants"]:
            self.repo_desc.setText(tr("Ese repositorio no contiene archivos GGUF ni el modelo en formato original."))
            self.info = None
            return
        self.info = r
        if self.base_repo is None and not self.chk_orig.isChecked():
            run_bg(lambda repo=r["repo"]: P.base_model(repo), lambda b, repo=r["repo"]: self._got_base(repo, b))
        desc = ""
        if cat:
            desc = tr("%s · %s · %s mil millones de parámetros%s.") % (
                cat["name"], _lab_txt(cat["lab"]), i18n.number(cat["params"] / 1e9),
                (" " + tr("(MoE, ~%s activos)") % i18n.number(cat["active"] / 1e9)) if cat["active"] < cat["params"] * 0.6 else "") + " "
            if cat is getattr(self, "rec_model", None):
                desc += tr("Recomendado para tu equipo: el más capaz que cabe y va fluido.") + " "
        self.repo_desc.setText(desc + tr("%d variantes disponibles.") % len(r["quants"]))
        self.chk_mm.setEnabled(bool(r["mmproj"]))
        self.chk_mm.setChecked(bool(r["mmproj"]))
        if not r["mmproj"]:
            self.chk_mm.setText(tr("Este modelo no trae proyector de visión (solo texto)"))
        else:
            self.chk_mm.setText(tr("Incluir visión (+%s): permite que vea imágenes y capturas") % HW.human(r["mmproj"][0]["size"]))
        self._fill_table()

    def _fill_table(self):
        qs = self.info["quants"]
        rec = HW.recommend_quant(qs, self.hw) if self.hw else None
        self.table.setRowCount(len(qs))
        sel = 0
        from PySide6.QtGui import QColor
        for i, q in enumerate(qs):
            got = self._have_quant(q)[1]
            name = q["label"] + ((" · " + tr("se crea al convertir")) if q.get("convert") and not got else "") + \
                (("   ★ " + tr("recomendada")) if rec is q else "") + (("   ✓ " + tr("ya descargada")) if got else "")
            it = QTableWidgetItem(name)
            it.setData(Qt.UserRole, i)
            if got:
                it.setForeground(QColor(C["ok"]))
                it.setToolTip(tr("Ya está en tu equipo: %s") % got)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(HW.human(q["size"])))
            if self.hw:
                fit = HW.classify(q["size"], self.hw, self.chk_mm.isChecked())
                fi = QTableWidgetItem(FIT_TXT[fit])
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
        got = self._have_quant(q)[1] if q else None
        if got:
            return self.disk_lbl.setText(tr("✓ Esta variante ya está descargada en %s: no se vuelve a descargar.") % got)
        free = HW.disk_free(self.dest.text() or core.models_dir(self.cfg))
        need = (q["size"] if q else 0) + (self.info["mmproj"][0]["size"] if self.info and self.info["mmproj"] and self.chk_mm.isChecked() else 0)
        warn = ("  ⚠ " + tr("no hay espacio suficiente")) if q and need > free else ""
        self.disk_lbl.setText(tr("Necesita %s · libre en esa unidad: %s%s") % (HW.human(need), HW.human(free), warn))

    # --- lo que ya está descargado (para marcarlo y no bajarlo otra vez)
    def _installed(self):
        """Modelos de tu lista cuyos archivos siguen en su sitio."""
        from . import relocate as R
        out = []
        for m in core.SET.snapshot()["models"]:
            try:
                if m.get("path") and R.files_ok(m):
                    out.append(m)
            except Exception:
                pass
        return out

    def _have_quant(self, q):
        """¿Ya hay en este equipo una copia completa de esa variante? Devuelve (modelo de tu lista o None, ruta o None):
        por la lista de modelos (mismo archivo del mismo repositorio, o mismo nombre y tamaño) o porque sus archivos
        ya están enteros en la carpeta de descarga."""
        info = self.info or {}
        repo = (info.get("repo") or "").lower()
        if not q or not repo:
            return None, None
        inst = self._installed()
        if q.get("convert"):                         # convertido en este equipo desde el original
            for m in inst:
                if (m.get("repo") or "").lower() == repo and m.get("converted_from") and \
                        (m.get("quant") or "").upper() == q["label"].upper():
                    return m, m["path"]
            return None, None
        parts = q.get("parts") or []
        if not parts:
            return None, None
        first = os.path.basename(parts[0]["file"]).lower()
        for m in inst:
            if os.path.basename(m["path"]).lower() == first and \
                    ((m.get("repo") or "").lower() == repo or int(m.get("size") or 0) == int(q["size"])):
                return m, m["path"]
        folder = os.path.join(self.dest.text() or core.models_dir(self.cfg), info["repo"].replace("/", "__"))
        files = [os.path.join(folder, os.path.basename(x["file"])) for x in parts]
        if all(os.path.isfile(f) and (not x.get("size") or os.path.getsize(f) == x["size"]) for f, x in zip(files, parts)):
            return None, files[0]
        return None, None

    def _engine_ready(self):
        return bool(self.cfg.get("setup_done")) and os.path.isfile(self.cfg.get("llama_exe") or "")

    def _offer_existing(self, m):
        """Ya lo tienes: en vez de descargarlo otra vez, se ofrece usarlo. Devuelve True si se usó."""
        box = QMessageBox(self)
        box.setWindowTitle(tr("Ya lo tienes"))
        box.setIcon(QMessageBox.Information)
        fm, name = box.fontMetrics(), os.path.basename(m["path"])               # una ruta larga, en una sola línea: se acorta
        shown = os.path.join(fm.elidedText(os.path.dirname(m["path"]), Qt.ElideMiddle, max(140, 460 - fm.horizontalAdvance(name))), name)   # la carpeta
        box.setText(tr("«%s» ya está descargado en este equipo:\n%s\n\nNo hace falta descargarlo otra vez.") % (
            core.model_title(m) + (" · " + core.model_quant(m) if core.model_quant(m) else ""), shown))
        use = box.addButton(tr("Usar este modelo"), QMessageBox.AcceptRole)
        box.addButton(tr("Elegir otro"), QMessageBox.RejectRole)
        box.setDefaultButton(use)
        box.exec()
        if box.clickedButton() is not use:
            return False
        core.SET.update({"active_model": m["id"], "llm_mode": "local"})
        self.done_lbl.setText(tr("«%s» ya estaba descargado: ahora es el modelo activo.\n\nArchivo: %s") % (core.model_title(m), m["path"]))
        self.chk_start.show()
        self.go(self.p_done)
        return True

    # --- modelo que ya tengo: GGUF, carpeta original de Hugging Face, Ollama o LM Studio
    def _pick_file(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("Elegir modelo"), os.path.dirname(self.f_model.text()) or os.path.expanduser("~"),
                                           tr("Modelos (*.gguf *.safetensors config.json);;Todos (*.*)"))
        if p:
            self.f_model.setText(os.path.normpath(p))

    def _pick_folder(self):
        p = QFileDialog.getExistingDirectory(self, tr("Elegir la carpeta del modelo"), self.f_model.text() or os.path.expanduser("~"))
        if p:
            self.f_model.setText(os.path.normpath(p))

    def _got_found(self, items):
        self.found.clear()
        if isinstance(items, Exception) or not items:
            self.found.addItem(tr("No hay modelos de Ollama ni de LM Studio en este equipo"), None)
            self.found.setEnabled(False)
            return
        self.found.addItem(tr("Elige uno (%d encontrados)…") % len(items), None)
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
            return self.f_info.setText(tr("No existe."))
        if fmt == "gguf":
            if self.local.get("mmproj") and not self.f_mm.text():
                self.f_mm.setText(self.local["mmproj"])
            return self.f_info.setText(tr("✓ GGUF listo para usar · %s") % HW.human(self.local["size"]))
        if fmt == "other" or self.local.get("why_not"):
            return self.f_info.setText("✗ " + self.local.get("why_not", tr("Formato no compatible.")))
        info = self.local
        self.f_info.setText(tr("Formato original de Hugging Face (%s, %s) · %s · ~%s mil millones de parámetros%s.") % (
            info["weights"], HW.human(info["size"]), info["arch"], i18n.number(info["params"] / 1e9), (" · " + tr("con visión")) if info["vision"] else ""))
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
            combo.addItem("%s · ~%s · %s · %s%s" % (q["label"], HW.human(q["size"]), FIT_TXT[fit], q["desc"], ("   ★ " + tr("recomendada")) if q is rec else ""), q)
        combo.setCurrentIndex(max(0, next((i for i in range(combo.count()) if combo.itemData(i) is rec), 0)))
        combo.blockSignals(False)

    def _local_space(self):
        q = self.f_quant.currentData()
        if not q or self.local.get("format") != "hf":
            return
        need, final = CV.plan_space(self.local, q["label"])
        dest = self.dest.text() or core.models_dir(self.cfg)
        free = HW.disk_free(dest)
        self.f_info.setText(tr("%s\nResultado ~%s en %s · durante la conversión hacen falta ~%s libres (hay %s)%s.") % (
            self.f_info.text().split("\n")[0], HW.human(final), dest, HW.human(need), HW.human(free),
            ("  ⚠ " + tr("no hay espacio suficiente")) if need > free else ""))

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
        self.chk_orig.setText(tr("Prefiero el formato original (%s) y convertirlo en mi equipo (descarga más grande)") % base)
        self.chk_orig.show()

    # --- externo
    def test_ext(self):
        url, key = self.e_url.text().strip().rstrip("/"), self.e_key.text().strip()
        self.e_res.setText(tr("Probando…"))

        def probe():
            import json
            req = urllib.request.Request(url + "/models", headers={"Authorization": "Bearer " + (key or "local")})
            d = json.loads(urllib.request.urlopen(req, timeout=5).read().decode("utf-8"))
            return [m.get("id") for m in d.get("data", [])]

        def done(r):
            if isinstance(r, Exception):
                self.e_res.setText(tr("✗ No responde: %s") % r)
            else:
                self.e_res.setText(tr("✓ Conectado. Modelos: %s") % (", ".join(r[:8]) or tr("(ninguno listado)")))
                if r and not self.e_model.text().strip():
                    self.e_model.setText(r[0])
        run_bg(probe, done)

    # --- tras elegir modelo
    def _after_model(self):
        if self.r_ext.isChecked():
            if not self.e_url.text().strip():
                return QMessageBox.warning(self, tr("Falta la URL"), tr("Escribe la URL del servidor."))
            core.SET.update({"llm_mode": "external", "external_url": self.e_url.text().strip(), "external_model": self.e_model.text().strip(),
                             "external_key": self.e_key.text().strip(), "setup_done": True})
            self.done_lbl.setText(tr("Usarás el servidor %s. Asegúrate de que esté encendido antes de chatear.") % self.e_url.text().strip())
            self.chk_start.hide()
            return self.go(self.p_done)
        if self.r_file.isChecked():
            fmt = (self.local or {}).get("format")
            if fmt not in ("gguf", "hf"):
                return QMessageBox.warning(self, tr("Modelo no válido"), tr("Elige un archivo .gguf o la carpeta de un modelo original de Hugging Face."))
            if self.local.get("why_not"):
                return QMessageBox.warning(self, tr("Formato no compatible"), self.local["why_not"])
            if fmt == "hf" and self.f_quant.currentData():
                need, _ = CV.plan_space(self.local, self.f_quant.currentData()["label"])
                if need > HW.disk_free(self.dest.text() or core.models_dir(self.cfg)):
                    return QMessageBox.warning(self, tr("Falta espacio"), tr("Para convertir hacen falta ~%s libres en %s.") % (
                        HW.human(need), self.dest.text() or core.models_dir(self.cfg)))
            if fmt == "gguf" and self.f_mm.text() and not os.path.isfile(self.f_mm.text()):
                return QMessageBox.warning(self, tr("Archivo no encontrado"), tr("El proyector de visión indicado no existe."))
            if fmt == "gguf" and self._engine_ready():       # ese archivo ya está en tu lista: no se añade dos veces
                p = os.path.normcase(os.path.normpath(self.local.get("path") or self.f_model.text()))
                m = next((m for m in self._installed() if os.path.normcase(os.path.normpath(m["path"])) == p), None)
                if m is not None and (not self.f_mm.text() or self.f_mm.text() == m.get("mmproj")):
                    self._offer_existing(m)              # usarlo, o quedarse aquí para elegir otro
                    return
        elif self._selected_quant() is None:
            return QMessageBox.warning(self, tr("Elige una variante"), tr("Elige un modelo de la lista y espera a que aparezcan sus variantes."))
        else:
            m, _ = self._have_quant(self._selected_quant())
            info = self.info or {}
            vision_missing = self.chk_mm.isChecked() and info.get("mmproj") and not (m and m.get("mmproj") and os.path.isfile(m["mmproj"]))
            if m is not None and self._engine_ready() and not vision_missing:
                self._offer_existing(m)                      # ya lo tenías: se usa sin descargar nada, o eliges otra variante
                return
        self.go(self.p_engine)

    def _llama_ok(self):
        """¿Ya está instalado el motor elegido? (con «Actualizar a la última versión» marcado, se vuelve a descargar)"""
        b = self.backend.currentData()
        if getattr(self, "chk_update", None) is not None and self.chk_update.isChecked():
            return False
        return os.path.isfile(self.cfg["llama_exe"]) and self.cfg["backend"] == b and \
            (b != "cuda" or (self.cfg.get("cuda_major") or "12") == self._cuda_for(b))

    def _eng_state(self):
        if self.chk_own.isChecked():
            self.eng_state.setText(tr("Se usará tu %s.") % SERVER_EXE)
        elif self._llama_ok():
            self.eng_state.setText(tr("✓ Ya instalado (%s). No hace falta descargarlo.") % (self.cfg["llama_tag"] or tr("versión local")))
        else:
            self.eng_state.setText(tr("Se descargará la última versión oficial desde GitHub (ggml-org/llama.cpp)."))

    # --- instalacion
    def _install(self):
        backend = self.backend.currentData()
        if self.chk_own.isChecked() and not os.path.isfile(self.own_exe.text()):
            return QMessageBox.warning(self, tr("Archivo no encontrado"), tr("Elige un %s existente.") % SERVER_EXE)
        job = P.Job()
        if self.chk_own.isChecked():
            exe = self.own_exe.text()
            job.add(tr("Motor: usar llama-server existente"), lambda pr, st, res: res.update(llama_exe=exe, llama_tag="propio"))
        elif self._llama_ok():
            job.add(tr("Motor: ya instalado"), lambda pr, st, res: res.update(llama_exe=self.cfg["llama_exe"], llama_tag=self.cfg["llama_tag"]))
        else:
            job.add(tr("Motor llama.cpp (%s)") % dict(BACKENDS)[backend], lambda pr, st, res: self._job_llama(backend, pr, st, res))
        threads = self.threads.value()
        m_have, have = self._have_quant(self._selected_quant()) if self.r_hf.isChecked() and self._selected_quant() else (None, None)
        if self.r_hf.isChecked() and m_have is not None and self._selected_quant().get("convert"):
            job.add(tr("Modelo %s (ya convertido)") % m_have.get("quant", ""), lambda pr, st, res: pr(1, 1, "ya descargado"))
            self.pending_model = dict(m_have)
        elif self.r_hf.isChecked() and self._selected_quant() and self._selected_quant().get("convert"):
            # formato original: descargar sus archivos, preparar el convertidor y crear el GGUF en este equipo
            q, info = self._selected_quant(), self.info
            models = self.dest.text() or core.models_dir(self.cfg)
            src = os.path.join(models, info["repo"].replace("/", "__") + "__original")
            out = os.path.join(models, info["repo"].replace("/", "__") + "__gguf")
            files = info["original"]["files"]
            big = [f for f in files if f["size"] > 50_000_000]
            small = [f for f in files if f not in big]
            job.add(tr("Archivos de configuración del original"), lambda pr, st, res: [
                P.download(P.hf_url(info["repo"], f["file"]), os.path.join(src, f["file"]), f["size"], "", pr, st) for f in small])
            for k, f in enumerate(big):
                job.add(tr("Original · parte %d de %d") % (k + 1, len(big)) if len(big) > 1 else tr("Modelo original"),
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
            out = os.path.join(self.dest.text() or core.models_dir(self.cfg), re.sub(r"[^\w.-]+", "_", info["name"]) + "__gguf")
            self._conversion_steps(job, info["path"], out, q["label"], info.get("vision"), threads, delete_src=False, name=info["name"])
            self.pending_model = {"id": re.sub(r"[^\w.-]+", "_", "local_" + info["name"] + "_" + q["label"]), "name": info["name"],
                                  "quant": q["label"], "path": "", "mmproj": "", "repo": "", "file": "", "size": int(q["size"]),
                                  "added": time.time(), "converted_from": info["path"]}
        elif self.r_hf.isChecked():
            q, info = self._selected_quant(), self.info
            if have:                                  # ya está en el equipo: se usa donde está, sin descargarlo otra vez
                folder = os.path.dirname(have)
                job.add(tr("Modelo %s (ya descargado)") % q["label"], lambda pr, st, res: pr(1, 1, "ya descargado"))
            else:
                folder = os.path.join(self.dest.text() or core.models_dir(self.cfg), info["repo"].replace("/", "__"))
                for k, part in enumerate(q["parts"]):
                    job.add(tr("Modelo %s parte %d/%d") % (q["label"], k + 1, len(q["parts"])) if len(q["parts"]) > 1 else tr("Modelo %s") % q["label"],
                            lambda pr, st, res, part=part: P.download(P.hf_url(info["repo"], part["file"]), os.path.join(folder, os.path.basename(part["file"])),
                                                                      part["size"], part["sha256"], pr, st), size=part["size"])
            mm = info["mmproj"][0] if info["mmproj"] and self.chk_mm.isChecked() else None
            mm_path = os.path.join(folder, os.path.basename(mm["file"])) if mm else ""
            if mm and m_have is not None and m_have.get("mmproj") and os.path.isfile(m_have["mmproj"]):
                mm_path = m_have["mmproj"]               # su proyector de visión también estaba
            elif mm:
                job.add(tr("Proyector de visión"), lambda pr, st, res: P.download(P.hf_url(info["repo"], mm["file"]), mm_path,
                                                                               mm["size"], mm["sha256"], pr, st), size=mm["size"])
            self.pending_model = {"id": m_have["id"] if m_have else re.sub(r"[^\w.-]+", "_", info["repo"] + "_" + q["label"]),
                                  "name": P.pretty_name(info["repo"]),
                                  "quant": quant_short(q["label"]), "path": have or os.path.join(folder, os.path.basename(q["parts"][0]["file"])),
                                  "mmproj": mm_path, "repo": info["repo"], "file": q["file"], "size": q["size"], "added": time.time()}
        else:
            p = os.path.normpath((self.local or {}).get("path") or self.f_model.text())
            same = next((m for m in self._installed() if os.path.normcase(os.path.normpath(m["path"])) == os.path.normcase(p)), None)
            self.pending_model = {"id": same["id"] if same else re.sub(r"[^\w.-]+", "_", "local_" + os.path.basename(p)),   # sin duplicados
                                  "name": (self.local or {}).get("name") or P.pretty_name(os.path.basename(p)),
                                  "quant": P.quant_label(os.path.basename(p)), "path": p, "mmproj": os.path.normpath(self.f_mm.text()) if self.f_mm.text() else "",
                                  "repo": "", "file": os.path.basename(p), "size": os.path.getsize(p), "added": time.time()}
        self.pending_cfg = {"backend": "cpu" if self.chk_own.isChecked() and backend == "cpu" else backend, "threads": self.threads.value(),
                            "n_ctx": self.ctx.currentData(), "models_dir": self.dest.text() or core.models_dir(self.cfg)}
        self._start_job(job)

    def _conversion_steps(self, job, src, out, quant, vision, threads, delete_src=False, name=""):
        """Pasos para pasar un original de Hugging Face a GGUF: herramientas (una vez), conversion y reduccion, vision."""
        def tools(pr, st, res):
            exe = res.get("llama_exe") or self.cfg["llama_exe"]
            if CV.tools_ready(CV.llama_build(exe)):
                pr(1, 1, tr("ya preparadas"))
                return
            CV.ensure_tools(exe, pr, st)

        def conv(pr, st, res):
            exe = res.get("llama_exe") or self.cfg["llama_exe"]
            model, mm = CV.convert_model(src, out, quant, exe, vision=vision, threads=threads, progress=pr, stop=st, name=name)
            res.update(model_path=model, mmproj_path=mm)
            if delete_src:
                shutil.rmtree(src, ignore_errors=True)
        job.add(tr("Herramientas de conversión (solo la primera vez)"), tools)
        job.add(tr("Convertir a GGUF y crear la variante %s%s") % (quant, (" + " + tr("visión")) if vision else ""), conv)

    def _job_llama(self, backend, pr, st, res):
        cuda = self._cuda_for(backend)
        exe, tag = P.install_llama(backend, cuda, pr, st)
        res.update(llama_exe=exe, llama_tag=tag, cuda_major=cuda)

    def _cuda_for(self, backend):
        """Con CUDA, la versión que admite este equipo (13 o 12); si aún no se sabe, la recomendada al detectarlo."""
        if backend != "cuda":
            return ""
        return ((getattr(self, "hw", None) or {}).get("engine") or {}).get("cuda") or "12"

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
        self.ov_det = lbl(tr("Preparando…"), "muted")
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
        self.setWindowTitle(tr("%d %% · Descargando · Asistente de configuración") % int(100 * frac) if not j.finished else tr("Asistente de configuración"))
        if j.finished:
            self.timer.stop()
            if j.error:
                self.prog_err.setText(j.error)
                self.prog_err.show()
                self.b_next.setText(tr("Reintentar"))
                self.b_next.setEnabled(True)
                self.b_next.clicked.disconnect()
                self.b_next.clicked.connect(self._retry)
                self.b_cancel.setText(tr("Cerrar"))
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
        rec = ((getattr(self, "hw", None) or {}).get("engine") or {}).get("backend")
        extra = {"backend_auto": rec is None or rec == self.pending_cfg["backend"]}     # elegido a mano otro motor: no se le propone
        if "cuda_major" in res:
            extra["cuda_major"] = res["cuda_major"]
        core.SET.update(dict(self.pending_cfg, llama_exe=res["llama_exe"], llama_tag=res.get("llama_tag", ""), llm_mode="local",
                             setup_done=True, **extra))
        core.LLM_MGR.cpu_only = False
        core.SET.add_model(self.pending_model, activate=True)
        self.done_lbl.setText(tr("Modelo «%s» instalado y activo.\n\nArchivo: %s%s\nMotor: %s (%s)") % (
            self.pending_model["name"], self.pending_model["path"],
            ("\n" + tr("Visión: %s") % self.pending_model["mmproj"]) if self.pending_model["mmproj"] else "",
            dict(BACKENDS)[self.pending_cfg["backend"]], res.get("llama_tag") or "local"))
        self.history.clear()
        self.go(self.p_done, push=False)


def quant_short(label):
    return label.replace("   ★ recomendada", "")


# ---------------------------------------------------------------- gestor de modelos
class ModelsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Modelos"))
        self.resize(760, 420)
        v = QVBoxLayout(self)
        v.addWidget(lbl(tr("Modelos instalados"), "h1"))
        v.addWidget(lbl(tr("El modelo activo es el que usa el agente. Cambiarlo apaga el modelo actual."), "muted"))
        self.t = QTableWidget(0, 6)
        self.t.setHorizontalHeaderLabels(["", tr("Modelo"), tr("Tipo"), tr("Variante"), tr("Tamaño"), tr("Archivo")])
        self.t.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.t.verticalHeader().setVisible(False)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t.setSelectionMode(QAbstractItemView.SingleSelection)
        self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t.setWordWrap(False)
        self.t.setTextElideMode(Qt.ElideMiddle)      # rutas largas: se ve el principio y el nombre del archivo
        self.t.doubleClicked.connect(self.activate)
        self.t.itemSelectionChanged.connect(self._sel_changed)
        v.addWidget(self.t, 1)
        self.note = lbl("", "muted")
        self.note.setWordWrap(True)
        self.note.hide()
        v.addWidget(self.note)
        row = QHBoxLayout()
        row.addWidget(btn(tr("Usar este"), "primary", self.activate, "ui_check"))
        row.addWidget(btn(tr("Añadir modelo…"), cb=self.add, ico="acc_anadir"))
        self.b_locate = btn(tr("Localizar…"), cb=self.locate, ico="acc_buscar")
        self.b_locate.setToolTip(tr("Indicar dónde está ahora el archivo de este modelo (si lo moviste de carpeta o de disco)"))
        row.addWidget(self.b_locate)
        b_scan = btn(tr("Buscar en una carpeta…"), cb=self.scan_folder, ico="act_carpeta_abierta")
        b_scan.setToolTip(tr("Enlazar los modelos que moviste a esa carpeta y añadir los que haya dentro"))
        row.addWidget(b_scan)
        row.addStretch(1)
        row.addWidget(btn(tr("Abrir carpeta"), cb=self.open_folder, ico="act_carpeta_abierta"))
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(btn(tr("Quitar de la lista"), cb=lambda: self.remove(False), ico="ui_cerrar"))
        row2.addWidget(btn(tr("Borrar archivos…"), "danger", lambda: self.remove(True), "acc_eliminar"))
        row2.addStretch(1)
        row2.addWidget(btn(tr("Cerrar"), cb=self.accept))
        v.addLayout(row2)
        self.changed = False
        self.states = {}                 # id -> lo que se sabe de un modelo cuyo archivo falta
        self._stop = False
        self._caps_busy = False
        self.refresh()
        self._sel_changed()
        from . import relocate as R
        if R.problems(core.SET.snapshot()):
            self._search("quick")

    # --- modelos que no están en su sitio
    def _search(self, level, folders=None, add_new=False, explicit=False):
        from . import relocate as R
        miss = R.problems(core.SET.snapshot())
        for m in miss:
            self.states[m["id"]] = tr("buscando…")
        if miss:
            self.note.setText(tr("Buscando %s en %s…") % (
                tr("«%s»") % core.model_title(miss[0]) if len(miss) == 1 else tr("%d modelos") % len(miss),
                tr("tus discos (puede tardar unos minutos)") if level == "deep" else tr("las carpetas habituales")))
            self.note.show()
        self.refresh()
        run_bg(lambda: R.run(level, folders, add_new, explicit, stop=lambda: self._stop),
               lambda rep: self._found(rep, level))

    def _found(self, rep, level):
        from . import relocate as R
        if self._stop:
            return
        if isinstance(rep, Exception):
            rep = {"missing": [], "error": str(rep)}
        if R.summary(rep):
            self.changed = True
        self.states = {}
        for mid, (st, drive) in (rep.get("by_id") or {}).items():
            self.states[mid] = {"copying": tr("se está copiando"), "offline": tr("el disco %s no está conectado") % drive,
                                "missing": tr("buscando…") if level != "deep" else tr("archivo no encontrado")}.get(st, "")
        text = " ".join(x for x in (R.summary(rep), R.pending_text(rep) if level == "deep" or not rep.get("missing") else "") if x)
        self.note.setText(text)
        self.note.setVisible(bool(text))
        self.refresh()
        if rep.get("missing") and level != "deep":
            self._search("deep")

    def _sel_changed(self):
        from . import relocate as R
        m = self._sel()
        self.b_locate.setEnabled(bool(m) and (not R.files_ok(m) or bool(m.get("mmproj") and not os.path.isfile(m["mmproj"]))))

    def locate(self):
        from . import relocate as R
        m = self._sel()
        if not m:
            return
        start = os.path.dirname(m.get("path", "")) if os.path.isdir(os.path.dirname(m.get("path", ""))) else core.models_dir()
        if not R.files_ok(m):
            p, _ = QFileDialog.getOpenFileName(self, tr("¿Dónde está ahora «%s»?") % core.model_title(m), start,
                                               tr("Modelo GGUF (%s);;Modelos GGUF (*.gguf)") % (os.path.basename(m.get("path", "")) or "*.gguf"))
            if not p:
                return
            err = R.relink(m["id"], os.path.normpath(p))
            if err:
                return QMessageBox.warning(self, tr("No se pudo usar ese archivo"), err)
        else:                            # solo falta el proyector de visión
            p, _ = QFileDialog.getOpenFileName(self, tr("¿Dónde está el proyector de visión de «%s»?") % core.model_title(m), start,
                                               tr("Proyector de visión (*mmproj*.gguf);;Modelos GGUF (*.gguf)"))
            if not p:
                return
            core.SET.update_model(m["id"], mmproj=os.path.normpath(p), mmproj_sig=R.sig(p))
        self.states.pop(m["id"], None)
        self.changed = True
        self.note.setText(tr("Listo: «%s» vuelve a apuntar a su archivo.") % core.model_title(m))
        self.note.show()
        self.refresh()

    def scan_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta donde están tus modelos"), core.models_dir())
        if d:
            self._search("guess", folders=[os.path.normpath(d)], add_new=True, explicit=True)

    def done(self, r):
        self._stop = True                # la búsqueda en segundo plano se detiene al cerrar
        super().done(r)

    def refresh(self):
        cfg = core.SET.snapshot()
        ms = cfg["models"]
        self.t.setRowCount(len(ms))
        from . import relocate as R
        todo = []
        for i, m in enumerate(ms):
            ok = R.files_ok(m)
            self.t.setItem(i, 0, QTableWidgetItem("●" if m["id"] == cfg["active_model"] else ""))
            st = self.states.get(m["id"]) or ("" if ok else tr("archivo no encontrado"))
            name = QTableWidgetItem(core.model_title(m) + ("  (%s)" % st if st else ""))
            if st:
                name.setForeground(QColor(C["warn"]))
                name.setToolTip(tr("Estaba en: %s\nPulsa «Localizar…» si sabes dónde está ahora.") % m.get("path", ""))
            self.t.setItem(i, 1, name)
            caps = core.model_caps(m, compute=False) if ok else None      # leído del propio archivo (y guardado)
            if ok and caps is None:
                todo.append(m)
            ki = QTableWidgetItem(core.caps_text(caps) if caps else (tr("leyendo…") if ok else "—"))
            if caps:
                ki.setForeground(QColor(C["acc"] if caps.get("tools") else C["warn"]))
                tip = [tr("Agente: sabe usar herramientas (archivos, comandos, web…)") if caps.get("tools") else
                       tr("No usa herramientas: puedes conversar con él, pero el agente no podrá actuar")]
                tip.append(tr("Visión: tiene su proyector de imágenes") if caps.get("vision") else tr("Sin visión (no tiene proyector de imágenes)"))
                if caps.get("think"):
                    tip.append(tr("Razona antes de responder"))
                if caps.get("ctx"):
                    tip.append(tr("Contexto máximo del modelo: %s tokens") % format(caps["ctx"], ",").replace(",", "."))
                tip.append(tr("(Leído de la plantilla dentro del archivo)") if caps.get("source") == "gguf" else tr("(Deducido del nombre)"))
                ki.setToolTip("\n".join(tip))
            self.t.setItem(i, 2, ki)
            self.t.setItem(i, 3, QTableWidgetItem(core.model_quant(m)))
            self.t.setItem(i, 4, QTableWidgetItem(HW.human(m.get("size", 0))))
            self.t.setItem(i, 5, QTableWidgetItem(m.get("path", "")))
            self.t.item(i, 5).setToolTip(m.get("path", ""))
        for c in (0, 1, 2, 3, 4):
            self.t.resizeColumnToContents(c)
        if todo and not self._caps_busy:     # el tipo se lee del archivo (1-2 s por modelo): en segundo plano
            self._caps_busy = True

            def got(_):
                self._caps_busy = False
                if not self._stop:
                    self.refresh()
            run_bg(lambda: [core.model_caps(m) for m in todo], got)

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
            caps = core.model_caps(m, compute=False)
            if caps and not caps.get("tools"):
                QMessageBox.information(self, tr("Modelo sin herramientas"),
                                        tr("«%s» no usa herramientas: podrás conversar con él, pero el agente no podrá trabajar con "
                                           "archivos, comandos ni la web. Para eso elige un modelo agéntico.") % core.model_title(m))

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
                return QMessageBox.information(self, tr("Sin archivos"), tr("No hay archivos que borrar; solo se quitará de la lista."))
            txt = tr("Se borrarán permanentemente %d archivo(s) (%s):\n\n%s\n\nNo se puede deshacer. ¿Continuar?") % (
                len(files), HW.human(sum(os.path.getsize(f) for f in files)), "\n".join(files))
            if QMessageBox.question(self, tr("Borrar archivos del modelo"), txt) != QMessageBox.StandardButton.Yes:
                return
            if m["id"] == core.SET.snapshot()["active_model"]:
                core.LLM_MGR.stop()
            for f in files:
                try:
                    os.remove(f)
                except OSError as e:
                    QMessageBox.warning(self, tr("No se pudo borrar"), str(e))
        elif m.get("path") and os.path.isfile(m["path"]):
            # quitado de la lista sin borrar: que la revisión de la carpeta de modelos no lo vuelva a añadir
            ign = core.SET.snapshot().get("models_ignored") or []
            core.SET.update({"models_ignored": ign + [m["path"]]})
        core.SET.remove_model(m["id"])
        self.changed = True
        self.refresh()
