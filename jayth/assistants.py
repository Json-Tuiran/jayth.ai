# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Asistentes y habilidades.

- Asistente: un «perfil» de Jayth con nombre, instrucciones propias y archivos de referencia (como los GPTs, Gems o
  Proyectos). Se elige al empezar una conversación y el agente trabaja con esas instrucciones y ese conocimiento.
- Habilidad: instrucciones reutilizables para un tipo de tarea, guardadas en una carpeta con un archivo SKILL.md
  (nombre, descripción e instrucciones; mismo formato que las «Agent Skills»). El modelo solo ve la lista con sus
  descripciones y carga las instrucciones completas con use_skill cuando una tarea encaja: así no gastan contexto.
"""
import os, re, uuid, shutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem, QWidget,
                               QTabWidget, QFileDialog, QMessageBox, QCheckBox)
from . import APP_NAME, core, paths
from .wizard import btn, lbl

SKILLS_DIR = os.path.join(paths.DATA, "skills")
KNOWLEDGE_LIMIT = 12000          # caracteres de archivos de referencia que van directos a las instrucciones


# ---------------------------------------------------------------- asistentes
def all_assistants(cfg=None):
    return list((cfg or core.SET.snapshot()).get("assistants") or [])


def get(aid, cfg=None):
    return next((a for a in all_assistants(cfg) if a["id"] == aid), None) if aid else None


def instructions_for(a):
    """Texto que se añade a las instrucciones del agente cuando la conversación usa este asistente."""
    out = ["Actúas como el asistente «%s»." % a["name"]]
    if a.get("instructions", "").strip():
        out.append("Instrucciones del asistente:\n" + a["instructions"].strip())
    files = [f for f in a.get("files") or [] if os.path.isfile(f)]
    if files:
        left, parts, rest = KNOWLEDGE_LIMIT, [], []
        for f in files:
            if left <= 300:
                rest.append(f)
                continue
            txt = core.attachments_text([f])
            if len(txt) > left:
                txt = txt[:left] + "\n…[cortado: lee el resto con read_file o read_document en %s]" % f
            parts.append(txt)
            left -= len(txt)
        out.append("Archivos de referencia del asistente (úsalos como fuente principal):\n\n" + "\n\n".join(parts))
        if rest:
            out.append("Otros archivos de referencia (léelos con read_file o read_document si hacen falta):\n" + "\n".join("- " + f for f in rest))
    return "\n\n".join(out)


# ---------------------------------------------------------------- habilidades
def _parse(path):
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    name, desc, body = "", "", text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            k, _, val = line.partition(":")
            k, val = k.strip().lower(), val.strip().strip("\"'")
            if k == "name":
                name = val
            elif k == "description":
                desc = val
    folder = os.path.dirname(path)
    return {"name": name or os.path.basename(folder), "description": desc, "body": body.strip(), "path": path, "folder": folder,
            "id": os.path.basename(folder)}


def all_skills():
    out = []
    if os.path.isdir(SKILLS_DIR):
        for d in sorted(os.listdir(SKILLS_DIR)):
            p = os.path.join(SKILLS_DIR, d, "SKILL.md")
            s = _parse(p) if os.path.isfile(p) else None
            if s:
                out.append(s)
    return out


def enabled_skills(cfg=None):
    off = set((cfg or core.SET.snapshot()).get("skills_disabled") or [])
    return [s for s in all_skills() if s["id"] not in off]


def skills_prompt(cfg=None):
    """Lista breve para las instrucciones del modelo (las instrucciones completas se cargan con use_skill)."""
    sk = enabled_skills(cfg)
    if not sk:
        return ""
    return ("Antes de una tarea que encaje con una de estas habilidades, carga sus instrucciones con use_skill(nombre) y síguelas:\n"
            + "\n".join("- %s: %s" % (s["name"], s["description"] or "(sin descripción)") for s in sk))


def find_skill(name):
    q = re.sub(r"[\s_-]+", "", str(name or "").lower())
    for s in enabled_skills():
        if q and q in (re.sub(r"[\s_-]+", "", s["name"].lower()), re.sub(r"[\s_-]+", "", s["id"].lower())):
            return s
    return None


def save_skill(name, description, body, old_id=None):
    sid = re.sub(r"[^a-z0-9áéíóúñ]+", "-", name.strip().lower()).strip("-")[:48] or "habilidad"
    folder = os.path.join(SKILLS_DIR, sid)
    if old_id and old_id != sid and os.path.isdir(os.path.join(SKILLS_DIR, old_id)):
        if os.path.exists(folder):
            raise ValueError("Ya existe una habilidad con ese nombre.")
        os.rename(os.path.join(SKILLS_DIR, old_id), folder)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n\n%s\n" % (name.strip(), description.strip().replace("\n", " "), body.strip()))
    return sid


def import_skill(src):
    """Importa una carpeta con SKILL.md (o un .md suelto). Devuelve el id."""
    if os.path.isdir(src):
        if not os.path.isfile(os.path.join(src, "SKILL.md")):
            raise ValueError("Esa carpeta no tiene un archivo SKILL.md.")
        sid = re.sub(r"[^\w-]+", "-", os.path.basename(src.rstrip("\\/")).lower()) or "habilidad"
        dst = os.path.join(SKILLS_DIR, sid)
        if os.path.exists(dst):
            raise ValueError("Ya existe una habilidad llamada «%s»." % sid)
        shutil.copytree(src, dst)
        return sid
    s = _parse(src) or {}
    name = s.get("name") if s.get("name") and s.get("name") != os.path.basename(os.path.dirname(src)) else os.path.splitext(os.path.basename(src))[0]
    return save_skill(name, s.get("description", ""), s.get("body", ""))


EXAMPLES = [
    ("Informe profesional", "Redactar informes o resúmenes ejecutivos claros y bien estructurados, y entregarlos como documento Word o PDF.",
     "# Informe profesional\n\n1. Pregunta (ask_user) para quién es el informe y qué decisión debe ayudar a tomar, si no está claro.\n"
     "2. Reúne los datos: lee los archivos indicados (read_document, read_file) y, si hay tablas, calcúlalas con run_python.\n"
     "3. Estructura: resumen de 3-5 líneas al principio, hallazgos con cifras, conclusiones y próximos pasos.\n"
     "4. Estilo: frases cortas, sin relleno, cada afirmación con su dato. Tablas para comparar; un gráfico si aclara.\n"
     "5. Entrega con create_document (.docx salvo que pidan PDF) y di dónde quedó.\n"),
    ("Revisión de código", "Revisar código en busca de errores, riesgos y mejoras antes de darlo por bueno.",
     "# Revisión de código\n\n1. Lee los archivos completos antes de opinar (read_file); no supongas lo que no has leído.\n"
     "2. Busca, en este orden: errores que rompen, casos límite sin tratar, problemas de seguridad, código duplicado y nombres confusos.\n"
     "3. Si hay pruebas, ejecútalas (run_command) y cita el resultado real.\n"
     "4. Responde con una lista ordenada por gravedad: archivo y línea, qué pasa, por qué importa y el arreglo propuesto.\n"
     "5. No cambies nada sin que te lo pidan; ofrece aplicar los arreglos al final.\n"),
]


# ---------------------------------------------------------------- diálogo
class AssistantsDialog(QDialog):
    def __init__(self, parent=None, tab=0):
        super().__init__(parent)
        self.setWindowTitle("Asistentes y habilidades")
        self.resize(900, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        self.tabs.addTab(self._assistants_tab(), "Asistentes")
        self.tabs.addTab(self._skills_tab(), "Habilidades")
        self.tabs.setCurrentIndex(tab)
        foot = QHBoxLayout()
        self.msg = lbl("", "faint")
        foot.addWidget(self.msg, 1)
        foot.addWidget(btn("Cerrar", "primary", self.accept))
        v.addLayout(foot)

    # ---- asistentes
    def _assistants_tab(self):
        w = QWidget()
        h = QHBoxLayout(w)
        left = QVBoxLayout()
        self.a_list = QListWidget()
        self.a_list.setObjectName("history")
        self.a_list.setFixedWidth(230)
        self.a_list.currentRowChanged.connect(self._a_pick)
        left.addWidget(self.a_list, 1)
        left.addWidget(btn("Nuevo asistente", None, self._a_new, "acc_anadir"))
        h.addLayout(left)
        f = QVBoxLayout()
        f.addWidget(lbl("Un asistente es %s con unas instrucciones y unos archivos de referencia fijos: un corrector de estilo, "
                        "un experto en tu producto, un tutor… Se elige al empezar una conversación." % APP_NAME, "faint"))
        f.addWidget(QLabel("Nombre"))
        self.a_name = QLineEdit()
        self.a_name.setPlaceholderText("Ej.: Corrector de estilo")
        f.addWidget(self.a_name)
        f.addWidget(QLabel("Instrucciones"))
        self.a_inst = QPlainTextEdit()
        self.a_inst.setPlaceholderText("Qué hace, cómo responde, qué debe evitar…")
        f.addWidget(self.a_inst, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Archivos de referencia"), 1)
        row.addWidget(btn("Añadir archivos…", None, self._a_files, "acc_nuevo"))
        f.addLayout(row)
        self.a_files = QListWidget()
        self.a_files.setObjectName("history")
        self.a_files.setFixedHeight(96)
        self.a_files.setToolTip("Doble clic para quitar un archivo")
        self.a_files.itemDoubleClicked.connect(lambda it: self.a_files.takeItem(self.a_files.row(it)))
        f.addWidget(self.a_files)
        row = QHBoxLayout()
        self.a_del = btn("Quitar asistente", "danger", self._a_delete)
        row.addWidget(self.a_del)
        row.addStretch(1)
        row.addWidget(btn("Guardar asistente", "primary", self._a_save))
        f.addLayout(row)
        h.addLayout(f, 1)
        self.a_cur = None
        self._a_reload()
        return w

    def _a_reload(self, select=None):
        self.a_list.blockSignals(True)
        self.a_list.clear()
        for a in all_assistants():
            it = QListWidgetItem(a["name"])
            it.setData(Qt.UserRole, a["id"])
            self.a_list.addItem(it)
            if a["id"] == select:
                self.a_list.setCurrentItem(it)
        self.a_list.blockSignals(False)
        if select is None:
            if self.a_list.count():
                self.a_list.setCurrentRow(0)
            else:
                self._a_new()

    def _a_pick(self, row):
        a = get(self.a_list.item(row).data(Qt.UserRole)) if row >= 0 else None
        if not a:
            return
        self.a_cur = a["id"]
        self.a_name.setText(a["name"])
        self.a_inst.setPlainText(a.get("instructions", ""))
        self.a_files.clear()
        for fp in a.get("files") or []:
            self._a_add_file(fp)
        self.a_del.show()

    def _a_add_file(self, fp):
        it = QListWidgetItem(os.path.basename(fp) + ("" if os.path.isfile(fp) else "  (no encontrado)"))
        it.setData(Qt.UserRole, fp)
        it.setToolTip(fp)
        self.a_files.addItem(it)

    def _a_new(self):
        self.a_cur = None
        self.a_list.blockSignals(True)
        self.a_list.setCurrentRow(-1)
        self.a_list.blockSignals(False)
        self.a_name.clear()
        self.a_inst.clear()
        self.a_files.clear()
        self.a_del.hide()
        self.a_name.setFocus()

    def _a_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Archivos de referencia", core.SET.snapshot()["workspace"],
                                                "Documentos y texto (*.txt *.md *.pdf *.docx *.xlsx *.pptx *.csv *.json *.html *.py);;Todos (*.*)")
        have = {self.a_files.item(i).data(Qt.UserRole) for i in range(self.a_files.count())}
        for fp in files:
            if os.path.normpath(fp) not in have:
                self._a_add_file(os.path.normpath(fp))

    def _a_save(self):
        name = self.a_name.text().strip()
        if not name:
            return self.msg.setText("Ponle un nombre al asistente.")
        items = all_assistants()
        a = next((x for x in items if x["id"] == self.a_cur), None)
        if a is None:
            a = {"id": uuid.uuid4().hex[:8]}
            items.append(a)
        a.update({"name": name, "instructions": self.a_inst.toPlainText().strip(),
                  "files": [self.a_files.item(i).data(Qt.UserRole) for i in range(self.a_files.count())]})
        core.SET.update({"assistants": items})
        self.a_cur = a["id"]
        self._a_reload(a["id"])
        self.a_del.show()
        self.msg.setText("✓ Asistente guardado. Elígelo con el botón + de la barra del mensaje.")

    def _a_delete(self):
        a = get(self.a_cur)
        if a and QMessageBox.question(self, "Quitar asistente", "¿Quitar el asistente «%s»?" % a["name"]) == QMessageBox.StandardButton.Yes:
            core.SET.update({"assistants": [x for x in all_assistants() if x["id"] != a["id"]]})
            self._a_reload()

    # ---- habilidades
    def _skills_tab(self):
        w = QWidget()
        h = QHBoxLayout(w)
        left = QVBoxLayout()
        self.s_list = QListWidget()
        self.s_list.setObjectName("history")
        self.s_list.setFixedWidth(230)
        self.s_list.currentRowChanged.connect(self._s_pick)
        left.addWidget(self.s_list, 1)
        left.addWidget(btn("Nueva habilidad", None, self._s_new, "acc_anadir"))
        left.addWidget(btn("Importar…", None, self._s_import, "acc_descargar"))
        self.s_ex = btn("Añadir ejemplos", None, self._s_examples)
        left.addWidget(self.s_ex)
        h.addLayout(left)
        f = QVBoxLayout()
        f.addWidget(lbl("Una habilidad son instrucciones para un tipo de tarea (cómo hacer un informe, cómo revisar código…). "
                        "El agente ve la lista y carga la que encaje con lo que le pidas, sin gastar memoria con las demás.", "faint"))
        f.addWidget(QLabel("Nombre"))
        self.s_name = QLineEdit()
        f.addWidget(self.s_name)
        f.addWidget(QLabel("Cuándo usarla (el agente decide con esta descripción)"))
        self.s_desc = QLineEdit()
        self.s_desc.setPlaceholderText("Ej.: Redactar informes ejecutivos y entregarlos en Word")
        f.addWidget(self.s_desc)
        f.addWidget(QLabel("Instrucciones"))
        self.s_body = QPlainTextEdit()
        f.addWidget(self.s_body, 1)
        row = QHBoxLayout()
        self.s_on = QCheckBox("Activa")
        self.s_on.setChecked(True)
        row.addWidget(self.s_on)
        self.s_del = btn("Quitar", "danger", self._s_delete)
        row.addWidget(self.s_del)
        self.s_open = btn("Abrir carpeta", None, lambda: self.s_cur and __import__("jayth.osys", fromlist=["x"]).open_path(os.path.join(SKILLS_DIR, self.s_cur)))
        row.addWidget(self.s_open)
        row.addStretch(1)
        row.addWidget(btn("Guardar habilidad", "primary", self._s_save))
        f.addLayout(row)
        h.addLayout(f, 1)
        self.s_cur = None
        self._s_reload()
        return w

    def _s_reload(self, select=None):
        off = set(core.SET.snapshot().get("skills_disabled") or [])
        self.s_list.blockSignals(True)
        self.s_list.clear()
        for s in all_skills():
            it = QListWidgetItem(s["name"] + ("  (apagada)" if s["id"] in off else ""))
            it.setData(Qt.UserRole, s["id"])
            it.setToolTip(s["description"])
            self.s_list.addItem(it)
            if s["id"] == select:
                self.s_list.setCurrentItem(it)
        self.s_list.blockSignals(False)
        self.s_ex.setVisible(not any(s["name"] == EXAMPLES[0][0] for s in all_skills()))
        if select is None:
            if self.s_list.count():
                self.s_list.setCurrentRow(0)
            else:
                self._s_new()

    def _s_pick(self, row):
        sid = self.s_list.item(row).data(Qt.UserRole) if row >= 0 else None
        s = next((x for x in all_skills() if x["id"] == sid), None)
        if not s:
            return
        self.s_cur = s["id"]
        self.s_name.setText(s["name"])
        self.s_desc.setText(s["description"])
        self.s_body.setPlainText(s["body"])
        self.s_on.setChecked(s["id"] not in set(core.SET.snapshot().get("skills_disabled") or []))
        self.s_del.show()
        self.s_open.show()

    def _s_new(self):
        self.s_cur = None
        self.s_list.blockSignals(True)
        self.s_list.setCurrentRow(-1)
        self.s_list.blockSignals(False)
        for w in (self.s_name, self.s_desc):
            w.clear()
        self.s_body.clear()
        self.s_on.setChecked(True)
        self.s_del.hide()
        self.s_open.hide()

    def _s_save(self):
        name = self.s_name.text().strip()
        if not name or not self.s_body.toPlainText().strip():
            return self.msg.setText("La habilidad necesita un nombre y unas instrucciones.")
        try:
            sid = save_skill(name, self.s_desc.text(), self.s_body.toPlainText(), self.s_cur)
        except ValueError as e:
            return self.msg.setText("✗ %s" % e)
        off = set(core.SET.snapshot().get("skills_disabled") or []) - {self.s_cur, sid}
        if not self.s_on.isChecked():
            off.add(sid)
        core.SET.update({"skills_disabled": sorted(x for x in off if x)})
        self.s_cur = sid
        self._s_reload(sid)
        self.s_del.show()
        self.s_open.show()
        self.msg.setText("✓ Habilidad guardada.")

    def _s_delete(self):
        if self.s_cur and QMessageBox.question(self, "Quitar habilidad", "¿Quitar esta habilidad y su carpeta?") == QMessageBox.StandardButton.Yes:
            shutil.rmtree(os.path.join(SKILLS_DIR, self.s_cur), ignore_errors=True)
            self._s_reload()

    def _s_import(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de la habilidad (con SKILL.md)", os.path.expanduser("~"))
        if not d:
            return
        try:
            self._s_reload(import_skill(d))
            self.msg.setText("✓ Habilidad importada.")
        except (ValueError, OSError) as e:
            self.msg.setText("✗ %s" % e)

    def _s_examples(self):
        for name, desc, body in EXAMPLES:
            if not any(s["name"] == name for s in all_skills()):
                save_skill(name, desc, body)
        self._s_reload()
        self.msg.setText("✓ Ejemplos añadidos: edítalos a tu gusto.")
