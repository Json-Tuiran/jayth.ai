# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Bucle del agente (el «arnés»): habla con el modelo (API compatible con OpenAI), ejecuta herramientas con permisos,
mantiene el contexto bajo control y aprovecha al máximo modelos locales pequeños y lentos."""
import os, re, json, time, uuid, base64, socket, threading, datetime, http.client, urllib.parse
from collections import Counter
from . import tools as T
from . import harness as H
from . import osys
from . import i18n
from .i18n import tr

MODES = {
    "readonly": tr("Solo lectura: no puede escribir, ejecutar ni usar la red."),
    "plan": tr("Planificar: investiga y propone un plan; no cambia nada hasta que lo apruebes."),
    "ask": tr("Preguntar: lee solo; todo lo demás pide tu aprobación."),
    "edits": tr("Editar archivos: escribe libremente; ejecutar, red y control piden aprobación."),
    "auto": tr("Automático: hace todo sin preguntar (salvo acciones peligrosas)."),
}

WORKFLOW = """Eres Jayth, un agente que trabaja en el ordenador del usuario (%(os)s, terminal %(shell)s) con herramientas reales. Hoy es %(date)s.
Carpeta de trabajo: %(ws)s

Cómo trabajas:
1. Entiende la petición. Si falta un dato importante o hay varias opciones razonables, pregunta con ask_user (con opciones) en lugar de suponer.
2. En tareas de varios pasos, crea una lista con update_plan y actualízala al avanzar (solo una tarea in_progress a la vez).
3. Investiga antes de cambiar: list_dir, search_files y read_file. Nunca inventes rutas, contenidos ni resultados.
4. Cambia con precisión: edit_file o multi_edit para modificar (copia el fragmento exacto de read_file); write_file solo para archivos nuevos o reescrituras completas.
5. Verifica: ejecuta las pruebas, el script o el comando que corresponda y lee los errores. Si algo falla, analiza la causa antes de reintentar; no repitas una acción que ya falló.
6. Termina con un resumen breve: qué hiciste, dónde quedó y cómo comprobarlo.

Mantén al usuario al tanto mientras trabajas, como un compañero que narra lo que hace:
- Antes de cada acción (o grupo de acciones seguidas) escribe una frase corta en el idioma del usuario: qué vas a hacer y para qué. Ej.: «Creo calculadora.py con la ventana y los botones.», «Lo ejecuto para comprobar que abre sin errores.»
- Si un resultado te hace cambiar de plan o algo falla, dilo en una frase («Falla al importar tkinter; pruebo otra forma.»).
- Frases breves y concretas, sin relleno ni repetir lo que ya se ve.

Formato de las respuestas:
- Rutas de archivos y carpetas entre `comillas de código` (se muestran como enlaces para abrirlas o copiarlas).
- Si el usuario debe ejecutar algo, pon cada comando en su propio bloque ``` de una línea con el lenguaje de su terminal (```%(fence)s): aparecerá con botones para copiarlo y ejecutarlo. No le pidas que ejecute lo que puedes ejecutar tú.

