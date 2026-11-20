"""Creacion de documentos de oficina sin dependencias: Word (.docx), Excel (.xlsx), PowerPoint (.pptx) y PDF.

El contenido llega en Markdown sencillo (lo que mejor escriben los modelos pequenos):
  # Titulo / ## Seccion / ### Apartado      parrafos con **negrita**, *cursiva*, `codigo` y [enlaces](https://…)
  - vinetas (con sangria para subniveles)   1. listas numeradas         > citas
  | tablas | con | cabecera |                ```codigo```               --- (separador)
  ![pie](ruta/imagen.png)                   <!-- salto de pagina -->

- Word y PDF: el documento tal cual, con estilos, numeracion de paginas y tablas con cabecera.
- Excel: cada tabla es una hoja (el titulo ## anterior le da nombre). Numeros, porcentajes, importes en euros
  y formulas (=SUMA… o =SUM…) se guardan como tales; cabecera fija con filtros.
- PowerPoint: cada # (o cada ---) empieza una diapositiva; vinetas, tablas e imagenes dentro de ella.
"""
import os, re, io, zlib, struct, zipfile, datetime
from xml.sax.saxutils import escape as _x

ACCENT = "2E8F62"          # verde Jayth
DARK = "16201B"


def x(s):
    return _x(str(s), {'"': "&quot;"})


# ---------------------------------------------------------------- Markdown -> bloques
def inline(text):
    """'**a** y *b* `c` [d](u)' -> [(texto, {'b':…, 'i':…, 'code':…, 'link':…})]"""
    out = []
    pat = re.compile(r"(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|__(.+?)__|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)"
                     r"|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\))")
    pos = 0
    for m in pat.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], {}))
        if m.group(2):
            out.append((m.group(2), {"b": True, "i": True}))
        elif m.group(3) or m.group(4):
            out.append((m.group(3) or m.group(4), {"b": True}))
        elif m.group(5) or m.group(6):
            out.append((m.group(5) or m.group(6), {"i": True}))
        elif m.group(7):
            out.append((m.group(7), {"code": True}))
        elif m.group(8):
            out.append((m.group(8), {"link": m.group(9)}))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], {}))
    return [(t, f) for t, f in out if t]


