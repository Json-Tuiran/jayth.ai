# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Vistas de lectura del editor de Jayth Code.

- Markdown formateado (títulos, listas, tablas, código, imágenes relativas) en una columna cómoda de leer.
- Documentos de Office en modo lectura: Word (títulos, negrita, listas, tablas, imágenes, enlaces), Excel (cada hoja
  como tabla, fechas y números legibles) y PowerPoint (cada diapositiva como una tarjeta con su título, viñetas,
  tablas e imágenes).
- PDF con el visor del navegador integrado (páginas y zoom); sin navegador, su texto.
- Imágenes ajustadas a la ventana con zoom; SVG dibujado; HTML como página; CSV como tabla.
Las de texto (Markdown, HTML, SVG, CSV) también se pueden ver como código y editar; las demás son de solo lectura."""
import os, re, csv, html, io, zipfile, hashlib, datetime, posixpath
import xml.etree.ElementTree as ET
from PySide6.QtCore import Qt, QUrl, QSize, Signal, QByteArray
from PySide6.QtGui import QPixmap, QPainter, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QScrollArea, QFrame, QToolButton, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView, QSizePolicy)
from . import paths, osys
from .theme import C, icon

TEXT_PREVIEW = {".md", ".markdown", ".html", ".htm", ".svg", ".csv"}      # texto con vista previa (y «Código» para editarlo)
DOCS = {".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pdf"}             # solo lectura
DOC_KIND = {".docx": "Documento de Word", ".docm": "Documento de Word", ".xlsx": "Hoja de Excel", ".xlsm": "Hoja de Excel",
            ".pptx": "Presentación de PowerPoint", ".pdf": "Documento PDF", ".md": "Markdown", ".markdown": "Markdown",
            ".html": "Página web", ".htm": "Página web", ".svg": "Dibujo SVG", ".csv": "Tabla CSV"}
MAX_DOC = 80 * 1024 * 1024

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def esc(s):
    return html.escape(s or "", quote=True)


# ---------------------------------------------------------------- utilidades de los paquetes de Office (zip + xml)
def _xml(z, name):
    try:
        return ET.fromstring(z.read(name))
    except (KeyError, ET.ParseError):
        return None


def _rels(z, name):
    """Relaciones de una parte del paquete: {id: ruta dentro del zip (o URL externa)}."""
    folder, base = posixpath.split(name)
    root = _xml(z, posixpath.join(folder, "_rels", base + ".rels"))
    out = {}
    if root is None:
        return out
    for r in root.iter(PR + "Relationship"):
        t = r.get("Target") or ""
        if r.get("TargetMode") == "External":
            out[r.get("Id")] = t
        else:
            out[r.get("Id")] = posixpath.normpath(posixpath.join(folder, t)).lstrip("/") if not t.startswith("/") else t.lstrip("/")
    return out


def _cache_dir(path):
    try:
        key = "%s|%s" % (os.path.abspath(path), os.path.getmtime(path))
    except OSError:
        key = path
    d = os.path.join(paths.DATA, "cache", "vistas", hashlib.sha1(key.encode("utf-8")).hexdigest()[:16])
    os.makedirs(d, exist_ok=True)
    return d


def _media(z, name, cache):
    """Saca una imagen del documento a la caché y devuelve su URL local (o None)."""
    try:
        data = z.read(name)
    except KeyError:
        return None
    dst = os.path.join(cache, re.sub(r"[^\w.-]", "_", name))
    if not os.path.isfile(dst):
        with open(dst, "wb") as f:
            f.write(data)
    if dst.lower().endswith((".emf", ".wmf")):                # formatos de Windows que no se pueden dibujar aquí
        return None
    return QUrl.fromLocalFile(dst).toString()


# ---------------------------------------------------------------- Word
def docx_html(path):
    cache = _cache_dir(path)
    with zipfile.ZipFile(path) as z:
        doc = _xml(z, "word/document.xml")
        if doc is None:
            raise ValueError("no es un documento de Word válido")
        rels = _rels(z, "word/document.xml")
        styles, style_num, based = {}, {}, {}
        st = _xml(z, "word/styles.xml")
        if st is not None:
            for s in st.iter(W + "style"):
                sid = s.get(W + "styleId")
                n = s.find(W + "name")
                styles[sid] = (n.get(W + "val") if n is not None else "").lower()
                b = s.find(W + "basedOn")
                if b is not None:
                    based[sid] = b.get(W + "val")
                npr = s.find(W + "pPr/" + W + "numPr")         # estilos de lista («List Bullet», «Lista con viñetas»…)
                if npr is not None and npr.find(W + "numId") is not None:
                    il = npr.find(W + "ilvl")
                    style_num[sid] = (npr.find(W + "numId").get(W + "val"), il.get(W + "val") if il is not None else "0")

        def num_of_style(sid):
            for _ in range(8):                           # el estilo puede heredar la lista de otro
                if not sid:
                    return None
                if sid in style_num:
                    return style_num[sid]
                sid = based.get(sid)
            return None
        fmts = {}                                       # (numId, nivel) -> formato de la lista
        nb = _xml(z, "word/numbering.xml")
        if nb is not None:
            absf = {}
            for an in nb.iter(W + "abstractNum"):
                for lvl in an.iter(W + "lvl"):
                    f = lvl.find(W + "numFmt")
                    absf[(an.get(W + "abstractNumId"), lvl.get(W + "ilvl"))] = f.get(W + "val") if f is not None else "bullet"
            for num in nb.iter(W + "num"):
                a = num.find(W + "abstractNumId")
                if a is not None:
                    for (aid, lv), f in absf.items():
                        if aid == a.get(W + "val"):
                            fmts[(num.get(W + "numId"), lv)] = f
        counters = {}

        def run_html(r):
            pr = r.find(W + "rPr")
            out = []
            for ch in r:
                t = ch.tag
                if t == W + "t":
                    out.append(esc(ch.text))
                elif t == W + "tab":
                    out.append("&emsp;")
                elif t in (W + "br", W + "cr"):
                    out.append("<hr>" if ch.get(W + "type") == "page" else "<br>")
                elif t == W + "drawing":
                    for b in ch.iter(A + "blip"):
                        url = _media(z, rels.get(b.get(R + "embed"), ""), cache)
                        if url:
                            ext = next(ch.iter(WP + "extent"), None)
                            wpx = int(int(ext.get("cx", "0")) / 9525) if ext is not None else 0
                            out.append('<img src="%s"%s>' % (url, (' width="%d"' % min(640, wpx)) if wpx else ' width="480"'))
            s = "".join(out)
            if pr is not None and s:
                on = lambda tag: pr.find(W + tag) is not None and pr.find(W + tag).get(W + "val") not in ("0", "false", "none")
                if on("b"):
                    s = "<b>%s</b>" % s
                if on("i"):
                    s = "<i>%s</i>" % s
                if on("u"):
                    s = "<u>%s</u>" % s
                if on("strike"):
                    s = "<s>%s</s>" % s
                v = pr.find(W + "vertAlign")
                if v is not None and v.get(W + "val") in ("superscript", "subscript"):
                    s = "<%s>%s</%s>" % (v.get(W + "val")[:3], s, v.get(W + "val")[:3])
            return s

        def inline(node):
            out = []
            for ch in node:
                t = ch.tag
                if t == W + "r":
                    out.append(run_html(ch))
                elif t == W + "hyperlink":
                    target = rels.get(ch.get(R + "id"), "")
                    inner = inline(ch)
                    out.append('<a href="%s">%s</a>' % (esc(target), inner) if target.startswith(("http", "mailto")) else inner)
                elif t in (W + "ins", W + "smartTag", W + "fldSimple", W + "sdt", W + "sdtContent", W + "customXml"):
                    out.append(inline(ch))
            return "".join(out)

        def para(p):
            pr = p.find(W + "pPr")
            text = inline(p)
            sname, lvl_tag, num = "", None, None
            if pr is not None:
                ps = pr.find(W + "pStyle")
                if ps is not None:
                    sname = styles.get(ps.get(W + "val"), ps.get(W + "val", "")).lower()
                    num = num_of_style(ps.get(W + "val"))
                npr = pr.find(W + "numPr")
                if npr is not None and npr.find(W + "numId") is not None:
                    il = npr.find(W + "ilvl")
                    num = (npr.find(W + "numId").get(W + "val"), il.get(W + "val") if il is not None else (num[1] if num else "0"))
                jc = pr.find(W + "jc")
                align = {"center": "center", "right": "right", "end": "right", "both": "justify"}.get(jc.get(W + "val") if jc is not None else "")
            else:
                align = None
            m = re.match(r"(heading|título|titulo|überschrift|titre)\s*(\d)", sname)
            if m:
                lvl_tag = "h%d" % min(6, int(m.group(2)))
            elif sname in ("title", "título", "titulo"):
                lvl_tag = "h1"
            elif sname in ("subtitle", "subtítulo", "subtitulo"):
                lvl_tag = "h3"
            if not text.strip():
                return "<p>&nbsp;</p>" if not lvl_tag and not num else ""
            if lvl_tag:
                return "<%s>%s</%s>" % (lvl_tag, text, lvl_tag)
            if num and num[0] != "0":
                f = fmts.get(num, "bullet")
                lv = int(num[1] or 0)
                key = num[0]
                cnt = counters.setdefault(key, [0] * 10)
                cnt[lv] += 1
                for k in range(lv + 1, 10):
                    cnt[k] = 0
                n = cnt[lv]
                mark = ("•◦▪"[lv % 3] if f == "bullet" else
                        "%s." % (chr(96 + (n - 1) % 26 + 1) if f == "lowerLetter" else chr(64 + (n - 1) % 26 + 1) if f == "upperLetter" else n))
                return '<p style="margin-left:%dpx; margin-top:2px; margin-bottom:2px">%s&nbsp; %s</p>' % (18 + 22 * lv, mark, text)
            return '<p%s>%s</p>' % ((' align="%s"' % align) if align else "", text)

        def table(t):
            rows = []
            for tr in t.findall(W + "tr"):
                cells = []
                for tc in tr.findall(W + "tc"):
                    span = tc.find(W + "tcPr/" + W + "gridSpan")
                    inner = "".join(para(p) for p in tc.findall(W + "p")) or "&nbsp;"
                    inner = re.sub(r"^<p[^>]*>|</p>$", "", inner) if inner.count("<p") == 1 else inner
                    cells.append("<td%s>%s</td>" % ((' colspan="%s"' % span.get(W + "val")) if span is not None else "", inner))
                rows.append("<tr>%s</tr>" % "".join(cells))
            return '<table border="1" cellspacing="0" cellpadding="6" width="100%%">%s</table>' % "".join(rows)

        body = doc.find(W + "body")
        out = []
        for el in (body if body is not None else []):
            if el.tag == W + "p":
                out.append(para(el))
            elif el.tag == W + "tbl":
                out.append(table(el))
            elif el.tag == W + "sdt":
                for p in el.iter(W + "p"):
                    out.append(para(p))
        return "".join(out) or "<p><i>(documento vacío)</i></p>"


# ---------------------------------------------------------------- Excel
def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref or "")
    n = 0
    for ch in (letters.group(0) if letters else "A"):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f.is_integer() and abs(f) < 1e15:
        return "%d" % f
    return "%.10g" % f


def xlsx_html(path, max_rows=1500, max_cols=40):
    with zipfile.ZipFile(path) as z:
        wb = _xml(z, "xl/workbook.xml")
        if wb is None:
            raise ValueError("no es una hoja de Excel válida")
        rels = _rels(z, "xl/workbook.xml")
        shared = []
        ss = _xml(z, "xl/sharedStrings.xml")
        if ss is not None:
            for si in ss.findall(S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(S + "t")))
        dates = set()                                   # estilos de celda que son fechas
        sty = _xml(z, "xl/styles.xml")
        if sty is not None:
            custom = {nf.get("numFmtId"): nf.get("formatCode", "") for nf in sty.iter(S + "numFmt")}
            xfs = sty.find(S + "cellXfs")
            for i, xf in enumerate(xfs.findall(S + "xf") if xfs is not None else []):
                fid = xf.get("numFmtId", "0")
                code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fid, ""))
                if (fid.isdigit() and (14 <= int(fid) <= 22 or 45 <= int(fid) <= 47)) or (fid in custom and re.search(r"[dmy]", code, re.I) and not re.search(r"0[.,]0", code)):
                    dates.add(str(i))
        out = []
        sheets = wb.find(S + "sheets")
        for sh in (sheets.findall(S + "sheet") if sheets is not None else []):
            name = sh.get("name") or "Hoja"
            target = rels.get(sh.get(R + "id"))
            root = _xml(z, target) if target else None
            out.append("<h2>%s</h2>" % esc(name))
            if root is None:
                out.append("<p><i>(hoja sin datos)</i></p>")
                continue
            grid, ncols, more = [], 0, 0
            for row in root.iter(S + "row"):
                if len(grid) >= max_rows:
                    more += 1
                    continue
                vals = {}
                for k, c in enumerate(row.findall(S + "c")):
                    ci = _col_index(c.get("r")) if c.get("r") else k
                    if ci >= max_cols:
                        continue
                    t, v = c.get("t"), c.find(S + "v")
                    v = v.text if v is not None else None
                    f = c.find(S + "f")
                    if v is None and f is not None and f.text:      # fórmula sin resultado guardado: se muestra la fórmula
                        vals[ci] = "=" + f.text
                        continue
                    if t == "s" and v is not None and v.isdigit() and int(v) < len(shared):
                        v = shared[int(v)]
                    elif t == "inlineStr":
                        v = "".join(x.text or "" for x in c.iter(S + "t"))
                    elif t == "b":
                        v = "VERDADERO" if v == "1" else "FALSO"
                    elif t in (None, "n") and v is not None:
                        if c.get("s") in dates:
                            try:
                                v = (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(v))).strftime("%d/%m/%Y")
                            except (ValueError, OverflowError):
                                v = _num(v)
                        else:
                            v = _num(v)
                    vals[ci] = v or ""
                if vals:
                    ncols = max(ncols, max(vals) + 1)
                grid.append(vals)
            while grid and not grid[-1]:
                grid.pop()
            if not grid:
                out.append("<p><i>(hoja vacía)</i></p>")
                continue
            rows = []
            for r, vals in enumerate(grid):
                cells = []
                for ci in range(ncols):
                    v = esc(str(vals.get(ci, "")))
                    num = re.fullmatch(r"-?[\d.,]+%?", v or "x") is not None
                    cells.append(("<th>%s</th>" if r == 0 else "<td%s>%%s</td>" % (' align="right"' if num else "")) % (v or "&nbsp;"))
                rows.append("<tr>%s</tr>" % "".join(cells))
            out.append('<table border="1" cellspacing="0" cellpadding="5">%s</table>' % "".join(rows))
            if more:
                out.append("<p><i>… y %d filas más (ábrela con su programa para verla entera).</i></p>" % more)
        return "".join(out) or "<p><i>(libro vacío)</i></p>"


# ---------------------------------------------------------------- PowerPoint
def pptx_html(path):
    cache = _cache_dir(path)
    with zipfile.ZipFile(path) as z:
        pres = _xml(z, "ppt/presentation.xml")
        if pres is None:
            raise ValueError("no es una presentación de PowerPoint válida")
        prels = _rels(z, "ppt/presentation.xml")
        ids = pres.find(P + "sldIdLst")
        order = [prels.get(s.get(R + "id")) for s in (ids.findall(P + "sldId") if ids is not None else [])]
        out = []
        for n, name in enumerate([o for o in order if o], 1):
            root = _xml(z, name)
            if root is None:
                continue
            rels = _rels(z, name)
            title, parts = "", []
            for el in root.iter():
                if el.tag == P + "sp":
                    ph = el.find(".//" + P + "ph")
                    paras = []
                    for p in el.iter(A + "p"):
                        txt = "".join(esc(t.text) if t.tag == A + "t" else "<br>" for t in p.iter() if t.tag in (A + "t", A + "br"))
                        if txt.strip():
                            ppr = p.find(A + "pPr")
                            paras.append((int(ppr.get("lvl", "0")) if ppr is not None else 0, txt))
                    if not paras:
                        continue
                    if ph is not None and ph.get("type") in ("title", "ctrTitle") and not title:
                        title = " ".join(t for _, t in paras)
                    elif ph is not None and ph.get("type") == "subTitle":
                        parts.append('<p><i>%s</i></p>' % " ".join(t for _, t in paras))
                    else:
                        many = len(paras) > 1 or (ph is not None and ph.get("type") in (None, "body", "obj"))
                        for lv, t in paras:
                            parts.append('<p style="margin-left:%dpx; margin-top:2px; margin-bottom:2px">%s%s</p>' % (
                                22 * lv, ("•&nbsp; " if lv == 0 else "◦&nbsp; ") if many else "", t))
                elif el.tag == P + "pic":
                    b = next(el.iter(A + "blip"), None)
                    url = _media(z, rels.get(b.get(R + "embed"), ""), cache) if b is not None else None
                    if url:
                        parts.append('<p><img src="%s" width="420"></p>' % url)
                elif el.tag == A + "tbl":
                    rows = []
                    for tr in el.findall(A + "tr"):
                        rows.append("<tr>%s</tr>" % "".join("<td>%s</td>" % ("<br>".join(esc("".join(t.text or "" for t in p.iter(A + "t")))
                                                                                      for p in tc.iter(A + "p")) or "&nbsp;") for tc in tr.findall(A + "tc")))
                    parts.append('<table border="1" cellspacing="0" cellpadding="5">%s</table>' % "".join(rows))
            out.append('<table width="100%%" cellspacing="0" cellpadding="18" border="1" style="margin-bottom:14px"><tr><td>'
                       '<p style="color:%s; font-size:9pt">Diapositiva %d</p>%s%s</td></tr></table><p>&nbsp;</p>' % (
                           C["faint"], n, ("<h2>%s</h2>" % title) if title else "", "".join(parts) or "<p><i>(sin texto)</i></p>"))
        return "".join(out) or "<p><i>(presentación vacía)</i></p>"


# ---------------------------------------------------------------- piezas de la interfaz
class Reader(QTextBrowser):
    """Lectura de texto con formato (Markdown, Word, Excel, PowerPoint): columna centrada de ancho cómodo, enlaces que
    se abren fuera y las imágenes relativas a la carpeta del archivo."""
    open_file = Signal(str)
    COL = 860

    def __init__(self, base_dir):
        super().__init__()
        self.base = base_dir
        self.setObjectName("reader")
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._link)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.document().setDocumentMargin(26)
        self.setSearchPaths([base_dir])
        self.document().setBaseUrl(QUrl.fromLocalFile(base_dir.rstrip("\\/") + "/"))
        self.document().setDefaultStyleSheet(
            "h1 { font-size: 20pt; margin-top: 6px; } h2 { font-size: 15pt; margin-top: 14px; } h3 { font-size: 12.5pt; } "
            "p, li { line-height: 145%%; } a { color: %s; } th { background: %s; } table { border-color: %s; }" % (C["acc"], C["panel2"], C["line"]))
        self.setStyleSheet("QTextBrowser#reader { background: %s; border: none; font-size: 10.5pt; }" % C["bg"])

    def resizeEvent(self, e):
        w = self.width()
        side = max(0, (w - self.COL) // 2)              # columna centrada: las líneas no se hacen larguísimas
        self.setViewportMargins(side, 0, side, 0)
        super().resizeEvent(e)
        if getattr(self, "_last", None) and abs(self.viewport().width() - getattr(self, "_fit_w", 0)) > 24:
            if not hasattr(self, "_refit"):
                from PySide6.QtCore import QTimer
                self._refit = QTimer(self, singleShot=True, interval=150, timeout=self._redo)
            self._refit.start()                           # las imágenes se vuelven a ajustar al nuevo ancho

    def _redo(self):
        kind, content = self._last
        (self.show_markdown if kind == "md" else self.show_html)(content)

    def show_markdown(self, text):
        from .widgets import TextView
        self._last = ("md", text or "")
        y = self.verticalScrollBar().value()
        self.setMarkdown(text or "")
        TextView._wrap_code_blocks(self)                 # mismos bloques de código y tablas que en el chat
        TextView._style_tables(self)
        self._fit_images()
        self.verticalScrollBar().setValue(y)

    def _fit_images(self):
        """Las imágenes grandes se reducen al ancho disponible (no se cortan, tampoco en un panel estrecho)."""
        from PySide6.QtGui import QTextCursor
        self._fit_w = self.viewport().width()
        max_w = max(120, min(self.COL, self._fit_w) - 2 * int(self.document().documentMargin()) - 8)
        doc = self.document()
        b = doc.begin()
        while b.isValid():
            it = b.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isImageFormat():
                    from PySide6.QtGui import QImageReader
                    f = frag.charFormat().toImageFormat()
                    u = QUrl(f.name())
                    src = u.toLocalFile() if u.isLocalFile() else os.path.join(self.base, f.name())
                    sz = QImageReader(src).size()                 # tamaño sin cargar la imagen entera
                    w = f.width() or max(0, sz.width())
                    h = f.height() or (w * sz.height() / sz.width() if sz.width() > 0 else 0)
                    if w > max_w and h:
                        f.setWidth(max_w)
                        f.setHeight(h * max_w / w)
                        c = QTextCursor(doc)
                        c.setPosition(frag.position())
                        c.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                        c.setCharFormat(f)
                it += 1
            b = b.next()

    def show_html(self, body):
        self._last = ("html", body)
        y = self.verticalScrollBar().value()
        self.setHtml("<html><body>%s</body></html>" % body)
        self._fit_images()
        self.verticalScrollBar().setValue(y)

    def _link(self, url):
        s = url.toString()
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return
        p = url.toLocalFile() if url.isLocalFile() else os.path.join(self.base, s.split("#")[0])
        if p and os.path.isfile(p):
            self.open_file.emit(os.path.normpath(p))


class ImageView(QWidget):
    """Imagen ajustada a la ventana (o a su tamaño real), con zoom: botones, Ctrl + rueda; arriba, su tamaño."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 4, 8, 4)
        h.setSpacing(4)
        self.info = QLabel()
        self.info.setObjectName("faint")
        h.addWidget(self.info, 1)
        self.zoom_lbl = QLabel()
        self.zoom_lbl.setObjectName("faint")
        h.addWidget(self.zoom_lbl)
        for text, tip, cb in (("−", "Alejar (Ctrl + rueda)", lambda: self.zoom_by(1 / 1.25)), ("+", "Acercar (Ctrl + rueda)", lambda: self.zoom_by(1.25)),
                              ("Ajustar", "Ajustar a la ventana", self.fit), ("100 %", "Tamaño real", lambda: self.set_zoom(1.0))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(cb)
            h.addWidget(b)
        v.addWidget(bar)
        self.area = QScrollArea()
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setAlignment(Qt.AlignCenter)
        self.area.setObjectName("imageArea")
        self.area.setStyleSheet("QScrollArea#imageArea { background: %s; } QScrollBar:horizontal { height: 10px; }" % C["code"])
        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("background: transparent")
        self.area.setWidget(self.lbl)
        self.area.viewport().installEventFilter(self)
        v.addWidget(self.area, 1)
        self.src, self.svg, self.zoom, self.fitting = QPixmap(), None, 1.0, True

    def set_pixmap(self, pm, info=""):
        self.src, self.svg = pm, None
        self.info.setText(info or ("%d × %d" % (pm.width(), pm.height()) if not pm.isNull() else "No se pudo leer la imagen."))
        self._render()

    def set_svg(self, data, info=""):
        from PySide6.QtSvg import QSvgRenderer
        r = QSvgRenderer(QByteArray(data))
        if not r.isValid():
            self.src, self.svg = QPixmap(), None
            self.info.setText("El SVG tiene errores y no se puede dibujar (míralo en «Código»).")
            self.lbl.clear()
            return
        self.svg = r
        s = r.defaultSize()
        self.src = QPixmap(max(1, s.width()), max(1, s.height()))
        self.info.setText(info or "%d × %d (vectorial)" % (s.width(), s.height()))
        self._render()

    def fit(self):
        self.fitting = True
        self._render()

    def set_zoom(self, z):
        self.fitting = False
        self.zoom = max(0.05, min(16.0, z))
        self._render()

    def zoom_by(self, k):
        self.set_zoom(self.zoom * k)

    def _render(self):
        if self.src.isNull():
            self.lbl.clear()
            self.zoom_lbl.setText("")
            return
        vw, vh = max(50, self.area.viewport().width() - 16), max(50, self.area.viewport().height() - 16)
        if self.fitting:
            self.zoom = min(1.0, vw / self.src.width(), vh / self.src.height()) if self.svg is None else min(vw / self.src.width(), vh / self.src.height())
        w, h = max(1, int(self.src.width() * self.zoom)), max(1, int(self.src.height() * self.zoom))
        dpr = self.devicePixelRatioF() or 1.0
        if self.svg is not None:                          # vectorial: se dibuja nítido a cualquier tamaño
            pm = QPixmap(int(w * dpr), int(h * dpr))
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            self.svg.render(p)
            p.end()
            pm.setDevicePixelRatio(dpr)
        else:
            pm = self.src.scaled(int(w * dpr), int(h * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
        self.lbl.setPixmap(pm)
        self.lbl.resize(w, h)
        self.zoom_lbl.setText("%d %%" % round(self.zoom * 100))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fitting:
            self._render()

    def eventFilter(self, obj, e):
        if e.type() == e.Type.Wheel and e.modifiers() & Qt.ControlModifier:
            self.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
            return True
        return False


class CsvView(QTableWidget):
    """Un CSV como tabla (se detecta el separador)."""

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setObjectName("csvView")
        self.setStyleSheet("QTableWidget#csvView QScrollBar:horizontal { height: 10px; }")

    def show_text(self, text, limit=5000):
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))[:limit + 1]
        self.setUpdatesEnabled(False)
        self.clear()
        if not rows:
            self.setRowCount(0)
            self.setColumnCount(0)
            self.setUpdatesEnabled(True)
            return
        head, body = rows[0], rows[1:]
        n = max(len(r) for r in rows)
        self.setColumnCount(n)
        self.setRowCount(len(body))
        self.setHorizontalHeaderLabels(head + [""] * (n - len(head)))
        for i, r in enumerate(body):
            for j, v in enumerate(r):
                it = QTableWidgetItem(v)
                if re.fullmatch(r"-?[\d.,]+%?", v.strip() or "x"):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.setItem(i, j, it)
        self.resizeColumnsToContents()
        for j in range(n):
            self.setColumnWidth(j, min(self.columnWidth(j), 320))
        self.setUpdatesEnabled(True)


def web_preview():
    """Vista web (HTML y visor de PDF) si hay navegador integrado; si no, None."""
    from .canvas import web_view_class
    cls = web_view_class()
    if not cls:
        return None
    v = cls()
    try:
        from PySide6.QtWebEngineCore import QWebEngineSettings
        s = v.settings()
        s.setAttribute(QWebEngineSettings.PluginsEnabled, True)          # visor de PDF de Chromium
        s.setAttribute(QWebEngineSettings.PdfViewerEnabled, True)
    except Exception:
        pass
    return v


def document_html(path):
    """HTML de lectura de un documento de Office (o el texto de un PDF, si no hay visor)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".docm"):
        return docx_html(path)
    if ext in (".xlsx", ".xlsm"):
        return xlsx_html(path)
    if ext == ".pptx":
        return pptx_html(path)
    if ext == ".pdf":
        from . import harness
        txt = harness.read_document(path, limit=400000)
        return "".join("<h3>%s</h3>" % esc(b[4:-4]) if b.startswith("--- ") else "<p>%s</p>" % esc(b).replace("\n", "<br>")
                       for b in re.split(r"(--- Página \d+ ---)", txt) if b.strip())
    raise ValueError("formato no soportado")