Herramientas:
- run_command ejecuta %(shell)s (Python está disponible como `%(python)s`). Para servidores o procesos largos usa background=true y revisa con command_output.
%(tools)s- Preguntas sobre Jayth (cómo se usa, dónde está un botón, menú o ajuste, qué versión es, dónde guarda las cosas, qué puedes hacer): consulta jayth_guide y responde con lo que diga, nombrando los botones y menús tal como aparecen en ella (es el idioma de su interfaz). No inventes menús ni opciones.
- remember: guarda una preferencia duradera cuando el usuario te la diga (p. ej. "usa pnpm", "mis proyectos están en %(example)s").
- Si el usuario deniega una acción, no insistas: propón otra vía.
Responde en el idioma del usuario, claro y sin relleno."""

# Herramientas a demanda: un grupo básico siempre a mano y el resto por grupos que se activan cuando hacen falta (lo
# detecta Jayth por el mensaje o lo pide el modelo con use_tools). Con modelos locales, ofrecer 50 herramientas gasta
# ~8000 tokens de contexto y confunde a los modelos pequeños. Los grupos activados se añaden al final de la lista y se
# conservan en la conversación: así lo ya procesado por el modelo (caché de prompt) sigue valiendo.
CORE = ["read_file", "write_file", "edit_file", "multi_edit", "list_dir", "search_files", "move_path", "delete_path",
        "run_command", "open_target", "update_plan", "ask_user", "remember", "jayth_guide"]
GROUPS = {   # grupo: (para qué sirve, herramientas, cómo usarlas: se le da al modelo al activarlo)
    "web": ("buscar en internet, leer páginas y descargar archivos", ["web_search", "web_fetch", "download_file"],
            "- Web (solo con internet): web_search, web_fetch y download_file para buscar y leer."),
    "navegador": ("el navegador de Jayth para webs que hay que usar: buscar dentro de un sitio, formularios, iniciar sesión",
                  ["browser_open", "browser_read", "browser_click", "browser_type", "browser_nav", "browser_screenshot"],
                  "- Para webs que hay que USAR (buscar dentro de un sitio, iniciar sesión, rellenar formularios, páginas con JavaScript), el navegador integrado de Jayth: browser_open, browser_read, browser_click y browser_type por el número de cada elemento, browser_nav y browser_screenshot. El usuario lo ve a la vista y puede intervenir. Las contraseñas las escribe él, y no compres, pagues, publiques ni envíes datos personales sin su confirmación (ask_user)."),
    "control": ("manejar programas del PC: capturas, leer botones, clic, teclado, ventanas y portapapeles",
                ["screenshot", "ui_elements", "click_element", "click", "drag", "move_mouse", "scroll", "type_text", "press_keys",
                 "list_windows", "focus_window", "window_action", "clipboard"],
                "- Usar cualquier programa: ábrelo (open_target o run_command) y elige cómo manejarlo. ui_elements lista los botones, menús y campos de una ventana con su número y click_element los pulsa sin adivinar coordenadas (lo más fiable, y sirve aunque no veas imágenes). Con screenshot ves la pantalla o una ventana; zoom amplía una zona para leer texto pequeño; click, drag y scroll usan píxeles de la última captura. Además: type_text, press_keys (atajos), window_action (maximizar, mover, cerrar…) y clipboard para pasar datos entre programas."),
    "documentos": ("Word, Excel, PowerPoint y PDF, ver imágenes del disco y el lienzo junto al chat",
                   ["read_document", "create_document", "view_image", "show_canvas"],
                   "- Documentos Word, Excel, PowerPoint y PDF: read_document para leerlos y create_document para crearlos (escribes el contenido en Markdown). Imágenes del disco: view_image.\n- Páginas web, documentos largos, diagramas SVG o programas completos que el usuario quiera VER: show_canvas (lienzo junto al chat). No pegues ese contenido en tu respuesta."),
    "procesos": ("Python para datos y gráficos, procesos en segundo plano y esperas", ["run_python", "command_output", "stop_command", "wait"],
                 "- Datos (CSV, Excel), cálculos y gráficos: run_python con pandas y matplotlib; los gráficos se muestran solos al usuario. Procesos lanzados con background=true: command_output y stop_command."),
    "imagenes": ("crear imágenes nuevas en este equipo", ["generate_image"], ""),
    "conocimiento": ("buscar por significado en las carpetas de conocimiento del usuario (sus notas, documentos y proyectos)",
                     ["search_knowledge"],
                     "- search_knowledge busca por significado en las carpetas de conocimiento del usuario y devuelve los fragmentos más parecidos con su archivo y línea; después lee con read_file o read_document lo que necesites. Cita de qué archivo sale cada dato."),
    "agenda": ("olvidar recuerdos, tareas programadas, habilidades y conectar servicios externos",
               ["forget", "schedule_task", "list_tasks", "cancel_task", "use_skill", "connect_service"],
               "- forget borra un recuerdo; schedule_task, list_tasks y cancel_task gestionan tareas programadas; use_skill carga una habilidad; connect_service propone conectar un servicio externo con la cuenta del usuario."),
}
# palabras que delatan que una tarea necesitará un grupo (español, inglés y portugués; sin acentos)
def _fold(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")


_HINTS = {
    "web": r"\b(busca|buscar|busqueda|internet|web|google|noticia|pagina|url|http|www\.|descarg|search|news|website|link|enlace|precio|"
           r"cotiza|clima|pesquis|baixar|noticias|wikipedia)",
    "navegador": r"(inicia sesion|iniciar sesion|log ?in|formulario|rellena|navegador|browser|compra|reserva|portal|entrar no site|"
                 r"preencher|cadastr)",
    "control": r"(clic|click|pantalla|captura|ventana|programa\b|aplicacion|\bapp\b|raton|teclado|escribe en|screenshot|mouse|"
               r"janela|tela|aplicativo|whatsapp|blender|photoshop|explorador|bloc de notas|notepad|calculadora|paint\b|outlook|"
               r"teams|spotify|discord|telegram|panel de control|configuracion de windows|"
               r"\b(abre|abrir|abra|open)\b.*\b(escrib|pulsa|presiona|selecciona|type|press|digit|clica))",
    "documentos": r"(word|excel|powerpoint|\bpdf|docx|xlsx|pptx|documento|informe|presentacion|hoja de calculo|planilha|"
                  r"lienzo|canvas|diagrama|svg|\bimagen del|esta imagen|la imagen|report|spreadsheet|slides)",
    "procesos": r"(python|datos|\bcsv|grafic|estadistic|analiza|servidor|segundo plano|chart|plot|dataset|dados)",
    "imagenes": r"(imagen|ilustracion|logo|foto\b|fotos|dibuj|portada|icono|fondo de pantalla|image|picture|illustration|"
                r"drawing|imagem|desenh|ilustra)",
    "conocimiento": r"(mis notas|mis documentos|mis apuntes|mis archivos|mis proyectos|segun mis|en mis (notas|documentos|archivos)|"
                    r"base de conocimiento|conocimiento|my notes|my documents|my files|knowledge|minhas notas|meus documentos|meus arquivos)",
    "agenda": r"(olvida|cada (dia|manana|semana|lunes|martes|miercoles|jueves|viernes|hora)|todos los dias|programa(r)? (una )?tarea|"
              r"recordatorio|habilidad|conecta|gmail|drive|notion|canva|higgsfield|calendar|calendario|jira|linear|forget|"
              r"schedule|every (day|morning|week)|todo dia|toda semana|agendar)",
}

# las mismas pistas en francés, alemán e italiano (sin interfaz traducida, pero el agente responde en su idioma)
_HINTS_MORE = {
    "web": r"(recherch|cherche|actualit|prix|meteo|suche|nachricht|preis|wetter|ricerca|cerca |notizi|prezzo)",
    "navegador": r"(connecte-toi|formulaire|anmeld|formular|accedi|modulo|reserv)",
    "control": r"(clique|fenetre|ecran|souris|clavier|klick|fenster|bildschirm|maus|tastatur|clicca|finestra|schermo|tastiera|"
               r"\b(ouvre|offne|apri)\b.*\b(ecri|schreib|scriv|appuie|druck|premi))",
    "documentos": r"(rapport|tableur|feuille de calcul|bericht|tabelle|prasentation|rapporto|foglio di calcolo|presentazione|dokument)",
    "procesos": r"(donnees|graphique|daten|diagramm|\bdati\b|grafico)",
    "imagenes": r"(dessin|bild|zeichn|immagine|disegn)",
    "conocimiento": r"(mes notes|mes documents|meine notizen|meine dokumente|miei appunti|miei documenti)",
    "agenda": r"(chaque (jour|matin|semaine)|jeden (tag|morgen)|ogni (giorno|mattina)|rappel|erinner|promemoria|oublie|vergiss|dimentica)",
}
# japonés y chino (sin espacios entre palabras: se buscan como trozos de texto)
_HINTS_CJK = {
    "web": r"(検索|調べ|ググ|ニュース|ウェブ|インターネット|ネットで|値段|価格|天気|ダウンロード|サイト|搜索|查一下|查找|新闻|网页|网上|互联网|价格|天气|下载|网站)",
    "navegador": r"(ログイン|フォーム|ブラウザ|予約|購入|登录|表单|填写|浏览器|预订|购买)",
    "control": r"(クリック|画面|スクリーンショット|ウィンドウ|マウス|キーボード|アプリ|メモ帳|電卓|点击|屏幕|截图|窗口|鼠标|键盘|应用|记事本|计算器)",
    "documentos": r"(ワード|エクセル|パワーポイント|ドキュメント|文書|報告書|レポート|資料|表計算|スライド|プレゼン|文档|报告|表格|演示|幻灯片)",
    "procesos": r"(データ|グラフ|統計|分析|サーバー|数据|图表|统计|服务器)",
    "imagenes": r"(画像|イラスト|ロゴ|写真|絵を|描い|アイコン|壁紙|图片|图像|插画|照片|画一|绘制|图标|壁纸)",
    "conocimiento": r"(私のメモ|私の資料|私のドキュメント|私のファイル|メモによると|ナレッジ|我的笔记|我的文档|我的文件|根据我的|知识库)",
    "agenda": r"(毎日|毎朝|毎週|毎時|リマインダー|忘れて|スケジュール|定期的|每天|每周|每早|每小时|提醒|忘记|定时)",
}
for _g, _p in _HINTS_MORE.items():
    _HINTS[_g] = "(?:%s|%s|%s)" % (_HINTS[_g], _p, _fold(_HINTS_CJK[_g]))   # el texto del usuario también se pliega



def on_demand(cfg):
    return (cfg or {}).get("tools_mode", "auto") != "all"


def detect_groups(text, cfg=None, files=(), images=()):
    """Grupos que la tarea seguramente necesitará, por lo que pide el usuario (no hace falta acertar: el modelo puede
    pedir más con use_tools)."""
    t = _fold(text)
    out = [g for g, pat in _HINTS.items() if re.search(pat, t)]
    if any(os.path.splitext(f)[1].lower() in (".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pdf", ".csv") for f in files or ()):
        out.append("documentos")
    if images:
        out.append("documentos")
    if (cfg or {}).get("_project"):
        out.append("procesos")                  # en un proyecto de código: procesos en segundo plano y Python
    for n in list(H.MCP):                       # un conector nombrado en el mensaje
        if _fold(n) and _fold(n) in t:
            out.append("mcp:" + n)
    return [g for g in dict.fromkeys(out)]

PLAN_MODE = """