def plain(text):
    return "".join(t for t, _ in inline(text))


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def parse(md):
    """Markdown -> lista de bloques (tipo, ...)."""
    lines = (md or "").replace("\r\n", "\n").replace("\t", "    ").split("\n")
    blocks, i, para = [], 0, []

    def flush():
        if para:
            blocks.append(("p", " ".join(s.strip() for s in para)))
            para.clear()
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            flush()
            i += 1
            continue
        if s.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(code)))
            i += 1
            continue
        if re.match(r"<!--\s*(salto|page ?break|nueva p[aá]gina)", s, re.I) or s.lower() in ("\\pagebreak", "\\newpage"):
            flush()
            blocks.append(("pagebreak",))
            i += 1
            continue
        m = re.match(r"(#{1,6})\s+(.*?)\s*#*$", s)
        if m:
            flush()
            blocks.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            flush()
            blocks.append(("hr",))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            flush()
            head = _cells(s)
            aligns = ["right" if c.endswith(":") and not c.startswith(":") else "center" if c.startswith(":") and c.endswith(":") else "left"
                      for c in _cells(lines[i + 1])]
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                r = _cells(lines[i])
                rows.append((r + [""] * len(head))[:len(head)])
                i += 1
            blocks.append(("table", head, rows, aligns))
            continue
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)$", s)
        if m:
            flush()
            blocks.append(("img", m.group(2).strip().strip("<>"), m.group(1)))
            i += 1
            continue
        if re.match(r"^([-*+]|\d+[.)])\s+", s):
            flush()
            kind = "ol" if re.match(r"^\d+[.)]", s) else "ul"
            items = []
            while i < len(lines):
                l2 = lines[i]
                m2 = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", l2)
                if m2:
                    lvl = min(len(m2.group(1)) // 2, 2)
                    txt = m2.group(3)
                    chk = re.match(r"\[( |x|X)\]\s+(.*)", txt)
                    if chk:
                        txt = ("☑ " if chk.group(1).lower() == "x" else "☐ ") + chk.group(2)
                    items.append([lvl, txt, "ol" if re.match(r"\d", m2.group(2)) else "ul"])
                    i += 1
                elif l2.strip() and l2.startswith("  ") and items:
                    items[-1][1] += " " + l2.strip()      # continuacion de la vineta
                    i += 1
                else:
                    break
            blocks.append((kind, [tuple(t) for t in items]))
            continue
        if s.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append(("quote", " ".join(q)))
            continue
        para.append(ln)
        i += 1
    flush()
    return blocks


# ---------------------------------------------------------------- imagenes
def image_info(path):
    """(tipo, ancho, alto) de un PNG o JPEG, o None."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", head[16:24])
                return "png", w, h
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    b = f.read(1)
                    while b and b != b"\xff":
                        b = f.read(1)
                    while b == b"\xff":
                        b = f.read(1)
                    if not b:
                        return None
                    mk = b[0]
                    if mk in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return "jpeg", w, h
                    ln = struct.unpack(">H", f.read(2))[0]
                    f.seek(ln - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def _img_path(src, base):
    p = os.path.expandvars(os.path.expanduser(src))
    if not os.path.isabs(p):
        p = os.path.join(base, p)
    return p if os.path.isfile(p) and image_info(p) else None


# ---------------------------------------------------------------- utilidades OOXML
def _zip(path, files):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    os.replace(tmp, path)


def _core(title):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>%s</dc:title><dc:creator>Jayth</dc:creator><cp:lastModifiedBy>Jayth</cp:lastModifiedBy>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
            '</cp:coreProperties>' % (x(title or ""), now, now))


def _app(name="Jayth"):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>%s</Application></Properties>' % name)


ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="%s"/>'
             '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
             '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
             '</Relationships>')
CT_HEAD = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
           '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
           '<Default Extension="xml" ContentType="application/xml"/>'
           '<Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/>'
           '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
           '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>')
EMU = 9525        # EMU por pixel a 96 ppp


# ---------------------------------------------------------------- Word
W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

W_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>'
            '<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="es-ES"/></w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:after="140" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
            '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
            '<w:pPr><w:spacing w:after="240"/><w:pBdr><w:bottom w:val="single" w:sz="12" w:space="6" w:color="%(a)s"/></w:pBdr></w:pPr>'
            '<w:rPr><w:b/><w:color w:val="%(d)s"/><w:sz w:val="48"/><w:szCs w:val="48"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
            '<w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>'
            '<w:rPr><w:b/><w:color w:val="%(a)s"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
            '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr>'
            '<w:rPr><w:b/><w:color w:val="%(d)s"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
            '<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr>'
            '<w:rPr><w:b/><w:color w:val="404040"/><w:sz w:val="23"/><w:szCs w:val="23"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>'
            '<w:pPr><w:spacing w:after="60"/><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/>'
            '<w:pPr><w:ind w:left="567"/><w:pBdr><w:left w:val="single" w:sz="18" w:space="8" w:color="%(a)s"/></w:pBdr></w:pPr>'
            '<w:rPr><w:i/><w:color w:val="505050"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/>'
            '<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:shd w:val="clear" w:color="auto" w:fill="F3F5F4"/><w:ind w:left="113" w:right="113"/></w:pPr>'
            '<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="19"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/>'
            '<w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:i/><w:color w:val="606060"/><w:sz w:val="18"/></w:rPr></w:style>'
            '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
            '<w:style w:type="table" w:styleId="Tabla"><w:name w:val="Tabla Jayth"/><w:tblPr><w:tblBorders>'
            '<w:top w:val="single" w:sz="4" w:color="BFC8C3"/><w:left w:val="single" w:sz="4" w:color="BFC8C3"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="BFC8C3"/><w:right w:val="single" w:sz="4" w:color="BFC8C3"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="BFC8C3"/><w:insideV w:val="single" w:sz="4" w:color="BFC8C3"/></w:tblBorders>'
            '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
            '</w:tblPr></w:style>'
            '</w:styles>') % {"a": ACCENT, "d": DARK}


def _w_numbering():
    def lvls(fmt):
        out = []
        for l in range(3):
            if fmt == "bullet":
                txt, font = ("•", "◦", "▪")[l], '<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/></w:rPr>'
            else:
                txt, font = "%%%d." % (l + 1), ""
            f = "bullet" if fmt == "bullet" else ("decimal", "lowerLetter", "lowerRoman")[l]
            out.append('<w:lvl w:ilvl="%d"><w:start w:val="1"/><w:numFmt w:val="%s"/><w:lvlText w:val="%s"/><w:lvlJc w:val="left"/>'
                       '<w:pPr><w:ind w:left="%d" w:hanging="360"/></w:pPr>%s</w:lvl>' % (l, f, txt, 720 + 360 * l, font))
        return "".join(out)
    return lvls


def write_docx(path, md, title=""):
    blocks = parse(md)
    base = os.path.dirname(os.path.abspath(path))
    body, rels, media, nums = [], [], [], []
    rid = [10]

    def runs(text, extra=""):
        out = []
        for t, f in inline(text):
            rpr = extra
            if f.get("b"):
                rpr += "<w:b/>"
            if f.get("i"):
                rpr += "<w:i/>"
            if f.get("code"):
                rpr += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:shd w:val="clear" w:color="auto" w:fill="EEF1EF"/>'
            r = '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % ("<w:rPr>%s</w:rPr>" % rpr if rpr else "", x(t))
            if f.get("link"):
                rid[0] += 1
                rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                            'Target="%s" TargetMode="External"/>' % (rid[0], x(f["link"])))
                r = '<w:hyperlink r:id="rId%d"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r></w:hyperlink>' % (
                    rid[0], extra, x(t))
            out.append(r)
        return "".join(out)

    def para(text, style=None, ppr=""):
        st = '<w:pStyle w:val="%s"/>' % style if style else ""
        return "<w:p><w:pPr>%s%s</w:pPr>%s</w:p>" % (st, ppr, runs(text))
    first_h1 = True
    for b in blocks:
        k = b[0]
        if k == "h":
            if b[1] == 1 and first_h1 and not body:
                body.append(para(b[2], "Title"))
            else:
                body.append(para(b[2], "Heading%d" % min(b[1] if not (b[1] == 1 and not first_h1) else 1, 3)))
            first_h1 = False if b[1] == 1 else first_h1
        elif k == "p":
            body.append(para(b[1]))
        elif k in ("ul", "ol"):
            num_ids = {}
            for lvl, txt, kind in b[1]:
                if kind not in num_ids:
                    nums.append(kind)
                    num_ids[kind] = len(nums)
                body.append(para(txt, "ListParagraph", '<w:numPr><w:ilvl w:val="%d"/><w:numId w:val="%d"/></w:numPr>' % (lvl, num_ids[kind])))
        elif k == "quote":
            body.append(para(b[1], "Quote"))
        elif k == "code":
            for ln in (b[1] or " ").split("\n"):
                body.append('<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % x(ln or " "))
            body.append("<w:p/>")
        elif k == "hr":
            body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="BFC8C3"/></w:pBdr></w:pPr></w:p>')
        elif k == "pagebreak":
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        elif k == "table":
            head, rows, aligns = b[1], b[2], b[3]
            n = max(1, len(head))
            tw = 9638
            grid = "".join('<w:gridCol w:w="%d"/>' % (tw // n) for _ in range(n))

            def cell(t, hdr, al):
                jc = {"right": "right", "center": "center"}.get(al, "left")
                shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % ("E3EFE8" if hdr else "FFFFFF")
                return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr><w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="%s"/></w:pPr>%s</w:p></w:tc>'
                        % (tw // n, shd, jc, runs(t, "<w:b/>" if hdr else "")))
            trs = ['<w:tr><w:trPr><w:tblHeader/></w:trPr>%s</w:tr>' % "".join(cell(h, True, aligns[i] if i < len(aligns) else "left") for i, h in enumerate(head))]
            for r in rows:
                trs.append("<w:tr>%s</w:tr>" % "".join(cell(c, False, aligns[i] if i < len(aligns) else "left") for i, c in enumerate(r)))
            body.append('<w:tbl><w:tblPr><w:tblStyle w:val="Tabla"/><w:tblW w:w="%d" w:type="dxa"/><w:tblLook w:val="04A0" w:firstRow="1"/></w:tblPr>'
                        '<w:tblGrid>%s</w:tblGrid>%s</w:tbl><w:p/>' % (tw, grid, "".join(trs)))
        elif k == "img":
            p = _img_path(b[1], base)
            if not p:
                body.append(para("[imagen no encontrada: %s]" % b[1]))
                continue
            kind, w, h = image_info(p)
            ext = "png" if kind == "png" else "jpeg"
            media.append(("word/media/imagen%d.%s" % (len(media) + 1, ext), open(p, "rb").read()))
            rid[0] += 1
            rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/imagen%d.%s"/>'
                        % (rid[0], len(media), ext))
            maxw = 6.0 * 914400          # 6 pulgadas de ancho como maximo
            cx, cy = w * EMU, h * EMU
            if cx > maxw:
                cy, cx = int(cy * maxw / cx), int(maxw)
            n = len(media)
            body.append('<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="60"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
                        '<wp:extent cx="%d" cy="%d"/><wp:docPr id="%d" name="Imagen %d"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                        '<pic:pic><pic:nvPicPr><pic:cNvPr id="%d" name="imagen%d.%s"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId%d"/>'
                        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
                        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
                        % (cx, cy, n, n, n, n, ext, rid[0], cx, cy))
            if b[2]:
                body.append(para(b[2], "Caption"))
    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rId3"/><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1418" w:right="1134" w:bottom="1418" w:left="1134" w:header="709" w:footer="567" w:gutter="0"/></w:sectPr>')
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s%s</w:body></w:document>' % (W_NS, "".join(body), sect))
    lv = _w_numbering()
    numbering = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                 '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>%s</w:abstractNum>'
                 '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>%s</w:abstractNum>%s</w:numbering>' % (
                     lv("bullet"), lv("decimal"),
                     "".join('<w:num w:numId="%d"><w:abstractNumId w:val="%d"/>%s</w:num>' % (
                         i + 1, 0 if k == "ul" else 1,
                         "" if k == "ul" else '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>') for i, k in enumerate(nums or ["ul"]))))
    footer = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">Página </w:t></w:r>'
              '<w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
              '<w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
              '<w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
              '<w:r><w:rPr><w:color w:val="808080"/><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
                '%s</Relationships>' % "".join(rels))
    # formato moderno: sin esto Word lo abre en «Modo de compatibilidad»
    settings = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:defaultTabStop w:val="708"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
                '</w:compat><w:themeFontLang w:val="es-ES"/></w:settings>')
    ct = (CT_HEAD + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
          '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
          '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/></Types>')
    title = title or next((plain(b[2]) for b in blocks if b[0] == "h"), "")
    _zip(path, [("[Content_Types].xml", ct), ("_rels/.rels", ROOT_RELS % "word/document.xml"), ("docProps/core.xml", _core(title)),
                ("docProps/app.xml", _app()), ("word/document.xml", doc), ("word/styles.xml", W_STYLES), ("word/numbering.xml", numbering),
                ("word/footer1.xml", footer), ("word/settings.xml", settings), ("word/_rels/document.xml.rels", doc_rels)] + media)
    return {"paginas_aprox": None, "bloques": len(blocks)}


# ---------------------------------------------------------------- Excel
def _num(s):
    """Texto de celda -> (valor, formato) con formato en ('', 'int', 'dec', 'pct', 'eur', 'formula')."""
    t = plain(str(s)).strip()
    if not t:
        return None, ""
    if t.startswith("="):
        return t, "formula"
    eur = bool(re.search(r"€|\bEUR\b", t))
    pct = t.endswith("%")
    core = re.sub(r"[€%\s]|\bEUR\b", "", t).replace(" ", "")
    neg = core.startswith("-") or (core.startswith("(") and core.endswith(")"))
    core = core.strip("-()")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", core):            # 45.000 o 1.234,56 (formato español)
        v = float(core.replace(".", "").replace(",", "."))
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", core):          # 45,000.50 (formato inglés)
        v = float(core.replace(",", ""))
    elif re.fullmatch(r"\d+,\d+", core):                            # 12,5
        v = float(core.replace(",", "."))
    elif re.fullmatch(r"\d+(\.\d+)?", core):
        v = float(core)
    else:
        return t, ""
    v = -v if neg else v
    if pct:
        return v / 100.0, "pct"
    if eur:
        return v, "eur"
    return v, ("int" if v == int(v) and "," not in core and not re.search(r"\.\d{1,2}$", core) else "dec")


FN_ES = {"SUMA": "SUM", "PROMEDIO": "AVERAGE", "CONTAR": "COUNT", "CONTARA": "COUNTA", "SI": "IF", "MAX": "MAX", "MIN": "MIN",
         "REDONDEAR": "ROUND", "BUSCARV": "VLOOKUP", "SUMAR.SI": "SUMIF", "CONTAR.SI": "COUNTIF", "HOY": "TODAY", "Y": "AND", "O": "OR"}


def _formula(f):
    """=SUMA(B2:B5;C1) -> SUM(B2:B5,C1) (el archivo guarda las funciones en ingles y con comas)."""
    f = f[1:]
    for es, en in sorted(FN_ES.items(), key=lambda kv: -len(kv[0])):
        f = re.sub(r"(?i)(?<![A-Z.])%s(?=\()" % re.escape(es), en, f)
    out, q = [], False
    for ch in f:                      # ; -> , fuera de las comillas
        if ch == '"':
            q = not q
        out.append("," if ch == ";" and not q else ch)
    return "".join(out)


def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _sheets_from(md):
    """Tablas del Markdown -> [(nombre, filas)]; si no hay tablas, admite CSV (coma, punto y coma o tabulador)."""
    blocks = parse(md)
    sheets, last_h = [], ""
    for b in blocks:
        if b[0] == "h":
            last_h = plain(b[2])
        elif b[0] == "table":
            sheets.append((last_h or "Hoja%d" % (len(sheets) + 1), [b[1]] + b[2]))
            last_h = ""
    if not sheets:
        lines = [l for l in (md or "").splitlines() if l.strip()]
        if lines:
            sep = max((";", "\t", ","), key=lambda c: sum(l.count(c) for l in lines[:5]))
            import csv
            sheets.append(("Hoja1", [r for r in csv.reader(lines, delimiter=sep)]))
    names, out = set(), []
    for n, rows in sheets:
        n = re.sub(r"[\[\]:*?/\\]", " ", n).strip()[:31] or "Hoja"
        base, k = n, 2
        while n.lower() in names:
            n = (base[:28] + " %d" % k)
            k += 1
        names.add(n.lower())
        out.append((n, rows))
    return out


X_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00\\ &quot;€&quot;"/><numFmt numFmtId="165" formatCode="#,##0.##"/></numFmts>'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
            '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FF%s"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left style="thin"><color rgb="FFD0D7D3"/></left><right style="thin"><color rgb="FFD0D7D3"/></right>'
            '<top style="thin"><color rgb="FFD0D7D3"/></top><bottom style="thin"><color rgb="FFD0D7D3"/></bottom><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="7">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>'                                   # 0 texto
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
            '<alignment vertical="center"/></xf>'                                                                                  # 1 cabecera
            '<xf numFmtId="3" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'             # 2 entero
            '<xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'           # 3 decimal
            '<xf numFmtId="10" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'            # 4 porcentaje
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'           # 5 euros
            '<xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>'             # 6 formula (#,##0.00)
            '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>') % ACCENT


def write_xlsx(path, md, title=""):
    sheets = _sheets_from(md)
    if not sheets:
        raise ValueError("No hay ninguna tabla en el contenido. Para Excel escribe tablas Markdown (| a | b |) o líneas CSV.")
    files, wb_sheets, wb_rels, ct = [], [], [], []
    style_of = {"": 0, "int": 2, "dec": 3, "pct": 4, "eur": 5, "formula": 6}
    for si, (name, rows) in enumerate(sheets, 1):
        ncol = max(len(r) for r in rows)
        widths = [8] * ncol
        xml_rows = []
        for ri, r in enumerate(rows):
            cells = []
            for ci in range(ncol):
                raw = r[ci] if ci < len(r) else ""
                ref = "%s%d" % (_col(ci), ri + 1)
                if ri == 0:
                    t = plain(raw)
                    cells.append('<c r="%s" s="1" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, x(t)))
                    widths[ci] = max(widths[ci], len(t) + 4)
                    continue
                v, fmt = _num(raw)
                if v is None:
                    cells.append('<c r="%s" s="0"/>' % ref)
                elif fmt == "formula":
                    cells.append('<c r="%s" s="6"><f>%s</f></c>' % (ref, x(_formula(v))))
                    widths[ci] = max(widths[ci], 12)
                elif fmt:
                    cells.append('<c r="%s" s="%d"><v>%s</v></c>' % (ref, style_of[fmt], repr(float(v)) if fmt != "int" else str(int(v))))
                    widths[ci] = max(widths[ci], len(plain(raw)) + 3)
                else:
                    cells.append('<c r="%s" s="0" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, x(v)))
                    widths[ci] = max(widths[ci], min(len(v), 60) + 2)
            xml_rows.append('<row r="%d"%s>%s</row>' % (ri + 1, ' ht="20" customHeight="1"' if ri == 0 else "", "".join(cells)))
        last = "%s%d" % (_col(ncol - 1), len(rows))
        sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><dimension ref="A1:%s"/>'
                 '<sheetViews><sheetView workbookViewId="0"%s><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                 '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
                 '<cols>%s</cols><sheetData>%s</sheetData>%s<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>') % (
            last, ' tabSelected="1"' if si == 1 else "",
            "".join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, min(w, 70)) for i, w in enumerate(widths)),
            "".join(xml_rows), '<autoFilter ref="A1:%s"/>' % last if len(rows) > 1 else "")
        files.append(("xl/worksheets/sheet%d.xml" % si, sheet))
        wb_sheets.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (x(name), si, si))
        wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (si, si))
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % si)
    n = len(sheets)
    defined = "".join('<definedName name="_xlnm._FilterDatabase" localSheetId="%d" hidden="1">\'%s\'!$A$1:$%s$%d</definedName>' % (
        i, x(name.replace("'", "''")), _col(max(len(r) for r in rows) - 1), len(rows)) for i, (name, rows) in enumerate(sheets) if len(rows) > 1)
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews>'
          '<sheets>%s</sheets>%s<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>' % ("".join(wb_sheets), "<definedNames>%s</definedNames>" % defined if defined else ""))
    wb_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1))
    ct_all = (CT_HEAD + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>%s</Types>' % "".join(ct))
    _zip(path, [("[Content_Types].xml", ct_all), ("_rels/.rels", ROOT_RELS % "xl/workbook.xml"), ("docProps/core.xml", _core(title or sheets[0][0])),
                ("docProps/app.xml", _app()), ("xl/workbook.xml", wb), ("xl/styles.xml", X_STYLES),
                ("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>' % "".join(wb_rels))] + files)
    return {"hojas": [(n, len(r) - 1) for n, r in sheets]}


# ---------------------------------------------------------------- PowerPoint
P_NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
SW, SH = 12192000, 6858000          # 16:9

THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Jayth">'
         '<a:themeElements><a:clrScheme name="Jayth"><a:dk1><a:srgbClr val="%(d)s"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
         '<a:dk2><a:srgbClr val="1F2A24"/></a:dk2><a:lt2><a:srgbClr val="EEF2F0"/></a:lt2><a:accent1><a:srgbClr val="%(a)s"/></a:accent1>'
         '<a:accent2><a:srgbClr val="3B82F6"/></a:accent2><a:accent3><a:srgbClr val="F2A541"/></a:accent3><a:accent4><a:srgbClr val="E05A3A"/></a:accent4>'
         '<a:accent5><a:srgbClr val="8B5CF6"/></a:accent5><a:accent6><a:srgbClr val="14B8A6"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink>'
         '<a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme><a:fontScheme name="Jayth"><a:majorFont><a:latin typeface="Calibri"/>'
         '<a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
         '</a:fontScheme><a:fmtScheme name="Jayth"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
         '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
         '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="25400"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
         '<a:ln w="38100"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
         '<a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst>'
         '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
         '</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>') % {"a": ACCENT, "d": DARK}

EMPTY_TREE = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
              '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
MASTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster %s><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
          '<a:effectLst/></p:bgPr></p:bg><p:spTree>%s</p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
          'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
          '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
          '<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="3200" b="1"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
          '<p:bodyStyle><a:lvl1pPr><a:defRPr sz="2000"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
          '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle></p:txStyles></p:sldMaster>') % (P_NS, EMPTY_TREE)
LAYOUT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout %s type="blank" preserve="1"><p:cSld name="En blanco"><p:spTree>%s</p:spTree></p:cSld>'
          '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>') % (P_NS, EMPTY_TREE)


def _slides_from(md):
    """# Titulo (o ---) empieza diapositiva. Devuelve [{'title', 'items': bloques}]."""
    slides, cur = [], None
    for b in parse(md):
        if b[0] == "h" and b[1] == 1 or b[0] in ("hr", "pagebreak"):
            cur = {"title": b[2] if b[0] == "h" else "", "items": []}
            slides.append(cur)
            continue
        if cur is None:
            cur = {"title": "", "items": []}
            slides.append(cur)
        if b[0] == "h" and not cur["title"]:
            cur["title"] = b[2]
        else:
            cur["items"].append(b)
    return [s for s in slides if s["title"] or s["items"]]


def _p_runs(text, size, bold=False, color=None):
    out = []
    for t, f in inline(text):
        attrs = ' lang="es-ES" sz="%d"%s%s dirty="0"' % (size, ' b="1"' if bold or f.get("b") else "", ' i="1"' if f.get("i") else "")
        fill = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % (color or "333F39")
        font = '<a:latin typeface="Consolas"/>' if f.get("code") else ""
        out.append('<a:r><a:rPr%s>%s%s</a:rPr><a:t>%s</a:t></a:r>' % (attrs, fill, font, x(t)))
    return "".join(out) or '<a:endParaRPr lang="es-ES" sz="%d"/>' % size


def _sp(sid, name, x0, y0, w, h, paras, anchor="t", fill=None):
    fill_xml = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % fill if fill else "<a:noFill/>"
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
            '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>%s</p:spPr><p:txBody><a:bodyPr wrap="square" lIns="91440" '
            'tIns="45720" rIns="91440" bIns="45720" anchor="%s"><a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>') % (
        sid, x(name), x0, y0, w, h, fill_xml, anchor, paras)