MODO PLANIFICAR: no modifiques nada; solo investiga (lectura). Cuando entiendas la tarea, crea el plan con update_plan (todas las tareas pending)
y explica en pocas líneas el enfoque, los archivos que tocarás y los riesgos. El usuario lo aprobará antes de ejecutarlo."""


LOOK = """

Puedes ver: cuando lo que haces tiene un resultado visible, compruébalo mirándolo, con la herramienta que mejor encaje (una captura de la pantalla o solo de una ventana, ver una imagen del disco, el lienzo…), y corrige lo que se vea mal antes de darlo por terminado. Tú decides qué y cuándo mirar según la tarea. El usuario ve tus capturas en el chat. Lo que deba quedarse abierto (ventanas, servidores) se lanza en segundo plano y se cierra al acabar."""

LOOK_BLIND = """

No ves imágenes: comprueba tu trabajo por la salida y los errores. Si el resultado es visual, una captura le sirve al usuario para verlo en el chat. Lo que deba quedarse abierto (ventanas, servidores) se lanza en segundo plano y se cierra al acabar."""


def can_see(cfg):
    """¿El modelo activo entiende imágenes? (local: tiene proyector de visión; externo: se supone que sí)."""
    if not cfg.get("vision", True):
        return False
    if cfg.get("llm_mode") == "external":
        return True
    m = next((x for x in cfg.get("models") or [] if x.get("id") == cfg.get("active_model")), None)
    return bool(m and m.get("mmproj") and os.path.isfile(m["mmproj"]))


def images_offered(cfg):
    """¿Se ofrece generate_image? Solo si está activado y el modelo activo no crea imágenes por sí mismo."""
    if not cfg.get("image_gen", True) or cfg.get("mode") in ("readonly", "plan"):
        return False
    from . import imagegen as IG
    return IG.available() and not IG.native_image_output(cfg)


IMAGES = """