def write_pptx(path, md, title=""):
    slides = _slides_from(md)
    if not slides:
        raise ValueError("No hay contenido para las diapositivas. Usa un «# Título» por diapositiva y viñetas debajo.")
    base = os.path.dirname(os.path.abspath(path))
    files, pres_ids, pres_rels, ct = [], [], [], []
    media_n = 0
    for si, s in enumerate(slides, 1):
        shapes, rels, sid = [], [], 2
        is_cover = si == 1 and len(slides) > 1 and all(b[0] == "p" for b in s["items"]) and len(s["items"]) <= 2
        if is_cover:                      # portada: titulo grande centrado y subtitulo
            shapes.append('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Banda"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="0" y="%d"/>'
                          '<a:ext cx="%d" cy="91440"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                          '<a:ln><a:noFill/></a:ln></p:spPr></p:sp>' % (sid, 3750000, SW, ACCENT))
            sid += 1
            shapes.append(_sp(sid, "Título", 685800, 1700000, SW - 1371600, 1900000,
                              '<a:p><a:pPr algn="ctr"/>%s</a:p>' % _p_runs(s["title"], 4400, True, DARK), "b"))
            sid += 1
            sub = "".join('<a:p><a:pPr algn="ctr"/>%s</a:p>' % _p_runs(b[1], 2200, False, "5A6660") for b in s["items"])
            if sub:
                shapes.append(_sp(sid, "Subtítulo", 685800, 3950000, SW - 1371600, 1300000, sub))
                sid += 1
        else:
            shapes.append('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Acento"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="457200" y="520000"/>'
                          '<a:ext cx="91440" cy="640000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                          '<a:ln><a:noFill/></a:ln></p:spPr></p:sp>' % (sid, ACCENT))
            sid += 1
            shapes.append(_sp(sid, "Título", 640000, 420000, SW - 1100000, 840000, "<a:p>%s</a:p>" % _p_runs(s["title"] or " ", 3200, True, DARK), "ctr"))
            sid += 1
            top, left, width = 1450000, 640000, SW - 1100000
            imgs = [b for b in s["items"] if b[0] == "img"]
            tables = [b for b in s["items"] if b[0] == "table"]
            texts = [b for b in s["items"] if b[0] not in ("img", "table")]
            text_w = width if not imgs else int(width * 0.55)
            paras = []
            for b in texts:
                if b[0] in ("ul", "ol"):
                    for n, (lvl, txt, kind) in enumerate(b[1], 1):
                        bullet = ('<a:buFont typeface="Arial"/><a:buChar char="•"/>' if kind == "ul" else '<a:buFont typeface="+mj-lt"/><a:buAutoNum type="arabicPeriod"/>')
                        paras.append('<a:p><a:pPr marL="%d" indent="-285750"><a:spcBef><a:spcPts val="600"/></a:spcBef><a:buClr><a:srgbClr val="%s"/></a:buClr>%s</a:pPr>%s</a:p>' % (
                            342900 + 342900 * lvl, ACCENT, bullet, _p_runs(txt, 2000 - 200 * lvl)))
                elif b[0] in ("p", "quote"):
                    paras.append('<a:p><a:pPr><a:spcBef><a:spcPts val="600"/></a:spcBef><a:buNone/></a:pPr>%s</a:p>' % _p_runs(b[1], 1800))
                elif b[0] == "h":
                    paras.append('<a:p><a:pPr><a:spcBef><a:spcPts val="900"/></a:spcBef><a:buNone/></a:pPr>%s</a:p>' % _p_runs(b[2], 2200, True, ACCENT))
                elif b[0] == "code":
                    for ln in b[1].split("\n"):
                        paras.append('<a:p><a:pPr><a:buNone/></a:pPr><a:r><a:rPr lang="es-ES" sz="1400"><a:latin typeface="Consolas"/></a:rPr><a:t>%s</a:t></a:r></a:p>' % x(ln))
            body_h = SH - top - 500000
            if tables:
                body_h = int(body_h * 0.42) if paras else 0
            if paras:
                shapes.append(_sp(sid, "Contenido", left, top, text_w, body_h or SH - top - 500000, "".join(paras)))
                sid += 1
            for b in tables[:1]:
                head, rows = b[1], b[2][:12]
                ncol = max(1, len(head))
                ty = top + (body_h + 150000 if paras else 0)
                th = SH - ty - 450000
                rh = min(520000, th // (len(rows) + 1))
                cw = width // ncol

                def tc(t, hdr):
                    fill = ACCENT if hdr else "FFFFFF"
                    return ('<a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p>%s</a:p></a:txBody><a:tcPr marL="91440" marR="91440" marT="45720" marB="45720">'
                            '<a:lnL w="9525"><a:solidFill><a:srgbClr val="D0D7D3"/></a:solidFill></a:lnL><a:lnR w="9525"><a:solidFill><a:srgbClr val="D0D7D3"/></a:solidFill></a:lnR>'
                            '<a:lnT w="9525"><a:solidFill><a:srgbClr val="D0D7D3"/></a:solidFill></a:lnT><a:lnB w="9525"><a:solidFill><a:srgbClr val="D0D7D3"/></a:solidFill></a:lnB>'
                            '<a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:tcPr></a:tc>') % (_p_runs(t, 1400, hdr, "FFFFFF" if hdr else "333F39"), fill)
                grid = "".join('<a:gridCol w="%d"/>' % cw for _ in range(ncol))
                trs = '<a:tr h="%d">%s</a:tr>' % (rh, "".join(tc(h, True) for h in head))
                trs += "".join('<a:tr h="%d">%s</a:tr>' % (rh, "".join(tc(c, False) for c in r)) for r in rows)
                shapes.append('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="%d" name="Tabla"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
                              '<p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></p:xfrm><a:graphic>'
                              '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table"><a:tbl><a:tblPr firstRow="1" bandRow="1"/>'
                              '<a:tblGrid>%s</a:tblGrid>%s</a:tbl></a:graphicData></a:graphic></p:graphicFrame>' % (
                                  sid, left, ty, cw * ncol, rh * (len(rows) + 1), grid, trs))
                sid += 1
            for b in imgs[:1]:
                p = _img_path(b[1], base)
                if not p:
                    continue
                kind, w, h = image_info(p)
                ext = "png" if kind == "png" else "jpeg"
                media_n += 1
                files.append(("ppt/media/imagen%d.%s" % (media_n, ext), open(p, "rb").read()))
                rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/imagen%d.%s"/>'
                            % (len(rels) + 2, media_n, ext))
                box_x = left + (text_w + 200000 if paras else 0)
                box_w = width - (text_w + 200000 if paras else 0)
                box_h = SH - top - 600000
                sc = min(box_w / (w * EMU), box_h / (h * EMU))
                cx, cy = int(w * EMU * sc), int(h * EMU * sc)
                shapes.append('<p:pic><p:nvPicPr><p:cNvPr id="%d" name="Imagen"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                              '<p:blipFill><a:blip r:embed="rId%d"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
                              '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>' % (
                                  sid, len(rels) + 1, box_x + (box_w - cx) // 2, top + (box_h - cy) // 2, cx, cy))
                sid += 1
            # numero de diapositiva
            shapes.append(_sp(sid, "Número", SW - 1300000, SH - 480000, 900000, 330000,
                              '<a:p><a:pPr algn="r"/><a:r><a:rPr lang="es-ES" sz="1100"><a:solidFill><a:srgbClr val="9AA59F"/></a:solidFill></a:rPr><a:t>%d</a:t></a:r></a:p>' % si))
            sid += 1
        slide = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld %s><p:cSld><p:spTree>%s%s</p:spTree></p:cSld>'
                 '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>') % (P_NS, EMPTY_TREE, "".join(shapes))
        files.append(("ppt/slides/slide%d.xml" % si, slide))
        files.append(("ppt/slides/_rels/slide%d.xml.rels" % si,
                      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                      '%s</Relationships>' % "".join(rels)))
        pres_ids.append('<p:sldId id="%d" r:id="rId%d"/>' % (255 + si, si + 1))
        pres_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide%d.xml"/>' % (si + 1, si))
        ct.append('<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % si)
    n = len(slides)
    pres = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation %s saveSubsetFonts="1"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
            '</p:sldMasterIdLst><p:sldIdLst>%s</p:sldIdLst><p:sldSz cx="%d" cy="%d"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle>'
            '<a:lvl1pPr><a:defRPr lang="es-ES"/></a:lvl1pPr></p:defaultTextStyle></p:presentation>') % (P_NS, "".join(pres_ids), SW, SH)
    pres_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'] + pres_rels + [
        '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>' % (n + 2),
        '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>' % (n + 3),
        '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>' % (n + 4),
        '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>' % (n + 5)]
    R = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>'
    ct_all = (CT_HEAD + '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
              '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
              '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
              '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
              '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>'
              '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>'
              '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>%s</Types>' % "".join(ct))
    _zip(path, [("[Content_Types].xml", ct_all), ("_rels/.rels", ROOT_RELS % "ppt/presentation.xml"),
                ("docProps/core.xml", _core(title or plain(slides[0]["title"]))), ("docProps/app.xml", _app()),
                ("ppt/presentation.xml", pres), ("ppt/_rels/presentation.xml.rels", R % "".join(pres_rels)),
                ("ppt/slideMasters/slideMaster1.xml", MASTER),
                ("ppt/slideMasters/_rels/slideMaster1.xml.rels", R % ('<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                                                                      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>')),
                ("ppt/slideLayouts/slideLayout1.xml", LAYOUT),
                ("ppt/slideLayouts/_rels/slideLayout1.xml.rels", R % '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'),
                ("ppt/theme/theme1.xml", THEME),
                ("ppt/presProps.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentationPr %s/>' % P_NS),
                ("ppt/viewProps.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:viewPr %s><p:normalViewPr><p:restoredLeft sz="15620"/>'
                                      '<p:restoredTop sz="94660"/></p:normalViewPr><p:gridSpacing cx="76200" cy="76200"/></p:viewPr>' % P_NS),
                ("ppt/tableStyles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                                        'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>')] + files)
    return {"diapositivas": n}


# ---------------------------------------------------------------- PDF
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278,
         584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
         667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
         278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_HELVB = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333,
          584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
          667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
          333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]
_BASE = str.maketrans("áéíóúàèìòùäëïöüâêîôûñçÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÊÎÔÛÑÇ", "aeiouaeiouaeiouaeiouncAEIOUAEIOUAEIOUAEIOUNC")


def _cp(s):
    """Texto -> bytes cp1252 (WinAnsi) con sustituciones para lo que no existe en esa codificación."""
    s = s.replace("−", "-").replace("‑", "-").replace("→", "->").replace("←", "<-").replace("≤", "<=").replace("≥", ">=").replace("✓", "v").replace("☑", "[x]").replace("☐", "[ ]")
    return s.encode("cp1252", "replace")


def _w(s, font, size):
    if font == "C":
        return len(s) * 600 * size / 1000.0
    tab = _HELVB if font in ("B", "BI") else _HELV
    tot = 0
    for ch in s:
        o = ord(ch.translate(_BASE)) if ord(ch) > 126 else ord(ch)
        tot += tab[o - 32] if 32 <= o <= 126 else (556 if ch != "€" else 556)
    return tot * size / 1000.0


def _pdf_str(s):
    b = _cp(s)
    return "(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").decode("latin-1") + ")"


class _PDF:
    W, H, M = 595.28, 841.89, 56.0

    def __init__(self):
        self.pages, self.ops = [], None
        self.images = []
        self.new_page()

    def new_page(self):
        self.ops = []
        self.pages.append(self.ops)
        self.y = self.H - self.M

    def need(self, h):
        if self.y - h < self.M + 20:
            self.new_page()

    def text(self, x0, y, s, font="R", size=11, color=(0.13, 0.15, 0.14)):
        f = {"R": "F1", "B": "F2", "I": "F3", "BI": "F4", "C": "F5"}[font]
        self.ops.append("BT %.3f %.3f %.3f rg /%s %.1f Tf %.2f %.2f Td %s Tj ET" % (color + (f, size, x0, y, _pdf_str(s))))

    def rect(self, x0, y, w, h, fill=None, stroke=None, lw=0.6):
        s = ""
        if fill:
            s += "%.3f %.3f %.3f rg " % fill
        if stroke:
            s += "%.3f %.3f %.3f RG %.2f w " % (stroke + (lw,))
        s += "%.2f %.2f %.2f %.2f re %s" % (x0, y, w, h, "B" if fill and stroke else "f" if fill else "S")
        self.ops.append(s)

    def line(self, x0, y0, x1, y1, color=(0.75, 0.78, 0.76), lw=0.6):
        self.ops.append("%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (color + (lw, x0, y0, x1, y1)))

    def wrap_runs(self, runs, width, size, base_font="R"):
        """[(texto, flags)] -> lineas [[(palabra, fuente)]] que caben en width."""
        words = []
        for t, f in runs:
            font = "C" if f.get("code") else ("BI" if (f.get("b") or base_font == "B") and f.get("i") else "B" if (f.get("b") or base_font == "B")
                                               else "I" if f.get("i") or base_font == "I" else "R")
            for part in re.split(r"(\s+)", t):
                if part:
                    words.append((part, font))
        lines, cur, cw = [], [], 0.0
        for wd, font in words:
            if wd.isspace():
                if cur:
                    cur.append((" ", font))
                    cw += _w(" ", font, size)
                continue
            ww = _w(wd, font, size)
            while ww > width and len(wd) > 1:            # palabra mas larga que la linea: se corta
                cut = max(1, int(len(wd) * width / ww) - 1)
                if cur:
                    lines.append(cur)
                    cur, cw = [], 0.0
                lines.append([(wd[:cut], font)])
                wd = wd[cut:]
                ww = _w(wd, font, size)
            if cw + ww > width and cur:
                while cur and cur[-1][0] == " ":
                    cur.pop()
                lines.append(cur)
                cur, cw = [], 0.0
            cur.append((wd, font))
            cw += ww
        if cur:
            lines.append(cur)
        return lines or [[]]

    def draw_line(self, x0, y, line, size, color=(0.13, 0.15, 0.14), align="left", width=0):
        if align != "left":
            tw = sum(_w(t, f, size) for t, f in line)
            x0 += (width - tw) if align == "right" else (width - tw) / 2
        for t, f in line:
            if t.strip():
                self.text(x0, y, t, f, size, color)
            x0 += _w(t, f, size)

    def paragraph(self, text, size=11, font="R", indent=0, color=(0.13, 0.15, 0.14), after=7, lead=1.38):
        width = self.W - 2 * self.M - indent
        for line in self.wrap_runs(inline(text), width, size, font):
            self.need(size * lead)
            self.y -= size * lead
            self.draw_line(self.M + indent, self.y + size * 0.25, line, size, color)
        self.y -= after


def write_pdf(path, md, title=""):
    blocks = parse(md)
    base = os.path.dirname(os.path.abspath(path))
    pdf = _PDF()
    acc = (0.18, 0.56, 0.38)
    for b in blocks:
        k = b[0]
        if k == "h":
            size = {1: 20, 2: 15, 3: 12.5}.get(b[1], 11.5)
            pdf.y -= 6 if b[1] > 1 else 2
            pdf.need(size * 2.6)
            pdf.paragraph(b[2], size, "B", 0, acc if b[1] <= 2 else (0.2, 0.22, 0.21), after=3 if b[1] > 1 else 2)
            if b[1] == 1:
                pdf.line(pdf.M, pdf.y + 2, pdf.W - pdf.M, pdf.y + 2, acc, 1.2)
                pdf.y -= 8
        elif k == "p":
            pdf.paragraph(b[1])
        elif k == "quote":
            y0 = pdf.y
            pdf.paragraph(b[1], 11, "I", 16, (0.32, 0.35, 0.33))
            pdf.line(pdf.M + 4, pdf.y + 6, pdf.M + 4, min(y0, pdf.H - pdf.M), acc, 2.2)
        elif k in ("ul", "ol"):
            counters = [0, 0, 0]
            for lvl, txt, kind in b[1]:
                if kind == "ol":                 # solo numeran los elementos numerados (las viñetas no cuentan)
                    counters[lvl] += 1
                    for j in range(lvl + 1, 3):
                        counters[j] = 0
                ind = 18 + 16 * lvl
                mark = "•" if kind == "ul" else "%d." % counters[lvl]
                width = pdf.W - 2 * pdf.M - ind
                lines = pdf.wrap_runs(inline(txt), width, 11)
                for li, line in enumerate(lines):
                    pdf.need(15)
                    pdf.y -= 15.2
                    if li == 0:
                        pdf.text(pdf.M + ind - 12 - (6 if kind == "ol" else 0), pdf.y + 2.75, mark, "B" if kind == "ol" else "R", 11, acc)
                    pdf.draw_line(pdf.M + ind, pdf.y + 2.75, line, 11)
                pdf.y -= 2
            pdf.y -= 5
        elif k == "code":
            lines = []
            for ln in (b[1] or "").split("\n"):
                while len(ln) > 92:
                    lines.append(ln[:92])
                    ln = ln[92:]
                lines.append(ln)
            for ln in lines:
                pdf.need(13)
                pdf.rect(pdf.M, pdf.y - 13, pdf.W - 2 * pdf.M, 13, (0.95, 0.96, 0.955))
                pdf.y -= 13
                pdf.text(pdf.M + 6, pdf.y + 3.3, ln, "C", 9.3, (0.15, 0.17, 0.16))
            pdf.y -= 9
        elif k == "hr":
            pdf.need(14)
            pdf.y -= 7
            pdf.line(pdf.M, pdf.y, pdf.W - pdf.M, pdf.y)
            pdf.y -= 9
        elif k == "pagebreak":
            pdf.new_page()
        elif k == "table":
            head, rows, aligns = b[1], b[2], b[3]
            n = max(1, len(head))
            tw = pdf.W - 2 * pdf.M
            # anchos proporcionales al contenido (con minimo)
            want = [max([_w(plain(h), "B", 10) for h in head[i:i + 1]] + [_w(plain(r[i]), "R", 10) for r in rows if i < len(r)] + [30]) + 12 for i in range(n)]
            tot = sum(want)
            cw = [w * tw / tot for w in want] if tot > tw else [w + (tw - tot) / n for w in want]

            def row(cells, hdr):
                wrapped = [pdf.wrap_runs(inline(c if hdr is False else c), cw[i] - 10, 10, "B" if hdr else "R") for i, c in enumerate(cells)]
                h = max(len(w) for w in wrapped) * 13 + 8
                if pdf.y - h < pdf.M + 20:
                    pdf.new_page()
                    if not hdr:
                        row(head, True)
                y_top = pdf.y
                x0 = pdf.M
                for i, lines in enumerate(wrapped):
                    pdf.rect(x0, y_top - h, cw[i], h, (0.18, 0.56, 0.38) if hdr else None, (0.8, 0.84, 0.82), 0.5)
                    yy = y_top - 4
                    for line in lines:
                        yy -= 13
                        pdf.draw_line(x0 + 5, yy + 3, line, 10, (1, 1, 1) if hdr else (0.13, 0.15, 0.14),
                                      aligns[i] if i < len(aligns) else "left", cw[i] - 10)
                    x0 += cw[i]
                pdf.y = y_top - h
            pdf.need(40)
            row(head, True)
            for r in rows:
                row([(r[i] if i < len(r) else "") for i in range(n)], False)
            pdf.y -= 12
        elif k == "img":
            p = _img_path(b[1], base)
            info = image_info(p) if p else None
            if not info:
                pdf.paragraph("[imagen no encontrada: %s]" % b[1], 10, "I")
                continue
            kind, w, h = info
            maxw = pdf.W - 2 * pdf.M
            dw = min(maxw, w * 0.75)
            dh = h * dw / w
            if dh > pdf.H - 2 * pdf.M - 40:
                dh = pdf.H - 2 * pdf.M - 40
                dw = w * dh / h
            pdf.need(dh + 10)
            data = _pdf_image(p, kind)
            if data is None:
                pdf.paragraph("[no se pudo incrustar la imagen: %s]" % os.path.basename(p), 10, "I")
                continue
            pdf.images.append(data)
            name = "Im%d" % len(pdf.images)
            pdf.y -= dh
            pdf.ops.append("q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (dw, dh, pdf.M + (maxw - dw) / 2, pdf.y, name))
            pdf.y -= 6
            if b[2]:
                pdf.paragraph(b[2], 9.5, "I", 0, (0.4, 0.42, 0.41))
            pdf.y -= 4
    # pie con numero de pagina
    total = len(pdf.pages)
    for i, ops in enumerate(pdf.pages, 1):
        s = "Página %d de %d" % (i, total)
        ops.append("BT 0.55 0.58 0.56 rg /F1 8.5 Tf %.2f 30 Td %s Tj ET" % ((pdf.W - _w(s, "R", 8.5)) / 2, _pdf_str(s)))
    _pdf_write(path, pdf, title or next((plain(b[2]) for b in blocks if b[0] == "h"), ""))
    return {"paginas": total}


def _png_decode(path):
    """PNG de 8 bits (gris, RGB, RGBA, paleta) -> (ancho, alto, rgb bytes, alpha bytes o None)."""
    data = open(path, "rb").read()
    pos, idat, plte, trns = 8, [], None, None
    w = h = depth = ctype = interlace = 0
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"IDAT":
            idat.append(chunk)
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"tRNS":
            trns = chunk
        pos += 12 + ln
    if depth != 8 or interlace:
        return None
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if f == 1:
            for k in range(ch, stride):
                line[k] = (line[k] + line[k - ch]) & 255
        elif f == 2:
            for k in range(stride):
                line[k] = (line[k] + prev[k]) & 255
        elif f == 3:
            for k in range(stride):
                line[k] = (line[k] + ((line[k - ch] if k >= ch else 0) + prev[k]) // 2) & 255
        elif f == 4:
            for k in range(stride):
                a = line[k - ch] if k >= ch else 0
                b_ = prev[k]
                c = prev[k - ch] if k >= ch else 0
                p = a + b_ - c
                pa, pb, pc = abs(p - a), abs(p - b_), abs(p - c)
                line[k] = (line[k] + (a if pa <= pb and pa <= pc else b_ if pb <= pc else c)) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    if ctype == 2:
        return w, h, bytes(out), None
    if ctype == 6:
        return w, h, bytes(b for k in range(0, len(out), 4) for b in out[k:k + 3]), bytes(out[3::4])
    if ctype == 0:
        return w, h, bytes(b for v in out for b in (v, v, v)), None
    if ctype == 4:
        return w, h, bytes(b for v in out[0::2] for b in (v, v, v)), bytes(out[1::2])
    if ctype == 3 and plte:
        rgb = bytes(b for v in out for b in plte[v * 3:v * 3 + 3])
        alpha = bytes((trns[v] if trns and v < len(trns) else 255) for v in out) if trns else None
        return w, h, rgb, alpha
    return None


def _pdf_image(path, kind):
    if kind == "jpeg":
        info = image_info(path)
        return {"w": info[1], "h": info[2], "filter": "/DCTDecode", "data": open(path, "rb").read(), "alpha": None}
    try:
        d = _png_decode(path)
    except Exception:
        d = None
    if not d:
        return None
    w, h, rgb, alpha = d
    return {"w": w, "h": h, "filter": "/FlateDecode", "data": zlib.compress(rgb, 6), "alpha": zlib.compress(alpha, 6) if alpha else None}


def _pdf_write(path, pdf, title):
    objs = []

    def add(b):
        objs.append(b if isinstance(b, bytes) else b.encode("latin-1"))
        return len(objs)
    fonts = []
    for name in ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique", "Courier"):
        fonts.append(add("<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % name))
    img_ids = []
    for im in pdf.images:
        smask = ""
        if im["alpha"]:
            sid = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n"
                      % (im["w"], im["h"], len(im["alpha"])) + im["alpha"] + b"\nendstream")
            smask = " /SMask %d 0 R" % sid
        img_ids.append(add(("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter %s%s /Length %d >>\nstream\n"
                            % (im["w"], im["h"], im["filter"], smask, len(im["data"]))).encode("latin-1") + im["data"] + b"\nendstream"))
    res = "<< /Font << %s >> /XObject << %s >> >>" % (" ".join("/F%d %d 0 R" % (i + 1, f) for i, f in enumerate(fonts)),
                                                        " ".join("/Im%d %d 0 R" % (i + 1, o) for i, o in enumerate(img_ids)))
    res_id = add(res)
    pages_id = len(objs) + 1 + 2 * len(pdf.pages)       # se reserva tras paginas y contenidos
    kids = []
    for ops in pdf.pages:
        stream = zlib.compress("\n".join(ops).encode("latin-1"))
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources %d 0 R /Contents %d 0 R >>" % (pages_id, pdf.W, pdf.H, res_id, cid)))
    assert add("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % k for k in kids), len(kids))) == pages_id
    info = add("<< /Title %s /Creator (Jayth) /Producer (Jayth) /CreationDate (D:%s) >>" % (_pdf_str(title or ""), datetime.datetime.now().strftime("%Y%m%d%H%M%S")))
    cat = add("<< /Type /Catalog /Pages %d 0 R /Lang (es-ES) >>" % pages_id)
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for o in offs:
        out.write(b"%010d 00000 n \n" % o)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, info, xref))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(out.getvalue())
    os.replace(path + ".tmp", path)


WRITERS = {".docx": write_docx, ".xlsx": write_xlsx, ".pptx": write_pptx, ".pdf": write_pdf}


def create(path, content, title=""):
    ext = os.path.splitext(path)[1].lower()
    if ext not in WRITERS:
        raise ValueError("Formato no soportado: %s. Usa .docx (Word), .xlsx (Excel), .pptx (PowerPoint) o .pdf." % (ext or "sin extensión"))
    return WRITERS[ext](path, content, title)