Imágenes nuevas (fotos, ilustraciones, logotipos, iconos, fondos, portadas): créalas con generate_image, que funciona en este equipo. Úsala cuando el usuario lo pida o cuando la tarea lo necesite (una web, una presentación o un documento con ilustraciones), una por llamada porque tarda. Para gráficos de datos sigue usando run_python, y para diagramas o dibujos sencillos, SVG."""


def services_prompt(cfg):
    """Servicios externos: los que el usuario puede conectar (si hace falta) y cómo usar los ya conectados."""
    if not cfg.get("web_access", True) or cfg.get("mode") == "readonly" or "connect_service" in (cfg.get("tools_disabled") or []):
        return ""
    try:
        from . import conectores as CN
        off = CN.offered(cfg)
        higgs = CN.connected("higgsfield", cfg)
    except Exception:
        return ""
    out = ""
    if off:
        out += ("\n\nServicios externos que el usuario puede conectar con su propia cuenta si lo pide o la tarea lo necesita: %s. "
                "Para proponerlo usa connect_service (él pulsa «Conectar» e inicia sesión). Lo normal es trabajar en el equipo; "
                "propón un servicio solo cuando aporte algo que aquí no se puede hacer bien.") % ", ".join(
            "%s (%s)" % (c["name"], c["id"]) for c in off)
    if higgs:
        out += ("\nHiggsfield está conectado: crea imágenes y vídeos en la nube gastando créditos del usuario. Úsalo solo si lo pide "
                "o para vídeo; para imágenes, por defecto generate_image (en el equipo y gratis).")
    return out


class LLMError(Exception):
    pass


def group_guide(g):
    """Cómo usar un grupo de herramientas (se le da al modelo al activarlo)."""
    if g == "imagenes":
        return IMAGES.strip()
    if g.startswith("mcp:"):
        return "- Herramientas del conector %s: empiezan por mcp__ y su descripción dice para qué sirven." % g[4:]
    return GROUPS.get(g, ("", [], ""))[2]


def _tools_text(cfg):
    if not on_demand(cfg):                       # todas siempre: las pautas de cada grupo van en las instrucciones
        return "".join(GROUPS[g][2] + "\n" for g in ("documentos", "procesos", "control", "web", "navegador"))
    return ("- Tienes a mano las herramientas básicas. Para lo demás (web, navegador, control del PC, documentos, Python, "
            "imágenes, tareas programadas, conectores…) actívalas primero con use_tools; puedes pedir varios grupos a la vez.\n")


def system_prompt(cfg):
    """Instrucciones del sistema. Se calculan una vez por tarea para que la cache del modelo se reutilice entre pasos
    (no dependen de qué grupos de herramientas estén activos)."""
    p = WORKFLOW % {"os": osys.os_label(), "shell": osys.shell_name(), "date": datetime.date.today().isoformat(), "ws": cfg["workspace"],
                    "python": "python" if osys.WIN else "python3", "example": "D:\\Trabajo" if osys.WIN else "~/Trabajo",
                    "fence": "powershell" if osys.WIN else "bash", "tools": _tools_text(cfg)}
    lang = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "de": "alemán", "it": "italiano", "ja": "japonés",
            "zh": "chino mandarín (caracteres simplificados)"}.get(cfg.get("response_language"))
    if lang:
        p += "\nResponde siempre en %s." % lang
    elif (cfg.get("response_language") or "auto") == "auto" and i18n.LANG != "es":   # ante la duda, el idioma de su interfaz
        p += "\nSi no está claro en qué idioma escribe el usuario, responde en %s (el idioma de su interfaz)." % (
            {"en": "inglés", "pt": "portugués de Brasil", "fr": "francés", "de": "alemán", "it": "italiano", "ja": "japonés",
             "zh": "chino mandarín (caracteres simplificados)"}.get(i18n.LANG, "inglés"))
    if not cfg.get("web_access", True):
        p += "\nNo tienes acceso a internet en esta sesión."
    if cfg.get("mode") == "plan":
        p += PLAN_MODE
    elif cfg.get("mode") != "readonly":          # puede ejecutar: que compruebe lo visual mirándolo (si puede ver)
        shots = cfg.get("computer_control", True) and "screenshot" not in (cfg.get("tools_disabled") or [])
        p += LOOK if (shots and can_see(cfg)) else LOOK_BLIND if shots else ""
    if images_offered(cfg) and "generate_image" not in (cfg.get("tools_disabled") or []) and not on_demand(cfg):
        p += IMAGES
    p += services_prompt(cfg)
    if cfg.get("user_name"):
        p += "\n\nEl usuario se llama %s." % cfg["user_name"]
    if cfg.get("about_me"):
        p += "\n\n## Sobre el usuario\n" + cfg["about_me"]
    if cfg.get("response_style"):
        p += "\n\n## Cómo quiere que respondas\n" + cfg["response_style"]
    mem = "" if (cfg.get("_temp") or not cfg.get("memory_enabled", True)) else H.memory_text()
    if mem:
        p += "\n\n## Memoria (lo que el usuario te pidió recordar)\n" + mem
    try:
        from . import assistants as AS
        sk = AS.skills_prompt(cfg)
    except Exception:
        sk = ""
    if sk:
        p += "\n\n## Habilidades\n" + sk
    ctx = H.context_files(cfg["workspace"])
    if ctx:
        p += "\n\n## Instrucciones del proyecto\n" + ctx
    if cfg.get("_project"):
        p += "\n\n## Estructura de la carpeta del proyecto\n" + H.repo_map(cfg["workspace"])
    if cfg.get("custom_instructions"):
        p += "\n\n## Instrucciones adicionales\n" + cfg["custom_instructions"]
    return p


def all_schemas(cfg):
    """Todas las herramientas permitidas por el modo y los ajustes (también las de los conectores)."""
    off = set(cfg.get("tools_disabled") or [])
    if not cfg.get("web_access", True):
        off |= {n for n, t in T.TOOLS.items() if t["category"] == "net"}
    if not cfg.get("computer_control", True):
        off |= {n for n, t in T.TOOLS.items() if t["category"] == "control"}
    if cfg.get("_temp") or not cfg.get("memory_enabled", True):       # chat temporal o memoria apagada: ni guarda ni olvida
        off |= {"remember", "forget"}
    if not images_offered(cfg):                  # desactivado, sin motor para este sistema o el modelo ya crea imágenes
        off.add("generate_image")
    if not cfg.get("web_access", True):          # los servicios externos necesitan internet
        off.add("connect_service")
    try:                                         # conocimiento local: solo con carpetas elegidas y el buscador instalado
        from . import conocimiento as KN
        if not (KN.folders(cfg) and KN.installed(cfg)):
            off.add("search_knowledge")
    except Exception:
        off.add("search_knowledge")
    mode = cfg.get("mode")
    cats = {"read", "agent"} if mode == "readonly" else {"read", "agent", "net"} if mode == "plan" else None
    out = [s for s in T.schemas(cats) if s["function"]["name"] not in off]
    if mode not in ("readonly", "plan"):
        out += H.mcp_schemas()
    return out


def _group_names(g, by):
    if g.startswith("mcp:"):
        return [fn for fn in by if fn.startswith("mcp__") and H._NAMES.get(fn, ("",))[0] == g[4:]]
    return GROUPS.get(g, ("", [], ""))[1]


def group_of(name):
    """Grupo al que pertenece una herramienta ('' si es básica o desconocida)."""
    if name.startswith("mcp__"):
        hit = H._NAMES.get(name)
        return "mcp:" + hit[0] if hit else ""
    return next((g for g, (d, names, h) in GROUPS.items() if name in names), "")


def available_groups(cfg, by=None):
    """[(grupo, para qué sirve)] de los grupos con alguna herramienta permitida."""
    by = by if by is not None else {s["function"]["name"]: s for s in all_schemas(cfg)}
    out = [(g, d) for g, (d, names, h) in GROUPS.items() if any(n in by for n in names)]
    for n, srv in list(H.MCP.items()):
        if any(fn in by for fn in _group_names("mcp:" + n, by)):
            ex = ", ".join(t["name"] for t in srv.tools[:4])
            out.append(("mcp:" + n, "conector %s (%d herramientas: %s…)" % (n, len(srv.tools), ex)))
    return out


def _core(cfg):
    core = list(CORE)
    try:
        from . import assistants as AS
        if AS.enabled_skills():
            core.append("use_skill")             # con habilidades instaladas, cargarlas siempre debe estar a mano
    except Exception:
        pass
    return core


def tool_schemas(cfg, groups=None):
    """Herramientas que se ofrecen al modelo según el modo y los ajustes (sin grupos: la lista del precalentamiento).
    A demanda: las básicas, use_tools y las de los grupos activos, en este orden (lo nuevo, al final)."""
    full = all_schemas(cfg)
    if not on_demand(cfg):
        return full
    by = {s["function"]["name"]: s for s in full}
    names = [n for n in _core(cfg) if n in by]
    av = available_groups(cfg, by)
    out = [by[n] for n in names]
    if av:
        out.append({"type": "function", "function": {
            "name": "use_tools",
            "description": "Activa grupos de herramientas que aún no tienes, en cuanto la tarea los necesite (quedan activos el resto "
                           "de la conversación). Grupos: " + "; ".join("%s (%s)" % (g, d) for g, d in av) + ".",
            "parameters": {"type": "object", "properties": {"groups": {"type": "array", "items": {"type": "string"},
                                                                       "description": "Nombres de los grupos a activar"}},
                           "required": ["groups"]}}})
    seen = set(names)
    for g in groups or []:
        for n in _group_names(g, by):
            if n in by and n not in seen:
                out.append(by[n])
                seen.add(n)
    return out


_GROUP_ALIAS = {"internet": "web", "buscar": "web", "search": "web", "browser": "navegador", "navegar": "navegador",
                "pc": "control", "ordenador": "control", "computer": "control", "pantalla": "control", "raton": "control",
                "documents": "documentos", "docs": "documentos", "office": "documentos", "lienzo": "documentos", "canvas": "documentos",
                "python": "procesos", "datos": "procesos", "data": "procesos", "processes": "procesos",
                "images": "imagenes", "imagen": "imagenes", "image": "imagenes", "imagens": "imagenes",
                "memoria": "agenda", "tareas": "agenda", "tasks": "agenda", "habilidades": "agenda", "skills": "agenda",
                "servicios": "agenda", "services": "agenda"}


def resolve_group(name, cfg):
    """Nombre de grupo que da el modelo -> grupo válido ('' si no existe)."""
    g = _fold(name).strip().strip("«»\"'")
    valid = [x for x, d in available_groups(cfg)]
    if g in valid:
        return g
    g = _GROUP_ALIAS.get(g, g)
    if g in valid:
        return g
    hit = next((x for x in valid if x.startswith("mcp:") and (_fold(x[4:]) == g.replace("mcp:", "") or _fold(x[4:]) in g)), "")
    return hit


def coerce(args, schema):
    props = (schema or {}).get("properties", {})
    out = {}
    for k, v in args.items():
        t = props.get(k, {}).get("type")
        try:
            if t == "integer" and not isinstance(v, bool):
                v = int(float(v))
            elif t == "boolean" and isinstance(v, str):
                v = v.strip().lower() in ("true", "1", "yes", "si", "sí")
            elif t == "array" and isinstance(v, str):
                v = json.loads(v)
        except (TypeError, ValueError):
            pass
        out[k] = v
    return out


def parse_text_tool_calls(text):
    """Respaldo: algunos modelos escriben la llamada como texto <tool_call>...</tool_call>."""
    calls = []
    for m in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.S):
        body = m.group(1).strip()
        name, args = None, {}
        try:
            j = H.repair_json(body)
            name, args = j.get("name"), j.get("arguments", {})
            if isinstance(args, str):
                args = H.repair_json(args)
        except Exception:
            fm = re.search(r"<function=([^>\s]+)>(.*?)</function>", body, re.S)
            if fm:
                name = fm.group(1)
                for pm in re.finditer(r"<parameter=([^>\s]+)>\n?(.*?)\n?</parameter>", fm.group(2), re.S):
                    args[pm.group(1)] = pm.group(2)
        if name:
            calls.append({"id": "call_" + uuid.uuid4().hex[:8], "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}})
    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.S).strip()
    return calls, cleaned


def llm_stream(base_url, api_key, payload, holder, on_delta):
    """Llama a una API compatible con OpenAI (base_url termina en /v1) con streaming.
    holder['conn'] permite cortar la conexion desde otro hilo."""
    u = urllib.parse.urlparse(base_url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = cls(u.hostname, u.port or (443 if u.scheme == "https" else 80), timeout=10)
    holder["conn"] = conn
    try:
        conn.connect()
        conn.sock.settimeout(None)
        conn.request("POST", u.path.rstrip("/") + "/chat/completions", json.dumps(payload).encode("utf-8"),
                     {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or "local"), "Accept": "text/event-stream"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise LLMError("HTTP %d: %s" % (resp.status, resp.read(2000).decode("utf-8", "replace")))
        content, reasoning, tcs, finish, timings, usage = [], [], {}, None, None, None
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ch = json.loads(data)
            except ValueError:
                continue
            if ch.get("timings"):
                timings = ch["timings"]
            if ch.get("usage"):
                usage = ch["usage"]
            for c in ch.get("choices") or []:
                d = c.get("delta") or {}
                if d.get("reasoning_content"):
                    reasoning.append(d["reasoning_content"])
                    on_delta("reasoning", d["reasoning_content"])
                if d.get("content"):
                    content.append(d["content"])
                    on_delta("content", d["content"])
                for tc in d.get("tool_calls") or []:
                    slot = tcs.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    f = tc.get("function") or {}
                    if f.get("name"):
                        slot["name"] += f["name"]
                    if f.get("arguments"):
                        slot["args"] += f["arguments"]
                    if slot["name"]:                # el modelo está escribiendo una acción: cuál y cuánto lleva
                        on_delta("tool", "%s\t%d" % (slot["name"], len(slot["args"])))
                if c.get("finish_reason"):
                    finish = c["finish_reason"]
        return {"content": "".join(content), "reasoning": "".join(reasoning), "tool_calls": [tcs[k] for k in sorted(tcs)],
                "finish": finish, "timings": timings, "usage": usage}
    finally:
        try:
            conn.close()
        except Exception:
            pass
        holder["conn"] = None


def _plain(c):
    return c if isinstance(c, str) else " ".join(p.get("text", "") for p in (c or []) if isinstance(p, dict) and p.get("type") == "text")


def clean_title(t):
    """Deja el titulo que propone el modelo en una sola linea limpia: sin comillas, prefijos ni punto final."""
    t = re.sub(r"<think>.*?</think>", "", t or "", flags=re.S)
    lines = [l.strip() for l in t.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    t = re.sub(r"^(t[ií]tulo|title)\s*:\s*", "", lines[0], flags=re.I)
    for _ in range(2):        # «"Titulo".» -> Titulo
        t = t.strip(" \t*#_`\"'«»“”‘’").rstrip(" .:;,")
    t = re.sub(r"\s+", " ", t)
    return t[:60].rstrip() if len(t) <= 60 else t[:59].rstrip() + "…"


def make_title(cfg, messages):
    """Pide al modelo elegido un titulo breve para la conversacion. Devuelve el titulo o '' si no se pudo."""
    user = next((_plain(m.get("content")) for m in messages if m["role"] == "user" and not m.get("_auto")), "")
    answer = next((_plain(m.get("content")) for m in reversed(messages) if m["role"] == "assistant" and _plain(m.get("content")).strip()), "")
    user = re.split(r"\n\n### [^\n]+\nRuta: ", user)[0]       # sin el contenido de los adjuntos, solo lo que escribio
    if not user.strip():
        return ""
    external = cfg.get("llm_mode") == "external"
    base = cfg["external_url"].rstrip("/") if external else "http://127.0.0.1:%d/v1" % int(cfg["llm_port"])
    key = cfg.get("external_key") if external else ""
    payload = {"model": (cfg.get("external_model") or "local") if external else "local", "stream": True,
               "max_tokens": 400 if external else 40, "temperature": 0.3,   # fuera no se puede apagar el razonamiento: margen
               "messages": [{"role": "system", "content": "Pones títulos breves a conversaciones. Respondes solo con el título."},
                            {"role": "user", "content": "Escribe un título de 2 a 6 palabras, en el idioma del usuario, sin comillas ni punto final, "
                                                        "que resuma de qué trata esta conversación.\n\nUsuario: %s\n\nAgente: %s"
                                                        % (user[:1500], answer[:1000])}]}
    if not external:   # sin razonamiento: el titulo debe salir en un instante
        payload.update({"cache_prompt": False, "chat_template_kwargs": {"enable_thinking": False, "reasoning_effort": "low"}})
    try:
        return clean_title(llm_stream(base, key, payload, {}, lambda k, t: None)["content"])
    except Exception:
        return ""


class Run:
    def __init__(self, session, settings, emit, images_dir):
        self.s = session            # dict con 'messages', 'allowed', 'plan'…
        self.cfg = settings
        self.emit = emit
        self.images_dir = images_dir
        self.stop = threading.Event()
        self.pending = {}           # tool_call_id -> {event, decision}
        self.holder = {}
        self.sid = settings.get("_sid", "sin_sesion")
        self.ctx = T.Ctx(settings["workspace"], self.stop, images_dir, int(settings["max_tool_output"]),
                         {"sid": self.sid, "brave_key": settings.get("brave_key"), "search_provider": settings.get("search_provider", "auto"),
                          "searxng_url": settings.get("searxng_url", ""), "command_timeout": int(settings.get("command_timeout", 60))})
        self._buf, self._last = {"kind": None, "text": ""}, 0.0
        self._prep = ("", 0.0)
        self.calls_seen = Counter()
        self.fails_seen = Counter()
        self.truncated = False
        self.system = system_prompt(settings)          # fijo durante toda la tarea (cache de prompt)
        self.groups = list(self.s.get("tool_groups") or [])     # grupos de herramientas ya activos en esta conversación
        self.tools = tool_schemas(settings, self.groups)
        self.sampling = self._sampling()

    def _sampling(self):
        c = self.cfg
        base = {"temperature": float(c["temperature"]), "top_p": float(c["top_p"]), "top_k": int(c["top_k"]), "min_p": float(c.get("min_p", 0))}
        if c.get("sampling", "auto") == "auto":
            rec = H.sampling_for(c.get("_model_title", ""), bool(c.get("thinking")))
            if rec:
                base.update(rec)
        return base

    # ---- control externo
    def request_stop(self):
        self.stop.set()
        c = self.holder.get("conn")
        if c is not None:
            try:
                c.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                c.close()
            except Exception:
                pass
        for p in self.pending.values():
            p["event"].set()

    def resolve(self, call_id, decision):
        p = self.pending.get(call_id)
        if p:
            p["decision"] = decision
            p["event"].set()
            return True
        return False

    # ---- salida de texto con agrupacion de deltas
    def _delta(self, kind, text):
        if kind == "tool":             # «nombre\tcaracteres»: como mucho un aviso por segundo (también se guarda)
            name, _, n = text.partition("\t")
            now = time.time()
            if name != self._prep[0] or now - self._prep[1] >= 1.0:
                self._flush()
                self._prep = (name, now)
                self.emit({"t": "tool_prep", "name": name, "chars": int(n or 0)})
            return
        b = self._buf
        if b["kind"] not in (None, kind):
            self._flush()
        b["kind"] = kind
        b["text"] += text
        if time.time() - self._last > 0.12:
            self._flush()

    def _flush(self):
        b = self._buf
        if b["text"]:
            self.emit({"t": "delta", "kind": b["kind"], "text": b["text"]})
        b["kind"], b["text"], self._last = None, "", time.time()

    # ---- contexto
    def _estimate(self, msgs):
        n = 0
        for m in msgs:
            c = m.get("content")
            if isinstance(c, list):
                for p in c:
                    n += 700 if p.get("type") in ("image_url", "image_ref") else len(p.get("text", "")) / 3.2
            else:
                n += len(c or "") / 3.2
            if m.get("tool_calls"):
                n += len(json.dumps(m["tool_calls"], ensure_ascii=False)) / 3.2
            n += 6
        return n * float(self.s.get("_ratio", 1.0))    # calibrado con los tokens reales que informa el servidor

    def _fixed_tokens(self):
        return (len(self.system) + len(json.dumps(self.tools, ensure_ascii=False))) / 3.2 * float(self.s.get("_ratio", 1.0))

    def _budget(self):
        return int(self.cfg["n_ctx"]) - int(self.cfg["max_tokens"]) - self._fixed_tokens() - 300

    def _to_llm(self, msgs=None):
        msgs = self.s["messages"] if msgs is None else msgs
        refs = [(i, j) for i, m in enumerate(msgs) if isinstance(m.get("content"), list)
                for j, p in enumerate(m["content"]) if p.get("type") == "image_ref"]
        keep = set(refs[-int(self.cfg["keep_images"]):]) if self.cfg.get("vision") and self.cfg["keep_images"] else set()
        out = []
        for i, m in enumerate(msgs):
            c = m.get("content")
            if isinstance(c, list):
                parts = []
                for j, p in enumerate(c):
                    if p.get("type") != "image_ref":
                        parts.append(p)
                    elif (i, j) in keep and os.path.isfile(os.path.join(self.images_dir, p["name"])):
                        with open(os.path.join(self.images_dir, p["name"]), "rb") as f:
                            b64 = base64.b64encode(f.read()).decode()
                        ext = os.path.splitext(p["name"])[1].lower()
                        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/png")
                        parts.append({"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}})
                    else:
                        parts.append({"type": "text", "text": "[imagen anterior omitida para ahorrar contexto]"})
                m = dict(m, content=parts)
            out.append({k: v for k, v in m.items() if not k.startswith("_")})   # claves internas (_auto) no van al modelo
        return out

    def _maybe_compact(self, base, key):
        """Si la conversacion se acerca al limite, resume la parte antigua con el propio modelo (en vez de olvidarla)."""
        msgs = self.s["messages"]
        budget = self._budget()
        if self._estimate(msgs) <= 0.85 * budget:
            return
        last_user = max((i for i, m in enumerate(msgs) if m["role"] == "user" and not m.get("_auto")), default=0)
        old, recent = msgs[:last_user], msgs[last_user:]
        if len(old) < 4:
            return
        lines = []
        for m in old:
            c = m.get("content")
            text = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if p.get("type") == "text")
            if m.get("tool_calls"):
                text += " [acciones: %s]" % ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
            if m["role"] == "tool":
                text = text[:400]
            lines.append("%s: %s" % ({"user": "Usuario", "assistant": "Agente", "tool": "Resultado"}.get(m["role"], m["role"]), text[:2500]))
        transcript = "\n".join(lines)[-24000:]
        payload = {"model": "local", "stream": True, "max_tokens": 700, "temperature": 0.2, "cache_prompt": False,
                   "messages": [{"role": "system", "content": "Resume conversaciones de trabajo de forma fiel y compacta."},
                                {"role": "user", "content": "Resume esta conversación entre un usuario y su agente para poder continuarla. Incluye: objetivo, "
                                                            "decisiones, archivos creados o modificados (con rutas), comandos importantes, problemas pendientes y "
                                                            "preferencias del usuario. Máximo 250 palabras.\n\n" + transcript}]}
        if self.cfg.get("llm_mode") == "external":
            payload["model"] = self.cfg.get("external_model") or "local"
            payload.pop("cache_prompt")
        self.emit({"t": "info", "text": tr("La conversación es larga: estoy resumiendo la parte antigua para liberar memoria del modelo…")})
        try:
            res = llm_stream(base, key, payload, self.holder, lambda k, t: None)
            summary = res["content"].strip()
        except Exception:
            summary = ""
        if not summary:
            return
        self.s["messages"] = [{"role": "user", "_auto": True, "content": "[Resumen de la conversación anterior]\n" + summary},
                              {"role": "assistant", "content": "Entendido. Continúo con ese contexto."}] + recent
        self.emit({"t": "compacted", "text": summary})

    def _fit(self, msgs):
        budget = self._budget()
        if self._estimate(msgs) <= budget:
            return msgs
        msgs = [dict(m) for m in msgs]
        for m in msgs:                                    # 1) recortar salidas antiguas de herramientas
            if m["role"] == "tool" and len(m.get("content") or "") > 400:
                m["content"] = m["content"][:300] + "\n...[recortado para ahorrar contexto]"
                if self._estimate(msgs) <= budget:
                    return msgs
        while self._estimate(msgs) > budget and len(msgs) > 2:   # 2) ultimo recurso: descartar lo mas antiguo
            msgs.pop(0)
            while msgs and msgs[0]["role"] != "user":
                msgs.pop(0)
        return msgs

    # ---- herramientas
    def _tool(self, name):
        if name.startswith("mcp__"):
            srv, real = H.mcp_resolve(name)
            if not srv:
                return None
            schema = next((t.get("inputSchema") for t in srv.tools if t["name"] == real), None) or {}
            def fn(a, ctx, srv=srv, real=real):
                try:
                    return srv.call(real, a)
                except H.MCPError as e:           # mensaje claro para el modelo, sin el nombre de la excepcion
                    raise T.ToolError(str(e))
            return {"name": name, "category": "mcp", "parameters": schema, "fn": fn}
        return T.TOOLS.get(name)

    def _needs_approval(self, tool, name, args):
        mode, cat = self.cfg["mode"], tool["category"]
        if name in (self.cfg.get("tools_disabled") or []):
            return "blocked"
        if mode == "readonly" and cat not in ("read", "agent"):
            return "blocked"
        if mode == "plan" and cat not in ("read", "agent", "net"):
            return "blocked"
        if T.is_dangerous(name, args, self.ctx):
            return "pending"
        if self._account_of(name) and cat not in self.s.setdefault("allowed", []):
            return "pending"        # cambia algo en una cuenta del usuario (publicar, enviar, gastar créditos): siempre se pregunta
        if cat in ("read", "agent") or cat in self.s.setdefault("allowed", []) or mode == "auto" or (mode == "edits" and cat == "write"):
            return "auto"
        if name == "run_command":   # comandos que el usuario marco como seguros (p. ej. "git status", "npm test")
            cmd = str(args.get("command", "")).strip().lower()
            if any(p.strip() and cmd.startswith(p.strip().lower()) for p in self.cfg.get("auto_allow_commands") or []) and not any(c in cmd for c in ";|&`$("):
                return "auto"
        return "pending"

    def _account_of(self, name):
        """Nombre del servicio si la herramienta actúa en una cuenta del usuario y no es de solo lectura; si no, ''."""
        if not name.startswith("mcp__"):
            return ""
        srv, real = H.mcp_resolve(name)
        if srv is None or not getattr(srv, "account", lambda: False)():
            return ""
        t = next((t for t in srv.tools if t.get("name") == real), {}) or {}
        return "" if (t.get("annotations") or {}).get("readOnlyHint") is True else srv.name

    def _wait(self, cid):
        ev = {"event": threading.Event(), "decision": None}
        self.pending[cid] = ev
        while not ev["event"].wait(0.3):
            if self.stop.is_set():
                break
        self.pending.pop(cid, None)
        return ev["decision"]

    def _files_of(self, name, args):
        if name == "move_path":
            return [self.ctx.path(args.get("source", "")), self.ctx.path(args.get("dest", ""))]
        if args.get("path"):
            return [self.ctx.path(args["path"])]
        return []

    def _activate(self, groups):
        """Añade grupos de herramientas (al final de la lista: lo ya procesado por el modelo sigue valiendo). Devuelve los nuevos."""
        new = [g for g in groups if g and g not in self.groups]
        if new:
            self.groups += new
            self.s["tool_groups"] = list(self.groups)
            self.tools = tool_schemas(self.cfg, self.groups)
        return new

    def _use_tools(self, args):
        want = args.get("groups") or args.get("group") or []
        if isinstance(want, str):
            want = re.split(r"[,;\s]+", want)
        ok_g, bad = [], []
        for w in want:
            g = resolve_group(w, self.cfg)
            (ok_g if g else bad).append(g or str(w))
        if not ok_g:
            return False, "Grupos desconocidos: %s. Disponibles: %s." % (", ".join(bad) or "(ninguno)", ", ".join(g for g, d in available_groups(self.cfg)))
        new = self._activate(ok_g)
        txt = ("Activadas: %s. Ya puedes usar sus herramientas." % ", ".join(new)) if new else "Esos grupos ya estaban activos."
        guides = [group_guide(g) for g in new if group_guide(g)]
        if guides:
            txt += "\n" + "\n".join(guides)
        if bad:
            txt += "\n(No existen: %s.)" % ", ".join(bad)
        return True, txt

    def _exec(self, call):
        """Ejecuta una llamada. Devuelve (ok, texto, imagen, extra)."""
        f = call["function"]
        name, raw = f["name"], f.get("arguments") or "{}"
        cid = call["id"]
        tool = self._tool(name)
        try:
            args = H.repair_json(raw)
        except ValueError as e:
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": {"_raw": str(raw)[:500]}, "category": "read", "approval": "auto"})
            if self.truncated:
                return False, ("Tu respuesta se cortó por el límite de longitud y los argumentos quedaron incompletos. Divide el trabajo: "
                               "escribe el archivo en partes (write_file con la primera parte y luego multi_edit/edit_file para añadir el resto)."), None, {}
            return False, "Argumentos JSON inválidos (%s). Envía un objeto JSON válido con los parámetros de la herramienta." % e, None, {}
        if name == "use_tools":                         # activar grupos de herramientas (lo gestiona el bucle; no se muestra)
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": "agent", "approval": "auto"})
            return self._use_tools(args) + (None, {})
        if tool is None:
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": "read", "approval": "auto"})
            return False, "Herramienta desconocida: %s. Usa una de las disponibles." % name, None, {}
        offered = {s["function"]["name"] for s in self.tools}
        if name not in offered:
            if name not in {s["function"]["name"] for s in all_schemas(self.cfg)}:   # desactivada en Ajustes, sin internet…
                self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": "blocked"})
                return False, "La herramienta %s no está disponible en esta sesión (está desactivada o no se permite en este modo)." % name, None, {}
            self._activate([group_of(name)])            # la conocía aunque no estaba cargada: se activa su grupo y se usa
        args = coerce(args, tool["parameters"])
        sig = name + json.dumps(args, sort_keys=True, ensure_ascii=False)[:2000]
        self.calls_seen[sig] += 1
        if self.fails_seen[sig] >= 2 or self.calls_seen[sig] >= 4:
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": "auto"})
            return False, ("Ya intentaste exactamente esta misma acción varias veces. No la repitas: cambia de enfoque, revisa la causa del fallo "
                           "o pregunta al usuario con ask_user."), None, {}
        # --- herramientas del propio agente
        if name == "ask_user":
            opts = [str(o) for o in (args.get("options") or [])][:6]
            self.emit({"t": "question", "id": cid, "question": str(args.get("question", "")), "options": opts})
            d = self._wait(cid)
            if not d or not d.startswith("answer:"):
                self.emit({"t": "answer", "id": cid, "text": ""})
                return False, "El usuario no respondió (detuvo la tarea).", None, {}
            ans = d[7:]
            self.emit({"t": "answer", "id": cid, "text": ans})
            return True, "Respuesta del usuario: " + ans, None, {}
        approval = self._needs_approval(tool, name, args)
        self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": approval,
                   "danger": T.is_dangerous(name, args, self.ctx), "account": self._account_of(name)})
        if approval == "blocked":
            why = "el modo Planificar solo permite investigar" if self.cfg["mode"] == "plan" else "el modo actual es solo lectura o la herramienta está desactivada"
            return False, "Bloqueado: %s." % why, None, {}
        if approval == "pending":
            d = self._wait(cid)
            if self.stop.is_set() and d is None:
                self.emit({"t": "approval", "id": cid, "decision": "cancel"})
                return False, "Cancelado por el usuario.", None, {}
            self.emit({"t": "approval", "id": cid, "decision": d})
            if d == "allow_category":
                self.s.setdefault("allowed", []).append(tool["category"])
            elif d != "allow":
                return False, "El usuario denegó esta acción.%s" % (" Motivo: " + d[5:] if d and d.startswith("deny:") and len(d) > 5 else ""), None, {}
        extra = {}
        if name in T.WRITE_TOOLS:
            try:
                H.snapshot(self.sid, cid, self._files_of(name, args))
                extra["undo"] = True
            except Exception:
                pass
        try:
            self.ctx.call_id = cid                   # las herramientas largas publican su avance con este id
            r = tool["fn"](args, self.ctx)
            if name == "update_plan":
                self.s["plan"] = [{"content": str(i.get("content", "")), "status": str(i.get("status", "pending"))} for i in args.get("items") or []]
                self.emit({"t": "plan", "items": self.s["plan"]})
            if isinstance(r, dict):
                if r.get("ui"):                          # datos para la interfaz (lienzo, archivos creados…)
                    extra.update(r["ui"])
                imgs = list(r.get("images") or ([r["image"]] if r.get("image") else []))
                return True, T.clip(r["text"], self.ctx.max_out), (imgs or None), extra
            return True, T.clip(str(r), self.ctx.max_out), None, extra
        except T.Abort:
            raise
        except T.ToolError as e:
            self.fails_seen[sig] += 1
            return False, str(e), None, dict(getattr(e, "ui", None) or {})
        except Exception as e:
            self.fails_seen[sig] += 1
            return False, "%s: %s" % (type(e).__name__, e), None, {}

    def _repair(self):
        """Si se corto a mitad, toda llamada a herramienta debe tener su respuesta para que el historial sea valido."""
        msgs = self.s["messages"]
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i]["role"] == "assistant":
                if msgs[i].get("tool_calls"):
                    done = {m.get("tool_call_id") for m in msgs[i + 1:] if m["role"] == "tool"}
                    for c in msgs[i]["tool_calls"]:
                        if c["id"] not in done:
                            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": "Interrumpido."})
                break

    # ---- bucle principal
    def run(self, text, image_names=(), attachments=""):
        msgs = self.s["messages"]
        body = text + (("\n\n" + attachments) if attachments else "")
        if on_demand(self.cfg):                         # grupos que seguramente hagan falta: activos desde el primer paso
            files = [l[4:].strip() for l in attachments.splitlines() if l.startswith("### ")]
            valid = {g for g, d in available_groups(self.cfg)}
            new = self._activate([g for g in detect_groups(text, self.cfg, files, image_names) if g in valid])
            guides = [group_guide(g) for g in new if group_guide(g)]
            if new:                                     # sus pautas van con el mensaje (no cambian las instrucciones fijas)
                body += "\n\n[Herramientas activadas para esta tarea: %s]%s" % (", ".join(new), ("\n" + "\n".join(guides)) if guides else "")
        content = body if not image_names else [{"type": "text", "text": body}] + [{"type": "image_ref", "name": n} for n in image_names]
        msgs.append({"role": "user", "content": content})
        self.emit({"t": "user", "text": text, "images": list(image_names), "files": [l[4:].strip() for l in attachments.splitlines() if l.startswith("### ")]})
        external = self.cfg.get("llm_mode") == "external"
        base = self.cfg["external_url"].rstrip("/") if external else "http://127.0.0.1:%d/v1" % int(self.cfg["llm_port"])
        key = self.cfg.get("external_key") if external else ""
        e = self.cfg.get("effort") or ""
        effort = e if e in ("low", "medium", "high") else ("medium" if self.cfg.get("thinking") else "low")
        try:
            for step in range(int(self.cfg["max_steps"])):
                if self.stop.is_set():
                    break
                self._maybe_compact(base, key)
                msgs = self.s["messages"]
                self.emit({"t": "turn_start", "step": step + 1})
                sent = self._fit(self._to_llm())
                payload = {"model": (self.cfg.get("external_model") or "local") if external else "local", "stream": True,
                           "stream_options": {"include_usage": True},
                           "messages": [{"role": "system", "content": self.system}] + sent,
                           "temperature": self.sampling["temperature"], "top_p": self.sampling["top_p"],
                           "max_tokens": int(self.cfg["max_tokens"]) * (2 if effort == "high" else 1)}
                if not external:   # parametros propios de llama.cpp (una API estricta podria rechazarlos)
                    # esfuerzo: Qwen/DeepSeek usan enable_thinking; gpt-oss y otros, reasoning_effort (los demas los ignoran)
                    payload.update({"top_k": self.sampling["top_k"], "cache_prompt": True, "min_p": self.sampling["min_p"],
                                    "repeat_penalty": float(self.cfg.get("repeat_penalty", 1.0)),
                                    "chat_template_kwargs": {"enable_thinking": effort != "low", "reasoning_effort": effort}})
                    if int(self.cfg.get("seed", -1)) >= 0:
                        payload["seed"] = int(self.cfg["seed"])
                payload["tools"] = self.tools
                try:
                    res = llm_stream(base, key, payload, self.holder, self._delta)
                except (ConnectionRefusedError, socket.timeout, OSError) as e:
                    self._flush()
                    if self.stop.is_set():
                        break
                    self.emit({"t": "error", "text": tr("No puedo conectar con el modelo en %s (%s). %s") % (
                        base, e, tr("Comprueba que ese servidor esté encendido.") if external else tr("Enciéndelo con el botón «Encender modelo»."))})
                    break
                except LLMError as e:
                    self._flush()
                    self.emit({"t": "error", "text": tr("Error del modelo: %s") % e})
                    break
                except Exception as e:
                    self._flush()
                    if self.stop.is_set():
                        break
                    self.emit({"t": "error", "text": tr("Conexión con el modelo interrumpida: %s: %s") % (type(e).__name__, e)})
                    break
                self._flush()
                if self.stop.is_set():
                    break
                # calibrar la estimacion de tokens con lo que realmente conto el servidor
                real = (res.get("usage") or {}).get("prompt_tokens")
                if real:
                    est = (self._estimate(sent) / float(self.s.get("_ratio", 1.0))) + self._fixed_tokens() / float(self.s.get("_ratio", 1.0))
                    if est > 50:
                        self.s["_ratio"] = round(max(0.5, min(3.0, 0.5 * float(self.s.get("_ratio", 1.0)) + 0.5 * real / est)), 3)
                self.truncated = res["finish"] == "length"
                # ids propios y unicos: algunos servidores repiten ids (p. ej. "call_0") entre turnos
                calls = [{"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                          "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for c in res["tool_calls"] if c["name"]]
                text_out = res["content"]
                if not calls and "<tool_call>" in text_out:
                    calls, text_out = parse_text_tool_calls(text_out)
                tm = res.get("timings") or {}
                self.emit({"t": "stats", "prompt_n": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"), "gen_n": tm.get("predicted_n"),
                           "tps": tm.get("predicted_per_second"), "finish": res["finish"],
                           "ctx_used": (res.get("usage") or {}).get("prompt_tokens"), "ctx_max": int(self.cfg["n_ctx"])})
                am = {"role": "assistant", "content": text_out}
                if calls:
                    am["tool_calls"] = calls
                msgs.append(am)
                self.emit({"t": "assistant_end", "text": text_out})
                if not calls:
                    if not text_out.strip():
                        self.emit({"t": "info", "text": (tr("El modelo no escribió respuesta (se alcanzó el límite de tokens; sube «longitud máxima» o desactiva el pensamiento).")
                                                       if res["finish"] == "length" else tr("El modelo no escribió respuesta."))})
                    break
                images = []
                for call in calls:
                    if self.stop.is_set():
                        msgs.append({"role": "tool", "tool_call_id": call["id"], "content": "Cancelado por el usuario."})
                        continue
                    ok, out, img, extra = self._exec(call)
                    names = []
                    for one in ([img] if isinstance(img, (bytes, bytearray)) else (img or [])):
                        n = uuid.uuid4().hex[:12] + ".png"
                        with open(os.path.join(self.images_dir, n), "wb") as f:
                            f.write(one)
                        names.append(n)
                    images += names[:2]                  # el modelo ve como mucho dos por acción (cada imagen gasta contexto)
                    name = names[0] if names else None
                    if len(names) > 1:
                        extra = dict(extra, images=names)    # la interfaz las muestra todas
                    self.emit(dict({"t": "tool_result", "id": call["id"], "ok": ok, "text": out, "image": name}, **extra))
                    msgs.append({"role": "tool", "tool_call_id": call["id"], "content": out if ok else "ERROR: " + out})
                if images:
                    msgs.append({"role": "user", "_auto": True,
                                 "content": [{"type": "text", "text": "Imagen resultante:"}] + [{"type": "image_ref", "name": n} for n in images]})
                if self.stop.is_set():
                    break
            else:
                self.emit({"t": "info", "text": tr("Se alcanzó el máximo de %s pasos. Escribe «continúa» si quieres seguir.") % self.cfg["max_steps"]})
        except T.Abort as e:
            self.emit({"t": "error", "text": str(e)})
            self.stop.set()
        except Exception as e:
            self.emit({"t": "error", "text": tr("Error interno: %s: %s") % (type(e).__name__, e)})
        finally:
            self._flush()
            self._repair()
            if self.stop.is_set():
                self.emit({"t": "info", "text": "Detenido."})
            if self.cfg.get("mode") == "plan" and self.s.get("plan") and not self.stop.is_set():
                self.emit({"t": "plan_ready"})
            self.emit({"t": "turn_end"})
