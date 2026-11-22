# Jayth · Copyright (C) 2026 Ing. Jeison Tuiran · Licencia GPL-3.0 (ver LICENSE y MARCA.md)
# SPDX-License-Identifier: GPL-3.0-only
"""Bucle del agente (el «arnés»): habla con el modelo (API compatible con OpenAI), ejecuta herramientas con permisos,
mantiene el contexto bajo control y aprovecha al máximo modelos locales pequeños y lentos."""
import os, re, json, time, uuid, base64, socket, hashlib, threading, datetime, http.client, urllib.parse
from collections import Counter
from . import tools as T
from . import harness as H
from . import apis as API
from . import consumo as USAGE
from . import errores as ERR
from . import claude as CL
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
Para hacer algo, llama a la herramienta: escribir la llamada o el comando en tu respuesta no hace nada, y nunca digas que algo está hecho si no lo hiciste con una herramienta.

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
Responde en el idioma del usuario, claro y sin relleno. Si razonas antes de responder, razona también en su idioma."""

# Herramientas a demanda: un grupo básico siempre a mano y el resto por grupos que se activan cuando hacen falta (lo
# detecta Jayth por el mensaje o lo pide el modelo con use_tools). Con modelos locales, ofrecer 50 herramientas gasta
# ~8000 tokens de contexto y confunde a los modelos pequeños. Los grupos activados se añaden al final de la lista y se
# conservan en la conversación: así lo ya procesado por el modelo (caché de prompt) sigue valiendo.
CORE = ["read_file", "write_file", "edit_file", "multi_edit", "replace_in_files", "list_dir", "search_files", "move_path", "delete_path",
        "run_command", "open_target", "update_plan", "ask_user", "remember", "list_memory", "jayth_guide", "undo_changes", "delegate"]

# ---- ayudantes (subagentes): otra copia del modelo, con la memoria en blanco, que hace una subtarea de lectura y devuelve
# solo su informe. Sirve para que una búsqueda o una lectura larga no llene la conversación del agente principal.
SUB_OFF = {"delegate", "ask_user", "update_plan", "remember", "forget", "schedule_task", "cancel_task", "list_tasks", "connect_service",
           "generate_image", "show_canvas", "use_skill", "open_target"}
SUB_BRIEF = ("\n\n## Eres un ayudante\nTrabajas para el agente principal de Jayth, que te encargó una subtarea y responde de lo que "
             "hagas: solo recibirá tu último mensaje. %s No puedes preguntar al usuario ni pedirle permisos: si algo queda fuera de lo "
             "que se te permite, no busques otra forma de hacerlo; dilo en tu informe. Haz la subtarea completa y termina con un informe "
             "para el agente principal: lo que encontraste o hiciste, con rutas, números de línea, direcciones y datos concretos; lo que "
             "no pudiste hacer y por qué. No expliques los pasos que diste ni ofrezcas seguir: solo el resultado.")
# Lo que puede hacer un ayudante lo decide el agente principal al encargarle la subtarea (y el usuario aprueba ese encargo
# como aprobaría la acción equivalente): modo → (categoría con la que se pide permiso, categorías de herramientas, texto).
SUB_MODES = {
    "read": ("agent", {"read", "agent", "net"}, "Puedes leer, buscar y consultar la web, pero no cambiar nada (ni archivos ni programas)."),
    "edit": ("write", {"read", "agent", "net", "write"},
             "Puedes leer, buscar, consultar la web y crear o cambiar archivos, solo dentro de: %s. No puedes ejecutar comandos."),
    "full": ("exec", {"read", "agent", "net", "write", "exec"},
             "Puedes leer, buscar, consultar la web, ejecutar comandos y crear o cambiar archivos, estos solo dentro de: %s."),
}


def sub_mode(v):
    m = str(v or "read").strip().lower()
    m = {"write": "edit", "editar": "edit", "escribir": "edit", "work": "full", "todo": "full", "completo": "full", "lectura": "read", "leer": "read"}.get(m, m)
    return m if m in SUB_MODES else "read"


def subagents_on(cfg):
    """¿Se ofrece `delegate`? «auto»: solo con modelos por API (con un modelo local cada ayudante relee desde cero las
    instrucciones y las herramientas, y eso en CPU son minutos). Un ayudante no tiene ayudantes."""
    if cfg.get("_sub"):
        return False
    v = cfg.get("subagents", "auto")
    return v == "on" or (v == "auto" and cfg.get("llm_mode") == "external")
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
    "procesos": ("Python para datos y gráficos, procesos en segundo plano y esperas", ["run_python", "command_output", "list_commands", "stop_command", "wait"],
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
    """¿Herramientas por grupos, según lo que pide cada mensaje? Con los modelos locales ahorra memoria y tiempo de
    lectura. Con un modelo por API no: activar un grupo cambia la lista de herramientas, que es lo primero que lee el
    servicio, y anula toda su caché (cada paso se cobraría entero); se ofrecen todas desde el principio."""
    cfg = cfg or {}
    return cfg.get("tools_mode", "auto") != "all" and cfg.get("llm_mode") != "external"


# El modelo anuncia una acción («Voy a ejecutarlo:» + el comando) y termina sin llamar a la herramienta: pasa con modelos
# pequeños. Se le recuerda una vez por mensaje (y el usuario lo ve en el chat).
_ANNOUNCE = re.compile(r"(voy a |vamos a |procedo a |a continuaci[oó]n |ahora (lo |la )?(ejecut|corr|lanz|prueb|abr)|i'?ll |i will |"
                       r"let me |let's |now i |next,? i |vou |agora vou |je vais |ich werde |lass mich |jetzt |ora |adesso |vado a |"
                       r"次に|実行します|試します|接下来|我将|我会|现在运行|现在执行)", re.I)
_CMD_BLOCK = re.compile(r"```[ \t]*(?:bash|sh|shell|zsh|powershell|pwsh|ps1|cmd|bat|console|terminal)?[ \t]*\n[ \t]*[$>]?[ \t]*"
                        r"(?:python3?|py|pip3?|npm|npx|node|git|dir|ls|cd|mkdir|copy|move|del|rm|cat|type|echo|start|\.\\|\./)\b", re.I)
NUDGE = ("[Aviso automático de Jayth, no lo escribió el usuario] Anunciaste una acción pero no usaste ninguna herramienta, así que "
         "no se hizo. Si hace falta, hazla ahora llamando a la herramienta adecuada; si ya está hecha, da el resultado al usuario y "
         "termina, en el idioma del usuario. No respondas a este aviso ni lo menciones.")


# o solo lo anuncia en la última frase («Primero revisaré la carpeta.», «I'll run it now.») con un verbo de acción
_V_ES = r"(?:revis|ejecut|cre|comprob|verific|busc|abr|le|escrib|list|descarg|instal|edit|mir|consult|prob|analiz|lanz|guard|mov|borr|elimin)"
_INTENT = re.compile(
    r"\b" + _V_ES + r"(?:aré|eré|iré)\b|\b(?:voy|vamos) a " + _V_ES + r"\w*|"
    r"\b(?:i'?ll|i will|let me|let's)\s+(?:now\s+|first\s+)?(?:run|check|create|open|read|write|list|search|look|install|edit|execute|"
    r"verify|test|make|save|delete|move)\b|"
    r"\b(?:vou|vamos)\s+(?:verificar|executar|criar|abrir|ler|escrever|listar|procurar|buscar|instalar|editar|testar|rodar|salvar|"
    r"apagar|mover)\b|\b(?:verificar|executar|criar|abrir|escrever|listar|procurar|instalar|editar|testar|rodar|salvar)ei\b|"
    r"\bje vais\s+(?:vérifier|exécuter|créer|ouvrir|lire|écrire|lister|chercher|installer|modifier|tester|lancer|enregistrer|"
    r"supprimer|déplacer)\b|"
    r"\bich werde\b.*\b(?:prüfen|ausführen|erstellen|öffnen|lesen|schreiben|auflisten|suchen|installieren|bearbeiten|testen|starten|"
    r"speichern|löschen|verschieben)\b|"
    r"\b(?:controllerò|eseguirò|creerò|aprirò|leggerò|scriverò|cercherò|installerò|modificherò|verificherò|proverò|avvierò|salverò|"
    r"eliminerò|sposterò)\b|\b(?:vado a|ora)\s+(?:controllare|eseguire|creare|aprire|leggere|scrivere|cercare|installare|modificare|"
    r"verificare|provare)\b|"
    r"(?:確認|実行|作成|検索|インストール|編集|保存|削除|移動)します[。．]?$|(?:開き|読み|書き|調べ|試し)ます[。．]?$|"
    r"(?:我(?:将|会|先|来)|让我|首先|接下来).{0,12}(?:检查|运行|执行|创建|打开|读取|写入|搜索|查找|安装|编辑|测试|保存|删除|移动|查看)", re.I)
_OFFER = re.compile(r"(si quieres|si deseas|si prefieres|cuando quieras|if you want|if you'd like|whenever you|se quiser|si vous le|"
                    r"si tu veux|wenn du willst|wenn du möchtest|se vuoi|必要であれば|ご希望|如果你|需要的话)", re.I)
# espera la decisión del usuario: «Una vez elijamos, instalaré…», «Cuando me digas, empiezo…», «Dime cuál prefieres y…»
_WAITS = re.compile(r"(una vez (que )?(elij|decid|me (digas|confirmes|indiques)|lo (confirmes|decidas))|cuando (me )?(digas|elijas|"
                    r"decidas|confirmes|indiques)|en cuanto (me )?(digas|elijas|confirmes)|dime (cu[aá]l|qu[eé]|si)|av[ií]same|"
                    r"once you (choose|decide|confirm|tell)|when you (choose|decide|confirm|tell)|let me know|tell me (which|what|if)|"
                    r"assim que (voc[eê] )?(escolher|decidir|confirmar)|me diga|dès que vous|dites-moi|sobald du|sag mir|"
                    r"appena (mi )?(dici|scegli)|dimmi|決めたら|教えてください|告诉我|确定后)", re.I)


def asks_user(text):
    """¿Termina preguntándole algo al usuario o esperando su decisión? Entonces no hay acción pendiente que recordarle:
    el turno acaba y la respuesta es del usuario (Gemma: «¿Prefieres 3D o 2D? … Una vez elijamos, instalaré…»)."""
    prose = re.sub(r"```.*?(```|$)", " ", str(text or ""), flags=re.S).strip()
    paras = [p for p in re.split(r"\n\s*\n", prose) if p.strip()]
    tail = "\n".join(paras[-2:])[-700:]
    return bool(re.search(r"[?？]", tail)) or bool(_WAITS.search(tail))


NUDGE_WRITTEN = ("[Aviso automático de Jayth, no lo escribió el usuario] Escribiste la llamada a «%s» como texto, así que no se "
                 "ejecutó y lo que digas de su resultado no es cierto. Si hace falta, llámala de verdad como herramienta; si no, "
                 "corrige lo que le dijiste al usuario y termina, en el idioma del usuario. No respondas a este aviso ni lo menciones.")


NUDGE_EMPTY = ("[Aviso automático de Jayth, no lo escribió el usuario] Tu última respuesta llegó vacía. Sigue con la tarea donde "
               "la dejaste, con las herramientas que hagan falta, o, si ya terminaste, da el resultado al usuario, en su idioma. "
               "No respondas a este aviso ni lo menciones.")
NUDGE_QUIET = ("[Aviso automático de Jayth, no lo escribió el usuario] Tu respuesta anterior se quedó generando sin producir "
               "texto ni acción, y Jayth la interrumpió. Continúa la tarea donde ibas: si toca usar una herramienta, llámala ahora "
               "directamente, sin anunciarla; si ya terminaste, da el resultado al usuario, en su idioma. No respondas a este "
               "aviso ni lo menciones.")
NUDGE_QUIET_API = ("[Aviso automático de Jayth, no lo escribió el usuario] Tu respuesta anterior no llegó: el servicio estuvo "
                   "varios minutos sin enviar nada y Jayth cortó la petición. Nada de lo que escribías en ella se ejecutó. Continúa "
                   "la tarea donde ibas; si ibas a escribir un archivo muy largo, hazlo en varias acciones más pequeñas. No "
                   "respondas a este aviso ni lo menciones.")
_CUT_TAIL = (" Lo último que ves en la conversación es lo último que se hizo de verdad; lo que estuvieras escribiendo después no "
             "llegó a ejecutarse. Si retomas la tarea, comprueba primero en qué estado quedó.")
CUT_SHORT = {"stop": "tu turno anterior no terminó: el usuario pulsó «Parar» mientras trabajabas." + _CUT_TAIL,
             "error": "tu turno anterior no terminó: se cortó por un error del modelo o de la conexión, y tu última respuesta no llegó." + _CUT_TAIL,
             "closed": "tu turno anterior no terminó: Jayth se cerró mientras trabajabas." + _CUT_TAIL}
STEER = ("[Mensaje nuevo del usuario, escrito mientras trabajabas. Tenlo en cuenta desde ahora: si cambia lo que pide, "
         "ajusta lo que queda de la tarea; si solo añade algo, sigue con ello incluido.]\n%s")
NUDGE_OFFER = ("[Aviso automático de Jayth, no lo escribió el usuario] Le propusiste al usuario «%s» como si fuera un comando, "
               "pero es una de tus herramientas: él no puede usarla. Si conviene hacerlo, llámala tú; si no, quítala de la "
               "respuesta y termina, en el idioma del usuario. No respondas a este aviso ni lo menciones.")
_OFFER_CALL = re.compile(r"(puedes|podr[ií]as|si (lo )?prefieres|si quieres|si deseas|you can|you could|if you (want|prefer|like)|"
                         r"voc[eê] pode|se preferir|vous pouvez|si vous|du kannst|sie k[oö]nnen|puoi|se preferisci|できます|可以)", re.I)


def offered_call(text, name):
    """¿Le propone al usuario la herramienta como si fuera un comando suyo («Puedes abrirlo con: open_target "x"»)? No
    dice haberla hecho: ni se avisa de que «no se hizo» ni se convierte en una llamada real (nadie la pidió)."""
    t = str(text or "")
    m = re.search(r"(?<![\w.])" + re.escape(name) + r"(?!\w)", t)
    if not m:
        return False
    before = re.sub(r"```[^\n]*\n?", " ", t[:m.start()]).strip()
    last = [x for x in re.split(r"(?<=[.!?。！])\s+|\n\s*\n", before) if x.strip()]
    return bool(last and _OFFER_CALL.search(last[-1]))


def written_tool_call(text, names):
    """La herramienta que el modelo escribió como texto en vez de llamarla («delete_path(path=…)», {"name": "delete_path"…}):
    no se ejecutó, aunque el modelo pueda decir que sí."""
    t = str(text or "")
    code = "\n".join(re.findall(r"```[^\n]*\n(.*?)```", t, re.S))      # bloques de código
    for n in sorted(set(names), key=len, reverse=True):
        if len(n) <= 3:
            continue
        e = re.escape(n)
        # «nombre(…)», «nombre{clave: …}» / «call:nombre{…}» (el formato propio de Gemma, sin sus marcas), {"name": "nombre"…}
        if re.search(r"(?<![\w.])" + e + r"\s*[({]", t) or re.search(r'"name"\s*:\s*"' + e + '"', t) or \
                re.search(r"(?m)^[ \t]*[$>]?[ \t]*" + e + (r"(?:[ \t]|$)" if "_" in n else r"(?:[ \t]+-|[ \t]*$|[ \t]+\w+=)"), code):
            return n
    return None


_ARG = re.compile(r"""--([\w-]+)\s+("[^"]*"|'[^']*'|\S+)|(\w+)=("[^"]*"|'[^']*'|\S+)|("[^"]*"|'[^']*'|\S+)""")


def _unq(v):
    return v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'" else v


_BQ = '<|"|>'                                                          # comillas del formato de Gemma
_BKEY = re.compile(r"""["']?([A-Za-z_]\w*)["']?\s*[:=]\s*""")
_BEND = re.compile(r"""\s*(?:\}|,\s*["']?[A-Za-z_]\w*["']?\s*[:=])""")   # tras un valor: «}» o la siguiente clave


def _brace_args(s, i):
    """Los datos de una llamada escrita al estilo de Gemma, «nombre{clave: "valor", n: 3}», desde la llave s[i].
    Un texto termina en la comilla que va seguida de «}» o de otra clave (así sirven comillas sin escapar dentro de un
    código de varias líneas). Devuelve el diccionario o None si no se entiende."""
    args, i, n = {}, i + 1, len(s)
    while i < n:
        while i < n and s[i] in " \t\r\n,":
            i += 1
        if i < n and s[i] == "}":
            return args
        m = _BKEY.match(s, i)
        if not m:
            return None
        key, i = m.group(1), m.end()
        if s.startswith(_BQ, i):
            j = s.find(_BQ, i + len(_BQ))
            if j < 0:
                return None
            args[key], i = s[i + len(_BQ):j], j + len(_BQ)
        elif i < n and s[i] in "\"'":
            q, j = s[i], i + 1
            while True:
                j = s.find(q, j)
                if j < 0:
                    return None
                if s[j - 1] != "\\" and _BEND.match(s, j + 1):
                    break
                j += 1
            raw, i = s[i + 1:j], j + 1
            val = raw.replace("\\" + q, q)
            if q == '"' and "\\" in raw and "\n" not in raw:   # en una sola línea con escapes al estilo JSON («\n», «\"»)
                try:
                    val = json.loads('"' + raw + '"')
                except ValueError:
                    pass
            args[key] = val
        elif i < n and s[i] in "[{":
            try:
                args[key], i = json.JSONDecoder().raw_decode(s, i)
            except ValueError:
                return None
        else:
            m = re.compile(r"[^,}\n]*").match(s, i)
            args[key], i = m.group(0).strip(), m.end()
    return None


def _typed_args(fn, args, pos=()):
    """Los datos de una llamada escrita, completados con los posicionales y con el tipo que pide la herramienta; None si
    falta algún obligatorio, sobra alguno o no tiene su tipo."""
    spec = (fn.get("parameters") or {}).get("properties") or {}
    props = list(spec.keys())
    req = list((fn.get("parameters") or {}).get("required") or props[:1])
    args = dict(args)
    for k, v in zip([p for p in props if p not in args], pos):
        args[k] = v
    if not all(k in args for k in req) or not all(k in props for k in args):
        return None
    for k, v in list(args.items()):
        t = (spec.get(k) or {}).get("type")
        if t in ("integer", "number"):
            try:
                args[k] = int(v) if t == "integer" else float(v)
            except (TypeError, ValueError):
                return None
        elif t == "boolean" and not isinstance(v, bool):
            if str(v).lower() not in ("true", "false"):
                return None
            args[k] = str(v).lower() == "true"
        elif t == "string" and not isinstance(v, str):
            return None
    return args


def parse_written_call(text, schemas):
    """Convierte la llamada que el modelo escribió como texto en una real, si se entienden sus datos:
    «delete_path(path='x')», «delete_path "x"», «run_command --command dir», «run_command command="python a.py"»,
    «run_python{code: "…"}» (Gemma). Devuelve (nombre, argumentos) o None. Solo si están todos los obligatorios y cada
    dato tiene el tipo que pide."""
    import ast
    by = {s["function"]["name"]: s["function"] for s in schemas or []}
    for m in re.finditer(r"(?<![\w.])([A-Za-z_]\w+)\s*\{", str(text or "")):     # estilo Gemma, puede ocupar varias líneas
        if m.group(1) in by:
            args = _brace_args(str(text), m.end() - 1)
            args = _typed_args(by[m.group(1)], args) if args is not None else None
            if args is not None:
                return m.group(1), args
    code = re.findall(r"```[^\n]*\n(.*?)```", str(text or ""), re.S)
    lines = [l.strip().lstrip("$>").strip() for b in code for l in b.splitlines()] + [l.strip() for l in str(text or "").splitlines()]
    for line in lines:
        name = re.match(r"([A-Za-z_]\w+)(?!\s*\{)", line)            # «nombre{…}» ya se miró arriba, entero
        if not name or name.group(1) not in by:
            continue
        fn = by[name.group(1)]
        args, pos = {}, []
        rest = line[len(name.group(1)):].strip()
        try:
            if rest.startswith("("):                          # estilo Python
                node = ast.parse(name.group(1) + rest, mode="eval").body
                if not isinstance(node, ast.Call):
                    continue
                pos = [ast.literal_eval(x) for x in node.args]
                args = {k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg}
            else:                                             # estilo consola
                for m in _ARG.finditer(rest):
                    if m.group(1):
                        args[m.group(1).replace("-", "_")] = _unq(m.group(2))
                    elif m.group(3):
                        args[m.group(3)] = _unq(m.group(4))
                    else:
                        pos.append(_unq(m.group(5)))
        except (ValueError, SyntaxError):
            continue
        args = _typed_args(fn, args, pos)
        if args is not None:
            return name.group(1), args
    return None


def announced_action(text):
    """¿Termina anunciando una acción que no hizo? Con el comando escrito, o en la última frase con un verbo de acción
    (no si pregunta o lo ofrece: «¿Lo ejecuto?», «Si quieres, lo ejecutaré»)."""
    t = str(text or "").strip()
    if not t or t.endswith(("?", "？")) or asks_user(t):
        return False
    tail = t[-600:]
    if _ANNOUNCE.search(tail) and _CMD_BLOCK.search(tail):
        return True
    blocks = list(re.finditer(r"```[^\n]*\n.*?(?:```|$)", t, re.S))
    if blocks and not t[blocks[-1].end():].strip():              # acaba en un bloque largo: lo anunciado va justo antes
        lead = re.sub(r"```.*?(```|$)", " ", t[:blocks[-1].start()], flags=re.S)[-300:]
        if _ANNOUNCE.search(lead) and _CMD_BLOCK.search(blocks[-1].group(0)):
            return True
    prose = re.sub(r"```.*?(```|$)", " ", t, flags=re.S)        # la última frase fuera de los bloques de código
    last = [x for x in re.split(r"(?<=[.!。！])\s+|\n+", prose.strip()) if x.strip()]
    last = last[-1] if last else ""
    return bool(_INTENT.search(last)) and not _OFFER.search(last)


# Idioma del mensaje del usuario: los modelos pequeños tienden a contestar en el idioma de las instrucciones (español)
_SCRIPTS = (("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"), ("zh", r"[\u4e00-\u9fff]"), ("ru", r"[\u0400-\u04ff]"),
            ("ar", r"[\u0600-\u06ff]"), ("he", r"[\u0590-\u05ff]"), ("el", r"[\u0370-\u03ff]"), ("th", r"[\u0e00-\u0e7f]"),
            ("hi", r"[\u0900-\u097f]"))
_WORDS = {"es": "el los las del que y en un una por para con no es se como más pero qué cómo dónde este esta mi mis puedes quiero",
          "en": "the and of to in is that it for you with on this be are can what how please my your i do does",
          "pt": "o os as do da que e em um uma para com não você é isso como mais meu minha pode quero está",
          "fr": "le les des et est que pour pas vous qui dans sur avec ce cette je mon ma une peux veux comment",
          "de": "der die das und ist nicht ich du ein eine zu den mit es auf für sie was wie bitte mein kannst",
          "it": "il lo gli di che e un una per non è sono con del della come mi ti puoi voglio questo cosa"}
_WORDS = {k: set(v.split()) for k, v in _WORDS.items()}
LANG_ES = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "de": "alemán", "it": "italiano", "ja": "japonés",
           "zh": "chino", "ko": "coreano", "ru": "ruso (u otro idioma de alfabeto cirílico)", "ar": "árabe", "he": "hebreo",
           "el": "griego", "th": "tailandés", "hi": "hindi"}


def legible(text):
    """¿Parece texto escrito, o el modelo se desbocó («?………..? …. ……...…?»)? Menos de un 40 % de letras o cifras
    (de cualquier escritura) entre lo que no es espacio = no se entiende."""
    t = [c for c in str(text or "") if not c.isspace()]
    if len(t) < 4:
        return True
    return sum(c.isalnum() for c in t) / len(t) >= 0.4


def guess_language(text):
    """Idioma del mensaje si se sabe con seguridad (por su escritura o por sus palabras más comunes), o None."""
    t = str(text or "")
    for code, pat in _SCRIPTS:
        if len(re.findall(pat, t)) >= 2:
            return code
    words = re.findall(r"[a-záéíóúàèìòùâêîôûãõçñüöäß']+", t.lower())
    if len(words) < 3:
        return None
    score = sorted(((sum(w in v for w in words), k) for k, v in _WORDS.items()), reverse=True)
    (best, lang), (second, _) = score[0], score[1]
    return lang if best >= 2 and best >= second + 2 else None


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

APPROVAL_MODE = """

Algunas acciones necesitan la aprobación del usuario: llama a la herramienta igualmente; Jayth le muestra la acción con «Permitir» y «Denegar» y espera su respuesta. No pidas permiso en el chat ni escribas la llamada como texto. Si la deniega, no insistas con lo mismo: pregunta qué prefiere."""

PLAN_MODE = """

MODO PLANIFICAR: no modifiques nada; solo investiga (lectura). Cuando entiendas la tarea, crea el plan con update_plan (todas las tareas pending)
y explica en pocas líneas el enfoque, los archivos que tocarás y los riesgos. El usuario lo aprobará antes de ejecutarlo."""


LOOK = """

Puedes ver: cuando lo que haces tiene un resultado visible, compruébalo mirándolo, con la herramienta que mejor encaje (una captura de la pantalla o solo de una ventana, ver una imagen del disco, el lienzo…), y corrige lo que se vea mal antes de darlo por terminado. Tú decides qué y cuándo mirar según la tarea. El usuario ve tus capturas en el chat. Lo que deba quedarse abierto (ventanas, servidores) se lanza en segundo plano y se cierra al acabar."""

LOOK_BLIND = """

No ves imágenes: comprueba tu trabajo por la salida y los errores. Para manejar programas usa ui_elements y click_element (te dice qué cambió en la ventana) y el teclado; no puedes hacer clic por coordenadas. Si el resultado es visual, una captura le sirve al usuario para verlo en el chat. Lo que deba quedarse abierto (ventanas, servidores) se lanza en segundo plano y se cierra al acabar."""


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
                "Para proponerlo usa connect_service%s (él pulsa «Conectar» e inicia sesión). Lo normal es trabajar en el equipo; "
                "propón un servicio solo cuando aporte algo que aquí no se puede hacer bien.") % (
            ", ".join("%s (%s)" % (c["name"], c["id"]) for c in off),
            " (si no está en tu lista, activa antes el grupo «agenda» con use_tools)" if on_demand(cfg) else "")
    if higgs:
        out += ("\nHiggsfield está conectado: crea imágenes y vídeos en la nube gastando créditos del usuario. Úsalo solo si lo pide "
                "o para vídeo; para imágenes, por defecto generate_image (en el equipo y gratis).")
    return out


class LLMError(Exception):
    """Error del modelo o del servicio. status: código HTTP (si lo hubo); body: lo que respondió; retry_after: segundos
    que pidió esperar; tries: cuántas veces se reintentó antes de rendirse."""

    def __init__(self, msg, status=None, body="", retry_after=None):
        super().__init__(msg)
        self.status, self.body, self.retry_after, self.tries = status, body or str(msg), ERR.retry_after(retry_after), 0


RETRY_WAITS = (4, 10, 25, 60)     # espera entre intentos ante un error pasajero (o lo que pida el servicio, hasta 120 s)


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
    return ("- Siempre tienes las herramientas básicas. Las demás van por grupos (web, navegador, control del PC, documentos, "
            "Python, imágenes, tareas programadas, conectores…): Jayth activa solo los que parece pedir cada mensaje (te lo dice "
            "en él) y esas ya están en tu lista; si necesitas una que no está en tu lista, activa su grupo con use_tools "
            "(puedes pedir varios a la vez).\n")


def volatile_parts(cfg):
    """Lo que las instrucciones del sistema llevan y cambia solo, sin que el usuario toque los ajustes: la fecha, la lista
    de archivos del proyecto y la memoria."""
    mem = "" if (cfg.get("_temp") or not cfg.get("memory_enabled", True)) else H.memory_text()
    return {"date": datetime.date.today().isoformat(), "repo": H.repo_map(cfg["workspace"]) if cfg.get("_project") else "", "mem": mem,
            "ctx": H.context_files(cfg["workspace"])}


def changes_note(now, seen):
    """Texto para el mensaje nuevo con lo que cambió desde la última vez que se le contó al modelo ('' si nada)."""
    seen = seen or {}
    notes = []
    if now.get("date") != seen.get("date"):
        notes.append("Hoy es %s." % now.get("date"))
    if now.get("repo") != seen.get("repo") and now.get("repo"):
        notes.append("Estructura actual de la carpeta del proyecto:\n" + now["repo"])
    if now.get("mem") != seen.get("mem"):
        notes.append("Memoria actual (lo que el usuario te pidió recordar):\n" + (now.get("mem") or "(vacía)"))
    if "ctx" in seen and now.get("ctx") != seen.get("ctx"):
        notes.append("Instrucciones del proyecto actualizadas (sustituyen a las del inicio):\n" + (now.get("ctx") or "(ya no hay)"))
    return ("\n\n[Datos actualizados por Jayth desde el inicio de la conversación]\n" + "\n".join(notes)) if notes else ""


def system_prompt(cfg, frozen=None):
    """Instrucciones del sistema. Son lo primero que lee el motor: si cambia una letra, relee toda la conversación.
    Por eso lo que cambia solo (fecha, archivos del proyecto, memoria) se fija al empezar la conversación (`frozen`, lo
    que devolvió volatile_parts entonces) y sus cambios se le cuentan al modelo en el mensaje nuevo (changes_note).
    No dependen de qué grupos de herramientas estén activos."""
    parts = frozen if isinstance(frozen, dict) else volatile_parts(cfg)
    svc = osys.synced_service(cfg["workspace"])      # p. ej. Documentos dentro de OneDrive: que no ponga ahí lo que la sincronización daña
    ws = cfg["workspace"] + ((" (esta carpeta se sincroniza con %s: no crees dentro bases de datos en uso, entornos virtuales ni "
                              "node_modules sin avisar al usuario de que la sincronización puede dañarlos)" % svc) if svc else "")
    # (la fecha es la del día en que empezó la conversación: así no cambia el principio de lo que lee el modelo; si
    # cambia el día, el mensaje nuevo lo dice)
    p = WORKFLOW % {"os": osys.os_label(), "shell": osys.shell_label(), "date": (parts.get("date") or datetime.date.today().isoformat())
                    + " (el día en que empezó esta conversación; si un mensaje trae otra fecha, esa es la de hoy)", "ws": ws,
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
    if cfg.get("mode") in ("ask", "edits"):
        p += APPROVAL_MODE
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
    mem = parts.get("mem") or ""
    if mem:
        p += "\n\n## Memoria (lo que el usuario te pidió recordar)\n" + mem
    try:
        from . import assistants as AS
        sk = AS.skills_prompt(cfg)
    except Exception:
        sk = ""
    if sk:
        p += "\n\n## Habilidades\n" + sk
    ctx = parts["ctx"] if "ctx" in parts else H.context_files(cfg["workspace"])    # (congeladas como la fecha)
    if ctx:
        p += "\n\n## Instrucciones del proyecto\n" + ctx
    if cfg.get("_project"):
        p += "\n\n## Estructura de la carpeta del proyecto\n" + (parts.get("repo") or "(vacía al empezar la conversación)")
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
    elif not can_see(cfg):         # sin ver la captura no sabe qué hay en unas coordenadas: ui_elements + click_element
        off |= {"click", "drag", "move_mouse"}
    if cfg.get("_temp") or not cfg.get("memory_enabled", True):       # chat temporal o memoria apagada: ni guarda ni olvida
        off |= {"remember", "forget", "list_memory"}
    if not images_offered(cfg):                  # desactivado, sin motor para este sistema o el modelo ya crea imágenes
        off.add("generate_image")
    if not cfg.get("web_access", True):          # los servicios externos necesitan internet
        off.add("connect_service")
    try:                                         # sin habilidades instaladas, use_skill solo podría fallar
        from . import assistants as AS
        if not AS.enabled_skills(cfg):
            off.add("use_skill")
    except Exception:
        pass
    try:                                         # conocimiento local: solo con carpetas elegidas y el buscador instalado
        from . import conocimiento as KN
        if not (KN.folders(cfg) and KN.installed(cfg)):
            off.add("search_knowledge")
    except Exception:
        off.add("search_knowledge")
    if not subagents_on(cfg):
        off.add("delegate")
    mode = cfg.get("mode")
    cats = {"read", "agent"} if mode == "readonly" else {"read", "agent", "net"} if mode == "plan" else None
    if cfg.get("_sub"):                          # un ayudante: lo que le permitió el agente principal, y nunca más que a él
        off |= SUB_OFF
        allowed = SUB_MODES[sub_mode(cfg["_sub"])][1]
        cats = allowed & (cats if cats is not None else allowed)
    out = [s for s in T.schemas(cats) if s["function"]["name"] not in off]
    if mode not in ("readonly", "plan") and not cfg.get("_sub"):
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


_TLS = []
_TLS_LOCK = threading.Lock()


def tls_context():
    """Contexto TLS compartido: se crea una vez (leer el almacén de certificados de Windows en cada petición era lento)."""
    with _TLS_LOCK:
        if not _TLS:
            import ssl
            _TLS.append(ssl.create_default_context())
        return _TLS[0]


# Tope de razonamiento de «Medio» si no se sabe nada del modelo. Lo normal es el que corresponde a su tamaño
# (core.think_budgets): sin topes, en los modelos que solo encienden o apagan el razonamiento (Qwen, Gemma, GLM…)
# «Medio» y «Alto» eran lo mismo. Lo aplica el motor (llama.cpp, campo por petición).
THINK_BUDGET_MEDIUM = 1024


def local_think(effort, style, budgets=None):
    """Lo que entiende el motor local para el esfuerzo elegido, según lo que trae el modelo de fábrica (style):
    'levels' (niveles propios, como gpt-oss), 'toggle' (encender/apagar), 'always' (razona siempre) o 'none'; y los topes
    de cada nivel a la medida del modelo (budgets: {'medium': n, 'high': n o None}).
    Devuelve (chat_template_kwargs, campos extra de la petición). Los argumentos de la plantilla son los mismos en todos
    los casos (así el precalentamiento coincide); lo que cambia es el tope de razonamiento."""
    kw = {"enable_thinking": effort != "low", "reasoning_effort": effort}
    extra = {}
    b = budgets or {"medium": THINK_BUDGET_MEDIUM, "high": None}
    if style in ("toggle", "always") and effort in ("medium", "high"):
        if b.get(effort):
            extra["thinking_budget_tokens"] = int(b[effort])
    elif style == "always" and effort == "low":
        extra["thinking_budget_tokens"] = 0               # no se puede apagar: se corta en cuanto empieza
    return kw, extra


INTERRUPTED = "Interrumpido."
_DAY_WARNED = {}     # aviso de gasto del día ya dado: fecha -> límite (una vez por día y límite)
# Consultas sin efectos fuera de la categoría «read»: repetirlas tras una acción no es un bucle
QUERY_TOOLS = {"list_windows", "screenshot", "ui_elements", "browser_read", "browser_screenshot", "command_output", "wait",
               "list_commands", "list_memory",
               "list_tasks"}
CUT_CALL = ("No se ejecutó: tu respuesta se cortó por el límite de salida a mitad de esta acción y sus datos llegaron "
            "incompletos (hacerla así habría dejado, por ejemplo, un archivo a medias). Divídela en partes más pequeñas: "
            "escribe el archivo en varias veces (write_file con la primera parte y luego edit_file o multi_edit para añadir "
            "el resto) o haz menos cosas en cada llamada.")
CUT_TEXT = ("[Aviso de Jayth: tu respuesta se cortó por el límite de salida. Continúa exactamente donde lo dejaste, sin "
            "repetir lo ya escrito.]")
RECOVERED = "\n[Jayth se cerró justo después de esta acción; este resultado se recuperó de su registro.]"


def repair_history(msgs, events=None):
    """Deja el historial como lo exigen los servicios: cada mensaje del asistente con llamadas a herramientas va seguido,
    justo después, de una respuesta por llamada. Tras un corte (Jayth se cerró, un error a mitad) faltaba alguna o
    quedaba más abajo, detrás de un mensaje nuevo, y el servicio rechazaba la conversación entera (HTTP 400) en cada
    turno. Recoloca las respuestas, recupera del registro del chat (events) el resultado que no llegó a guardarse,
    pone «Interrumpido.» si no hay nada y quita respuestas sueltas sin su llamada. Devuelve cuántos cambios hizo."""
    found = {}
    for e in events or ():
        if e.get("t") == "tool_result" and e.get("id"):
            found[e["id"]] = e

    def from_log(cid):
        e = found.get(cid)
        if e is None:
            return None
        txt = str(e.get("text") or "")
        return (txt if e.get("ok") else "ERROR: " + txt) + RECOVERED

    answers = {}
    for m in msgs:
        if m.get("role") == "tool":
            answers.setdefault(m.get("tool_call_id"), []).append(m)
    placed = set()                                    # respuestas ya colocadas (por identidad)

    def take(t, cid):
        placed.add(id(t))
        if t.get("content") == INTERRUPTED and from_log(cid):     # el registro sabe cómo acabó
            return dict(t, content=from_log(cid)), 1
        return t, 0

    out, changes, i = [], 0, 0
    while i < len(msgs):
        m = msgs[i]
        if m.get("role") == "tool":                   # suelta (sin su llamada justo antes) o ya colocada en su sitio
            if id(m) not in placed:
                changes += 1
            i += 1
            continue
        out.append(m)
        i += 1
        if m.get("role") != "assistant" or not m.get("tool_calls"):
            continue
        ids = [c.get("id") for c in m["tool_calls"]]
        left = list(ids)
        while i < len(msgs) and msgs[i].get("role") == "tool" and msgs[i].get("tool_call_id") in left:
            t, ch = take(msgs[i], msgs[i].get("tool_call_id"))  # las que ya van justo detrás, en su orden: se quedan
            left.remove(t.get("tool_call_id"))
            out.append(t)
            changes += ch
            i += 1
        for cid in left:                              # las que faltan: de más abajo, del registro o «Interrumpido.»
            t = next((x for x in answers.get(cid, ()) if id(x) not in placed), None)
            if t is not None:
                t, _ = take(t, cid)
                out.append(t)
            else:
                out.append({"role": "tool", "tool_call_id": cid, "content": from_log(cid) or INTERRUPTED})
            changes += 1
    if changes:
        msgs[:] = out
    return changes


def hidden_reasoning(usage):
    """Tokens que el servicio dedicó a razonar sin mostrarlo (OpenAI, Gemini, xAI…), si lo dice; si no, None."""
    if not isinstance(usage, dict):
        return None
    det = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    n = det.get("reasoning_tokens") if isinstance(det, dict) else None
    n = n if n is not None else usage.get("reasoning_tokens")
    try:
        return int(n) if n else None
    except (TypeError, ValueError):
        return None


class ThinkTags:
    """Separa el razonamiento que un servidor deja dentro del texto entre etiquetas (<think>…</think>, <thought>…</thought>)
    cuando la respuesta empieza por ellas. Funciona trozo a trozo: una etiqueta puede llegar partida entre dos trozos."""
    OPEN = ("<think>", "<thought>", "<thinking>")

    def __init__(self):
        self.state = "start"            # start: aún no se sabe; think: dentro; text: fuera (ya no se buscan más)
        self.buf = ""
        self.close = ""

    def feed(self, text):
        """-> [(tipo, texto)] con tipo 'reasoning' o 'content'."""
        out = []
        self.buf += text
        while self.buf:
            if self.state == "text":
                out.append(("content", self.buf))
                self.buf = ""
            elif self.state == "start":
                s = self.buf.lstrip()
                tag = next((t for t in self.OPEN if s.startswith(t)), None)
                if tag:
                    self.state, self.close = "think", "</" + tag[1:]
                    self.buf = s[len(tag):]
                elif s and any(t.startswith(s) for t in self.OPEN):
                    break                                  # puede ser el principio de una etiqueta: esperar al siguiente trozo
                elif s:
                    self.state = "text"
                else:
                    break
            else:                                          # dentro del razonamiento
                i = self.buf.find(self.close)
                if i >= 0:
                    if i:
                        out.append(("reasoning", self.buf[:i]))
                    self.buf = self.buf[i + len(self.close):].lstrip("\n")
                    self.state = "text"
                else:
                    keep = next((k for k in range(min(len(self.close) - 1, len(self.buf)), 0, -1)
                                 if self.close.startswith(self.buf[-k:])), 0)
                    if len(self.buf) > keep:
                        out.append(("reasoning", self.buf[:len(self.buf) - keep]))
                    self.buf = self.buf[len(self.buf) - keep:]
                    break
        return out

    def flush(self):
        rest, self.buf = self.buf, ""
        return [("reasoning" if self.state == "think" else "content", rest)] if rest else []


def delta_parts(d):
    """Razonamiento y texto de un trozo de respuesta, sea cual sea el servicio: [(tipo, texto)]."""
    out = []
    r = d.get("reasoning_content") or d.get("reasoning") or d.get("thinking")
    if isinstance(r, str) and r:
        out.append(("reasoning", r))
    elif isinstance(d.get("reasoning_details"), list):          # OpenRouter (cuando no manda «reasoning»)
        for x in d["reasoning_details"]:
            t = isinstance(x, dict) and (x.get("text") or x.get("summary"))
            if isinstance(t, str) and t:
                out.append(("reasoning", t))
    c = d.get("content")
    if isinstance(c, str) and c:
        out.append(("content", c))
    elif isinstance(c, list):                                   # Mistral: trozos con tipo
        for x in c:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "thinking":
                th = x.get("thinking")
                th = "".join(y.get("text", "") for y in th if isinstance(y, dict)) if isinstance(th, list) else (th or "")
                if th:
                    out.append(("reasoning", th))
            elif x.get("type") == "text" and x.get("text"):
                out.append(("content", x["text"]))
    return out


# campos de un trozo de respuesta que Jayth ya entiende; el resto (si un servicio añade algo propio) se guarda para devolvérselo
_KNOWN_DELTA = {"role", "content", "tool_calls", "reasoning_content", "reasoning", "thinking", "refusal", "function_call", "audio",
                "annotations", "logprobs"}
_KNOWN_CALL = {"index", "id", "type", "function"}


def merge_extra(dst, src):
    """Junta lo que llega por partes de un campo extra: textos seguidos se concatenan, diccionarios se mezclan y en las
    listas de trozos con «index» (los reasoning_details de OpenRouter) cada trozo se junta con el suyo."""
    for k, v in src.items():
        cur = dst.get(k)
        if isinstance(v, dict) and isinstance(cur, dict):
            merge_extra(cur, v)
        elif isinstance(v, list) and isinstance(cur, list):
            for item in v:
                same = None
                if isinstance(item, dict) and "index" in item:
                    same = next((x for x in cur if isinstance(x, dict) and x.get("index") == item["index"]
                                 and x.get("type") == item.get("type")), None)
                if same is None:
                    cur.append(item if not isinstance(item, dict) else dict(item))
                else:
                    for kk, vv in item.items():
                        if kk in ("text", "summary") and isinstance(vv, str) and isinstance(same.get(kk), str):
                            same[kk] += vv
                        else:
                            same[kk] = vv
        elif isinstance(v, str) and isinstance(cur, str) and k not in ("id", "type", "signature", "thought_signature"):
            dst[k] = cur + v
        else:
            dst[k] = json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else v
    return dst


def llm_stream(base_url, api_key, payload, holder, on_delta):
    """Llama a una API compatible con OpenAI (base_url termina en /v1) con streaming.
    holder['conn'] permite cortar la conexion desde otro hilo."""
    u = urllib.parse.urlparse(base_url)
    if any(k.startswith("_") for m in payload.get("messages") or [] for k in m) or \
            any(k.startswith("_") for m in payload.get("messages") or [] for c in m.get("tool_calls") or [] for k in c):
        def clean(m):                                  # lo interno no va al servicio (tampoco dentro de las llamadas)
            m = {k: v for k, v in m.items() if not k.startswith("_")}
            if m.get("tool_calls"):
                m["tool_calls"] = [{k: v for k, v in c.items() if not k.startswith("_")} for c in m["tool_calls"]]
            return m
        payload = dict(payload, messages=[clean(m) for m in payload["messages"]])
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=10, context=tls_context())
    else:
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=10)
    holder["conn"] = conn
    try:
        conn.connect()
        conn.sock.settimeout(None)
        holder["sock"] = conn.sock        # con «Connection: close» http.client suelta conn.sock: se guarda para poder cortar
        conn.request("POST", u.path.rstrip("/") + "/chat/completions", json.dumps(payload).encode("utf-8"),
                     {"Content-Type": "application/json", "Authorization": "Bearer " + (api_key or "local"), "Accept": "text/event-stream"})
        resp = conn.getresponse()
        if resp.status != 200:
            body = resp.read(4000).decode("utf-8", "replace")
            raise LLMError("HTTP %d: %s" % (resp.status, body[:2000]), resp.status, body, resp.getheader("retry-after"))
        content, reasoning, tcs, finish, timings, usage = [], [], {}, None, None, None
        extra = {}                                     # campos propios del servicio en su respuesta (ver merge_extra)
        tags = ThinkTags() if payload.get("model") != "local" else None    # (el motor propio de Jayth ya lo separa)
        heads = {k.lower(): v for k, v in resp.getheaders() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
        holder["rx"], holder["rx_n"], holder["t_gen"] = time.time(), 0, None      # último trozo visible (lo mira el vigilante)
        while True:
            try:
                line = resp.readline()
            except Exception:
                if holder.get("cut"):          # Jayth cortó a propósito una respuesta que no avanzaba: vale lo que llegó
                    finish = "cut"
                    break
                raise
            if not line:
                if holder.get("cut"):
                    finish = "cut"
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
            pp = ch.get("prompt_progress")
            if isinstance(pp, dict) and pp.get("total"):       # llama.cpp: cuánto lleva leído del mensaje
                on_delta("reading", "%d\t%d\t%d\t%d" % (int(pp.get("processed") or 0), int(pp["total"]), int(pp.get("cache") or 0),
                                                        int(pp.get("time_ms") or 0)))
            for c in ch.get("choices") or []:
                d = c.get("delta") or {}
                parts = delta_parts(d)
                if parts or d.get("tool_calls"):
                    holder["rx"], holder["rx_n"] = time.time(), holder.get("rx_n", 0) + 1
                    if holder.get("t_gen") is None:
                        holder["t_gen"] = holder["rx"]
                for kind, text in parts:
                    for kind2, text2 in (tags.feed(text) if (tags is not None and kind == "content") else [(kind, text)]):
                        (reasoning if kind2 == "reasoning" else content).append(text2)
                        on_delta(kind2, text2)
                more = {k: v for k, v in d.items() if k not in _KNOWN_DELTA and v not in (None, "", [], {})}
                if more:
                    merge_extra(extra, more)
                for tc in d.get("tool_calls") or []:
                    slot = tcs.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    xc = {k: v for k, v in tc.items() if k not in _KNOWN_CALL and v not in (None, "", [], {})}
                    if xc:                       # p. ej. Gemini: extra_content.google.thought_signature (la exige de vuelta)
                        merge_extra(slot.setdefault("extra", {}), xc)
                    f = tc.get("function") or {}
                    if f.get("name"):
                        slot["name"] += f["name"]
                    if f.get("arguments"):
                        slot["args"] += f["arguments"]
                    if slot["name"]:                # el modelo está escribiendo una acción: cuál y cuánto lleva
                        on_delta("tool", "%s\t%d" % (slot["name"], len(slot["args"])))
                if c.get("finish_reason"):
                    finish = c["finish_reason"]
        for kind, text in (tags.flush() if tags is not None else []):
            (reasoning if kind == "reasoning" else content).append(text)
            on_delta(kind, text)
        return {"content": "".join(content), "reasoning": "".join(reasoning), "tool_calls": [tcs[k] for k in sorted(tcs)],
                "finish": finish, "timings": timings, "usage": usage, "headers": heads, "extra": extra}
    finally:
        try:
            conn.close()
        except Exception:
            pass
        holder["conn"] = None
        holder["sock"] = None


def ext_stream(base_url, api_key, payload, holder, on_delta):
    """llm_stream para un servicio por API: no le repite lo que ya rechazó y, si rechaza un parámetro opcional o el límite
    de salida (HTTP 400), se adapta y repite la petición en vez de dejar al usuario con el error."""
    def noted(res):
        if isinstance(res, dict) and res.get("finish") != "cut":
            res["spent"] = USAGE.record(base_url, payload.get("model"), res.get("usage"), res.get("headers"), holder.get("_sid", ""))
        return res
    if CL.is_claude(base_url):         # Claude por su API nativa: esfuerzo de verdad, razonamiento visible y caché
        return noted(CL.stream(base_url, api_key, payload, holder, on_delta, LLMError))
    for _ in range(6):
        sent = API.adapt(base_url, API.prepare(base_url, payload))
        try:
            return noted(llm_stream(base_url, api_key, sent, holder, on_delta))
        except LLMError as e:
            if not API.learn(base_url, sent, str(e)):
                raise
    return noted(llm_stream(base_url, api_key, API.adapt(base_url, API.prepare(base_url, payload)), holder, on_delta))


def drop_connection(holder):
    """Corta desde otro hilo la petición en curso (Parar, o una respuesta que no avanza)."""
    c = holder.get("conn")          # se toma antes de cortar: al cortar, el otro hilo sigue y puede abrir la petición siguiente
    socks = []
    for sock in (holder.get("sock"), getattr(c, "sock", None)):
        if sock is not None and not any(sock is s for s in socks):
            socks.append(sock)
    for sock in socks:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        # En Windows, shutdown no despierta una lectura pendiente si el otro extremo sigue enviando (un servicio por API manda
        # «ping» cada pocos segundos): solo cerrar el descriptor lo hace. detach() deja el objeto sin descriptor, para que
        # no lo cierre otra vez más tarde (para entonces ese número podría ser de otra conexión).
        try:
            socket.close(sock.detach())
        except Exception:
            pass
    # Sin c.close() aquí: cerraría el lector de la respuesta, que tiene tomado el hilo que está leyendo, y quien llama (la
    # interfaz, al pulsar «Parar») se quedaría esperando. El hilo que lee cierra la conexión al despertar (llm_stream).


def slot_decoded(port):
    """Tokens que lleva escritos el motor local en la respuesta en curso (0 = aún lee; None = no se sabe)."""
    try:
        c = http.client.HTTPConnection("127.0.0.1", int(port), timeout=3)
        try:
            c.request("GET", "/slots")
            r = c.getresponse()
            if r.status != 200:
                return None
            best = None
            for s in json.loads(r.read()):
                if isinstance(s, dict) and s.get("is_processing"):
                    nt = s.get("next_token") or {}
                    if isinstance(nt, list):
                        nt = nt[0] if nt else {}
                    n = int(nt.get("n_decoded") or 0)
                    best = n if best is None else max(best, n)
            return best
        finally:
            c.close()
    except Exception:
        return None


_SPLIT_CACHE = {}
_GEMMA4 = re.compile(r"gemma[\s_-]*4", re.I)


def text_then_call_apart(cfg):
    """¿Hay que enviar en mensajes separados el texto y la acción de un mismo paso del modelo?

    La plantilla de Gemma 4 escribe primero la acción y su resultado y DESPUÉS el texto que el modelo dijo antes de
    actuar, y con eso da su turno por cerrado. En el paso siguiente el modelo se encuentra «ya terminé» seguido de un
    pensamiento suelto y se desorienta: repite, anuncia sin hacer o se queda generando sin producir nada (un usuario
    esperó 26 minutos así). Separando «texto» y «acción» en dos mensajes seguidos, la misma plantilla los deja en orden y
    con el turno abierto. Se reconoce por su formato de acciones («<|tool_call>call:»); otras plantillas no se tocan."""
    external = cfg.get("llm_mode") == "external"
    name = (cfg.get("external_model") or "") if external else (cfg.get("_model_title") or "")
    guess = bool(_GEMMA4.search(name))
    if external:
        return guess
    key = (int(cfg.get("llm_port") or 0), name)
    if key in _SPLIT_CACHE:
        return _SPLIT_CACHE[key]
    try:
        c = http.client.HTTPConnection("127.0.0.1", key[0], timeout=3)
        try:
            c.request("GET", "/props")
            r = c.getresponse()
            if r.status != 200:
                return guess
            tpl = json.loads(r.read()).get("chat_template") or ""
        finally:
            c.close()
    except Exception:
        return guess
    _SPLIT_CACHE[key] = "<|tool_call>call:" in tpl if tpl else guess
    return _SPLIT_CACHE[key]


def split_text_and_calls(msgs):
    """Cada mensaje del modelo con texto y acciones pasa a ser dos seguidos: el texto y, después, las acciones."""
    out = []
    for m in msgs:
        if m.get("role") == "assistant" and m.get("tool_calls") and isinstance(m.get("content"), str) and m["content"].strip():
            out.append({"role": "assistant", "content": m["content"]})
            m = dict(m, content="")
        out.append(m)
    return out


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
               "max_tokens": 2000 if external else 40,   # fuera no se puede apagar el razonamiento: margen
               "messages": [{"role": "system", "content": "Pones títulos breves a conversaciones. Respondes solo con el título."},
                            {"role": "user", "content": "Escribe un título de 2 a 6 palabras, en el idioma del usuario, sin comillas ni punto final, "
                                                        "que resuma de qué trata esta conversación.\n\nUsuario: %s\n\nAgente: %s"
                                                        % (user[:1500], answer[:1000])}]}
    if external:       # sin temperatura propia: hay servicios que la rechazan; el esfuerzo más bajo de cada servicio
        payload.update(API.effort_params(base, "low", payload["model"]))
    else:              # sin razonamiento: el titulo debe salir en un instante
        kw, extra = local_think("low", cfg.get("_think_style") or "")
        payload.update({"temperature": 0.3, "cache_prompt": False, "chat_template_kwargs": kw}, **extra)
    try:
        return clean_title((ext_stream if external else llm_stream)(base, key, payload, {"_sid": cfg.get("_sid", "")}, lambda k, t: None)["content"])
    except Exception:
        return ""


class Run:
    def __init__(self, session, settings, emit, images_dir):
        self.s = session            # dict con 'messages', 'allowed', 'plan'…
        self.cfg = settings
        self._failed = False        # el turno acabó en un error del modelo o del servicio (se le cuenta en su siguiente turno)

        self._last_err = ""

        def emit_(ev):
            if ev.get("t") == "error":
                self._failed = True
                self._last_err = str(ev.get("text") or "")
            return emit(ev)
        self.emit = emit_
        self.images_dir = images_dir
        self.stop = threading.Event()
        self.pending = {}           # tool_call_id -> {event, decision}
        self.holder = {"_sid": settings.get("_sid", "")}      # (la conversación, para anotar su consumo)
        self.sid = settings.get("_sid", "sin_sesion")
        self.ctx = T.Ctx(settings["workspace"], self.stop, images_dir, int(settings["max_tool_output"]),
                         {"sid": self.sid, "brave_key": settings.get("brave_key"), "search_provider": settings.get("search_provider", "auto"),
                          "searxng_url": settings.get("searxng_url", ""), "command_timeout": int(settings.get("command_timeout", 60))})
        self._buf, self._last = {"kind": None, "text": ""}, 0.0
        self._prep = ("", 0.0)
        self.calls_seen = Counter()
        self.fails_seen = Counter()
        self._effects = 0                 # acciones con efectos ejecutadas (las consultas repetidas entre medias no son bucle)
        self._sig_epoch = {}
        self.truncated = False
        self._deltas = 0                  # trozos de respuesta recibidos (si ya llegó algo, un error no se reintenta: se duplicaría)
        self._cut_ids = set()             # acciones que llegaron cortadas por el límite de salida (no se ejecutan)
        self._cut_nudges = 0
        self._read_ev, self._ptps = 0.0, 0.0           # avance de lectura: último aviso y velocidad medida (tok/s)
        self._cuts = 0                                 # respuestas cortadas por generar sin producir nada visible
        self._split = None                             # ¿texto y acción en mensajes separados? (se averigua una vez)
        # instrucciones fijas durante toda la CONVERSACIÓN (no solo la tarea): lo que cambia solo se fijó en su primer
        # mensaje y los cambios van en el mensaje nuevo; así el motor reutiliza lo ya leído de un mensaje al siguiente
        self._sys_now = volatile_parts(settings)
        if not isinstance(self.s.get("_sys"), dict):
            self.s["_sys"], self.s["_sys_seen"] = dict(self._sys_now), dict(self._sys_now)
        self.system = system_prompt(settings, self.s["_sys"])
        self.groups = list(self.s.get("tool_groups") or [])     # grupos de herramientas ya activos en esta conversación
        self.tools = tool_schemas(settings, self.groups)
        self.sampling = self._sampling()
        self.t0 = time.time()
        self.inbox = []             # mensajes que el usuario escribe mientras trabaja: los ve en su próximo paso
        self.inbox_lock = threading.Lock()

    # ---- mensajes escritos mientras trabaja (para corregirle sin pararlo)
    def queue(self, text):
        with self.inbox_lock:
            item = {"id": uuid.uuid4().hex[:8], "text": text}
            self.inbox.append(item)
        return item["id"]

    def unqueue(self, qid):
        with self.inbox_lock:
            n = len(self.inbox)
            self.inbox = [i for i in self.inbox if i["id"] != qid]
            return len(self.inbox) < n

    def queued(self):
        with self.inbox_lock:
            return list(self.inbox)

    def _deliver(self, msgs):
        """Pasa al modelo lo que el usuario escribió mientras trabajaba. Devuelve True si había algo."""
        with self.inbox_lock:
            items, self.inbox = self.inbox, []
        for it in items:
            msgs.append({"role": "user", "_auto": True, "content": STEER % it["text"]})
            self.emit({"t": "steer", "id": it["id"], "text": it["text"]})
        return bool(items)

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
        drop_connection(self.holder)
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
        if kind in ("content", "reasoning"):
            self._deltas += 1
        if kind == "reading":          # «leídos\ttotal\tde_caché\tms»: el motor va leyendo el mensaje (no se guarda en disco)
            try:
                done, total, cache, ms = (int(x) for x in text.split("\t"))
            except ValueError:
                return
            if ms > 0 and done > cache:
                self._ptps = (done - cache) * 1000.0 / ms
            now = time.time()
            if now - self._read_ev >= 2.0 or done >= total:
                self._read_ev = now
                self.emit({"t": "reading", "done": max(0, done - cache), "total": max(1, total - cache), "tps": round(self._ptps, 2)})
            return
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

    # ---- vigilante: que nunca haya silencio mientras el modelo trabaja
    QUIET_SHOW = (20, 15)        # tokens y segundos escritos sin que llegue nada visible para avisar en el chat
    QUIET_CUT = (250, 90)        # …y para cortar la primera vez (lo normal son huecos de 10-30 tokens)
    QUIET_CUT_AGAIN = (1500, 300)   # la segunda, mucho más margen (por si ese modelo entrega las acciones de golpe)
    WATCH_EVERY = 2.0            # segundos entre miradas al motor
    API_QUIET_SHOW = 20          # servicio por API: segundos sin que llegue nada para decirlo en el chat
    API_QUIET_CUT = 600          # …y para dar la petición por colgada

    def _watch(self, external, done):
        """Hilo que acompaña a cada petición al modelo. El motor local dice cuántos tokens lleva escritos (/slots) aunque
        no entregue texto: si escribe y escribe sin que llegue nada (ni texto, ni pensamiento, ni acción), el chat lo
        muestra y, pasado un límite, Jayth corta y le pide al modelo que continúe. Así no vuelve a pasar que el modelo se
        quede media hora generando en vacío sin que se vea nada (plantilla confundida, bucle de espacios en blanco…)."""
        h = self.holder
        port = int(self.cfg.get("llm_port") or 0)
        mark_n = mark_rx = None
        t_mark = last_ev = 0.0
        limit = None if self.s.get("_quiet_ok") else (self.QUIET_CUT if self._cuts == 0 else self.QUIET_CUT_AGAIN)
        while not done.wait(self.WATCH_EVERY):
            if self.stop.is_set():
                return
            rx, now = h.get("rx"), time.time()
            if rx is None:                       # el servidor aún no ha empezado a contestar
                continue
            n = None if external else slot_decoded(port)
            if n is None:
                # Sin dato del motor. Un servicio por API piensa sin mostrarlo y entrega cada acción de una vez, así que es
                # normal que calle minutos: se dice en el chat y, si pasa de lo que tardaría en escribir la respuesta más
                # larga posible, es que la petición se quedó colgada: se corta y se le pide que siga.
                if (external or h.get("t_gen")) and now - rx >= (self.API_QUIET_SHOW if external else 30) and now - last_ev >= 5:
                    last_ev = now
                    self.emit({"t": "quiet", "tokens": 0, "secs": int(now - rx), "api": bool(external)})
                if external and now - rx >= self.API_QUIET_CUT:
                    h["cut"], h["cut_tokens"] = "quiet", 0
                    drop_connection(h)
                    return
                continue
            if n <= 0:                           # todavía lee el mensaje
                mark_n = None
                continue
            if mark_n is None or mark_rx != h.get("rx_n") or n < mark_n:
                mark_n, mark_rx, t_mark = n, h.get("rx_n"), now      # llegó algo visible (o empezó a escribir): se cuenta desde aquí
                continue
            tok, secs = n - mark_n, now - t_mark
            h["quiet_max"] = max(h.get("quiet_max", 0), tok)
            if tok >= self.QUIET_SHOW[0] and secs >= self.QUIET_SHOW[1] and now - last_ev >= 4:
                last_ev = now
                self.emit({"t": "quiet", "tokens": tok, "secs": int(secs)})
            if limit and tok >= limit[0] and secs >= limit[1]:
                h["cut"], h["cut_tokens"] = "quiet", tok
                drop_connection(h)
                return

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

    def _max_out(self, effort=None):
        """Tokens de salida que se piden en cada respuesta (con esfuerzo alto, el doble: el pensamiento también cuenta)."""
        high = (effort or self.cfg.get("effort")) == "high"
        if self.cfg.get("llm_mode") == "external":
            return API.max_out(self.cfg, high)             # un servicio por API tiene sus propios límites
        return int(self.cfg["max_tokens"]) * (2 if high else 1)

    def _budget(self):
        out = self._max_out() if self.cfg.get("llm_mode") == "external" else int(self.cfg["max_tokens"])
        return int(self.cfg["n_ctx"]) - out - self._fixed_tokens() - 300

    def _to_llm(self, msgs=None):
        msgs = self.s["messages"] if msgs is None else msgs
        # solo si el modelo de verdad ve (tiene proyector de visión): si no, el motor rechaza la petición entera (HTTP 500)
        see = can_see(self.cfg)
        keep = self._images_kept(msgs) if see else set()
        out = []
        for i, m in enumerate(msgs):
            c = m.get("content")
            if isinstance(c, list):
                parts = []
                for j, p in enumerate(c):
                    if p.get("type") != "image_ref":
                        parts.append(p)
                    elif (i, j) in keep and not p.get("_omit") and os.path.isfile(os.path.join(self.images_dir, p["name"])):
                        with open(os.path.join(self.images_dir, p["name"]), "rb") as f:
                            raw = f.read()
                        if not T.image_mime(raw):          # un formato que los modelos no admiten (bmp, tiff…): como PNG
                            raw = T.to_png(raw) or raw
                        b64 = base64.b64encode(raw).decode()
                        mime = T.image_mime(raw, p["name"])                # el tipo, por su contenido y no por su nombre
                        parts.append({"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}})
                    else:
                        parts.append({"type": "text", "text": "[imagen anterior omitida para ahorrar contexto]" if see else
                                      "[imagen: el usuario la ve en el chat; tú no puedes ver imágenes]"})
                m = dict(m, content=parts)
            # claves internas (_auto) no van al modelo; la respuesta tal cual de Claude (_ant) y el razonamiento (_reasoning)
            # sí, para devolvérselos al servicio que los pida (los quita llm_stream para los demás)
            out.append({k: v for k, v in m.items() if not k.startswith("_") or k in ("_ant", "_ant_model", "_reasoning", "_x", "_xbase", "_xmodel")})
        if self._split is None:
            self._split = text_then_call_apart(self.cfg)
        return split_text_and_calls(out) if self._split else out

    IMAGE_BATCH = 3     # con un modelo por API, imágenes antiguas de más que se toleran antes de omitirlas de golpe

    def _images_kept(self, msgs):
        """Qué imágenes ve el modelo. Siempre las del último mensaje que trae imágenes y las de después de su última
        respuesta (las del paso en curso: antes, de 3 en un mismo paso solo llegaba la última). De las anteriores, las
        `keep_images` más recientes. Con un modelo por API, las sobrantes se omiten por tandas y la decisión se guarda
        en el mensaje (_omit): omitir una imagen cambia lo ya enviado y anula la caché desde ahí, mejor de vez en cuando."""
        refs = [(i, j) for i, m in enumerate(msgs) if isinstance(m.get("content"), list)
                for j, p in enumerate(m["content"]) if p.get("type") == "image_ref" and not p.get("_omit")]
        if not refs:
            return set()
        last_asst = max((i for i, m in enumerate(msgs) if m.get("role") == "assistant"), default=-1)
        newest = refs[-1][0]
        protected = {r for r in refs if r[0] > last_asst or r[0] == newest}
        older = [r for r in refs if r not in protected]
        n = max(0, int(self.cfg.get("keep_images") or 0))
        slack = self.IMAGE_BATCH if self.cfg.get("llm_mode") == "external" else 0
        if len(older) > n + slack:
            for i, j in older[:len(older) - n]:
                msgs[i]["content"][j] = dict(msgs[i]["content"][j], _omit=True)
            older = older[len(older) - n:]
        return protected | set(older if n else [])

    # ---- memoria de la conversación (contexto): recortar y resumir antes de llegar al tope
    TRIM_AT = 0.70      # a partir de aquí se recortan las salidas antiguas de las herramientas (sin llamar al modelo)
    TRIM_TO = 0.45      # …de una vez, hasta aquí: así no se vuelve a recortar en cada paso (cada recorte anula la caché)
    SUMMARY_AT = 0.85   # y si aun así no baja, el modelo resume lo antiguo
    KEEP_STEPS = 3      # los resultados de los últimos pasos no se recortan nunca

    def ctx_used(self, msgs=None):
        """Tokens que ocupa la conversación (estimados) y el máximo del modelo."""
        msgs = self.s["messages"] if msgs is None else msgs
        return int(self._fixed_tokens() + self._estimate(msgs)), int(self.cfg["n_ctx"])

    def _emit_ctx(self):
        used, mx = self.ctx_used()
        self.emit({"t": "ctx", "used": used, "max": mx})

    def _trim_old_results(self, msgs, budget=None, keep=None):
        """Sin llamar al modelo: las salidas largas de herramientas antiguas se quedan en su principio, con una nota que
        dice dónde está entera (se guarda en un archivo). Es lo que más ocupa (archivos, páginas web) y casi nunca vuelve
        a hacer falta entera. Se recorta de una vez, de lo más antiguo a lo más nuevo, hasta bajar a TRIM_TO del
        presupuesto: cada recorte cambia lo ya enviado y anula la caché desde ese punto, así que mejor pocas veces.
        Nunca se tocan los resultados de los últimos KEEP_STEPS pasos ni los que el modelo aún no ha visto."""
        keep = self.KEEP_STEPS if keep is None else keep
        if budget and self._estimate(msgs) <= self.TRIM_TO * budget:
            return 0                                    # ya está por debajo: recortar ahora solo anularía la caché
        asst = [i for i, m in enumerate(msgs) if m.get("role") == "assistant"]
        limit = asst[-keep] if keep and len(asst) >= keep else (asst[0] if keep and asst else len(msgs))
        idx = [i for i, m in enumerate(msgs) if m["role"] == "tool" and i < limit]
        cut = 0
        for i in idx:
            c = msgs[i].get("content")
            if not isinstance(c, str) or len(c) <= 700 or msgs[i].get("_trimmed"):
                continue
            where = T.spill(c, "recorte")
            note = ("\n[… salida antigua recortada para ahorrar memoria (%d caracteres en total). %s]" % (
                len(c), ("Está entera en %s: léela con read_file (con offset) si la necesitas." % where) if where else
                "Si la necesitas entera, vuelve a pedirla."))
            msgs[i] = dict(msgs[i], content=c[:400] + note, _trimmed=True)
            cut += len(c) - 400
            if budget and self._estimate(msgs) <= self.TRIM_TO * budget:
                break
        return cut

    @staticmethod
    def _line(m, limit=2500):
        c = m.get("content")
        text = c if isinstance(c, str) else " ".join(p.get("text", "") for p in (c or []) if p.get("type") == "text")
        if m.get("tool_calls"):
            text += " [acciones: %s]" % ", ".join(tc["function"]["name"] for tc in m["tool_calls"])
        if m["role"] == "tool":
            limit = 400
        if text.startswith("[Resumen"):
            limit = 20000                               # un resumen anterior va entero: es lo único que queda de aquello
        return "%s: %s" % ({"user": "Usuario", "assistant": "Agente", "tool": "Resultado"}.get(m["role"], m["role"]), text[:limit])

    def _summarize(self, base, key, part, what):
        """Pide al modelo un resumen de esos mensajes, del tamaño adecuado a su memoria. Devuelve el texto o ''."""
        n = int(self.cfg["n_ctx"])
        out_tok = int(min(2000, max(350, n * 0.05)))     # 8k → ~400 tokens · 32k → ~1600 · 128k o más → 2000
        words = int(out_tok * 0.6)
        room = max(1500, n - out_tok * 2 - 900)          # lo que cabe del texto a resumir en la propia petición
        transcript = "\n".join(self._line(m) for m in part)
        transcript = transcript[-int(room * 3.0 / float(self.s.get("_ratio", 1.0))):]
        ask = ("Resume %s para poder continuarla sin perder nada importante. Incluye: objetivo, decisiones, datos y cifras "
               "obtenidos, archivos creados o modificados (con rutas), comandos importantes, lo que falta por hacer y las "
               "preferencias del usuario. Máximo %d palabras, en el idioma de la conversación.\n\n%s") % (what, words, transcript)
        other = self.cfg.get("_slot_other")
        if callable(other):                          # el motor va a leer otra cosa: lo suyo deja de ser la conversación
            other()
        payload = {"model": "local", "stream": True, "max_tokens": out_tok * 2, "temperature": 0.2, "cache_prompt": False,
                   "messages": [{"role": "system", "content": "Resumes conversaciones de trabajo de forma fiel y compacta."},
                                {"role": "user", "content": ask}]}
        external = self.cfg.get("llm_mode") == "external"
        if external:
            payload["model"] = self.cfg.get("external_model") or "local"
            payload.pop("cache_prompt")
            payload.pop("temperature")                    # hay servicios que la rechazan
            payload.update({"max_tokens": out_tok * 2 + 2000}, **API.effort_params(base, "low", payload["model"]))   # margen por si razona
        else:                                             # sin razonar: el resumen sale antes (en CPU cada token cuenta)
            kw, extra = local_think("low", self.cfg.get("_think_style") or "")
            payload.update({"chat_template_kwargs": kw}, **extra)
        try:
            return ((ext_stream if external else llm_stream)(base, key, payload, self.holder, lambda k, t: None)["content"] or "").strip()
        except Exception:
            return ""

    def _maybe_compact(self, base, key, force=False):
        """Antes de cada paso: si la conversación se acerca al tope de memoria del modelo, primero se recortan las salidas
        antiguas de las herramientas y, si no basta, el modelo resume lo antiguo (en vez de olvidarlo). force: el usuario
        pidió «Resumir ahora». Devuelve True si cambió algo."""
        msgs = self.s["messages"]
        budget = self._budget()
        if not force and self._estimate(msgs) <= self.TRIM_AT * budget:
            return False
        changed = False
        if not force:
            cut = self._trim_old_results(msgs, budget)
            if self._estimate(msgs) > self.SUMMARY_AT * budget:
                # no basta respetando los últimos pasos: también ellos, salvo lo que el modelo aún no ha visto. Queda
                # guardado (como el resto del recorte): si no, _fit recortaría una copia distinta en cada petición y la
                # caché se perdería en cada paso de un turno largo (en un turno con un solo mensaje no hay nada que resumir)
                cut += self._trim_old_results(msgs, budget, keep=1)
            if cut:
                changed = True
                self.emit({"t": "trimmed", "chars": cut})
                if self._estimate(msgs) <= self.SUMMARY_AT * budget:
                    self._emit_ctx()
                    return True
        last_user = max((i for i, m in enumerate(msgs) if m["role"] == "user" and not m.get("_auto")), default=0)
        old = msgs[:last_user]
        trivial = len(old) < 4 and not (force and len(old) >= 2 and not str(old[0].get("content", "")).startswith("[Resumen"))
        if not trivial:
            # 1) lo anterior a tu último mensaje: un resumen al principio
            self.emit({"t": "info", "text": tr("Resumiendo la parte antigua de la conversación para liberar memoria del modelo…") if force else
                       tr("La conversación ocupa casi toda la memoria del modelo: estoy resumiendo la parte antigua para no perderla…")})
            summary = self._summarize(base, key, old, "esta conversación entre un usuario y su agente")
            if not summary:
                self._emit_ctx()
                return changed
            self.s["messages"] = [{"role": "user", "_auto": True, "content": "[Resumen de la conversación anterior]\n" + summary},
                                  {"role": "assistant", "content": "Entendido. Continúo con ese contexto."}] + msgs[last_user:]
            self.s.pop("_sys", None)                 # el motor releerá todo de todas formas: las instrucciones se
            self.s.pop("_sys_seen", None)            # ponen al día en el próximo mensaje
        else:
            # 2) una sola tarea muy larga: se resumen sus primeros pasos y se conservan los últimos tal cual
            starts = [i for i in range(last_user + 1, len(msgs)) if msgs[i]["role"] == "assistant"]
            if len(starts) < 3:
                if force:
                    self.emit({"t": "info", "text": tr("Aún no hay suficiente conversación para resumir.")})
                self._emit_ctx()
                return changed
            keep_from = starts[-1]
            for i in reversed(starts[1:]):                   # los pasos recientes que quepan en ~35 % de la memoria
                if self._estimate(msgs[i:]) > 0.35 * budget:
                    break
                keep_from = i
            keep_from = min(keep_from, starts[-2])          # al menos los dos últimos pasos enteros
            part = msgs[last_user + 1:keep_from]
            if len(part) < 2:
                self._emit_ctx()
                return changed
            self.emit({"t": "info", "text": tr("Esta tarea ocupa casi toda la memoria del modelo: estoy resumiendo sus primeros pasos "
                                                "para no perderlos…")})
            summary = self._summarize(base, key, part, "lo que el agente ya hizo en la tarea actual del usuario")
            if not summary:
                self._emit_ctx()
                return changed
            first = dict(msgs[keep_from])                   # el resumen va al principio de ese mensaje del agente:
            first["content"] = "[Resumen de lo que ya hice en esta tarea]\n%s\n\n%s" % (summary, first.get("content") or "")
            self.s["messages"] = msgs[:last_user + 1] + [first] + msgs[keep_from + 1:]   # (los turnos siguen alternando)
        self.emit({"t": "compacted", "text": summary})
        self._emit_ctx()
        return True

    def compact_now(self):
        """«Resumir ahora» (fuera de una tarea): resume lo antiguo con el modelo aunque no haga falta todavía."""
        external = self.cfg.get("llm_mode") == "external"
        base = self.cfg["external_url"].rstrip("/") if external else "http://127.0.0.1:%d/v1" % int(self.cfg["llm_port"])
        key = self.cfg.get("external_key") if external else ""
        try:
            self._maybe_compact(base, key, force=True)
        except Exception as e:
            self.emit({"t": "error", "text": tr("No pude resumir la conversación: %s") % e})
        finally:
            self.emit({"t": "compact_end"})

    def _fit(self, msgs):
        budget = self._budget()
        if self._estimate(msgs) <= budget:
            return msgs
        msgs = [dict(m) for m in msgs]
        for m in msgs:                                    # 1) recortar salidas antiguas de herramientas
            if m["role"] == "tool" and len(m.get("content") or "") > 400:
                note = re.search(r"\n\[… salida antigua recortada[^\n]*\]$", m["content"])     # la nota con la ruta, siempre
                m["content"] = m["content"][:300] + "\n...[recortado para ahorrar contexto]" + (note.group(0) if note else "")
                if self._estimate(msgs) <= budget:
                    return msgs
        while self._estimate(msgs) > budget:              # 2) ultimo recurso: descartar lo mas antiguo, hasta el siguiente
            nxt = next((i for i in range(1, len(msgs)) if msgs[i]["role"] == "user"), None)    # mensaje del usuario
            if nxt is None:
                break       # nunca el mensaje en curso ni lo que va detrás: antes se iba todo y el modelo solo recibía sus
            del msgs[:nxt]  # instrucciones (sin nada que responder); así, como mucho, el servicio dice que no cabe
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
        if self._account_of(name):
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
        if name == "replace_in_files":               # los archivos que va a tocar (para poder deshacerlo): los mismos que cambiará
            try:
                return [] if args.get("preview") else [p[0] for p in T.replace_plan(args, self.ctx)[0]][:300]
            except Exception:
                return []
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
        had = [g for g in dict.fromkeys(ok_g) if g in self.groups]
        new = self._activate(ok_g)
        txt = ("Activadas: %s. Ya puedes usar sus herramientas." % ", ".join(new)) if new else "Esos grupos ya estaban activos."
        if new and had:                                 # que no parezca que los demás se ignoraron
            txt += " (Ya estaban activos: %s.)" % ", ".join(had)
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
        # nombres de parámetros de otras herramientas (old_string, file_path…) se aceptan; lo que falta se dice claro
        # (solo las herramientas propias: las de conectores tienen esquemas ajenos y más laxos)
        args, missing_args, extra_args = T.normalize_args(tool, args) if name in T.TOOLS else (args if isinstance(args, dict) else {}, [], [])
        args = coerce(args, tool["parameters"])
        # firma con todos los argumentos (antes, cortados a 2000 letras: dos write_file distintos con el mismo principio
        # contaban como el mismo). Una consulta sin efectos (mirar la pantalla, listar ventanas…) solo cuenta como
        # repetida si entre medias no se hizo nada: después de un clic, volver a mirar es lo correcto.
        sig = name + hashlib.sha1(json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        query = name in QUERY_TOOLS or tool["category"] == "read"
        if query and self._sig_epoch.get(sig) != self._effects:
            self.calls_seen[sig] = self.fails_seen[sig] = 0
        self._sig_epoch[sig] = self._effects
        if self.fails_seen[sig] >= 2 or self.calls_seen[sig] >= 3:   # la 4.ª vez (o la 3.ª tras dos fallos); las bloqueadas no suman
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": "auto"})
            return False, ("Ya intentaste exactamente esta misma acción varias veces. No la repitas: cambia de enfoque, revisa la causa del fallo "
                           "o pregunta al usuario con ask_user."), None, {}
        self.calls_seen[sig] += 1
        if missing_args:
            self.fails_seen[sig] += 1
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": "auto"})
            return False, ("Faltan parámetros obligatorios de %s: %s.%s Sus parámetros son: %s. Vuelve a llamarla con esos nombres exactos."
                           % (name, ", ".join(missing_args), (" Recibí estos, que no existen en ella: %s." % ", ".join(extra_args)) if extra_args else "",
                              T.describe_params(tool))), None, {}
        note = ("\n[Nota de Jayth: %s no tiene %s (%s): se ignoró. Sus parámetros son: %s.]"
                % (name, "el parámetro" if len(extra_args) == 1 else "los parámetros", ", ".join(extra_args), T.describe_params(tool))) if extra_args else ""
        for k in extra_args:
            args.pop(k, None)
        # --- herramientas del propio agente
        if name == "ask_user":
            q = str(args.get("question", ""))
            if legible(q) is False:     # el modelo se desbocó («?………..? ….»): no se le enseña eso al usuario
                return False, ("Error: la pregunta no se entiende («%s»). Si de verdad necesitas preguntar algo, escríbela de "
                               "nuevo con palabras; si no, sigue con la tarea." % q[:60]), None, {}
            opts = [str(o) for o in (args.get("options") or [])][:6]
            self.emit({"t": "question", "id": cid, "question": str(args.get("question", "")), "options": opts})
            d = self._wait(cid)
            if not d or not d.startswith("answer:"):
                self.emit({"t": "answer", "id": cid, "text": ""})
                return False, "El usuario no respondió (detuvo la tarea).", None, {}
            ans = d[7:]
            self.emit({"t": "answer", "id": cid, "text": ans})
            return True, "Respuesta del usuario: " + ans, None, {}
        if name == "delegate":                          # el permiso que se pide es el de lo que podrá hacer el ayudante
            tool = dict(tool, category=SUB_MODES[sub_mode(args.get("mode"))][0])
        approval = self._needs_approval(tool, name, args)
        if approval == "pending" and self.cfg.get("_sub"):     # un ayudante no puede pedir permisos al usuario
            self.emit({"t": "tool_call", "id": cid, "name": name, "args": args, "category": tool["category"], "approval": "blocked"})
            return False, ("Esta acción necesita el permiso del usuario y un ayudante no puede pedirlo. No la intentes de otra forma: "
                           "di en tu informe que hace falta, para que la haga el agente principal."), None, {}
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
                said = d[5:].strip() if d and d.startswith("deny:") else ""
                if said:                                 # «no, y haz esto otro»: lo que dijo manda sobre lo que iba a hacer
                    return False, ("El usuario no permitió esta acción y te dice qué hacer en su lugar: «%s». Hazle caso y "
                                   "sigue la tarea así." % said), None, {}
                return False, "El usuario denegó esta acción.", None, {}
        if name == "delegate":                          # un ayudante hace la subtarea y devuelve su informe
            return self._delegate(args)
        roots = self.cfg.get("_sub_paths")
        if roots and tool["category"] == "write" and name != "undo_changes":     # un ayudante solo cambia lo que se le encargó
            norm = lambda p: os.path.normcase(os.path.abspath(p))
            out = [f for f in self._files_of(name, args) if not any((norm(f) + os.sep).startswith(norm(r) + os.sep) or norm(f) == norm(r) for r in roots)]
            if out:
                return False, ("Fuera de tu encargo: solo puedes cambiar archivos dentro de %s, y esto tocaría %s. No lo intentes de otra "
                               "forma: dilo en tu informe para que lo decida el agente principal." % (", ".join(roots), ", ".join(out[:4]))), None, {}
        extra = {}
        if name in T.WRITE_TOOLS:
            try:
                H.snapshot(self.sid, cid, self._files_of(name, args))
                extra["undo"] = True
            except Exception:
                pass
        if tool["category"] == "control":
            T.CONTROL_RUN = self                     # el botón «Parar» del aviso en pantalla detiene esta tarea
        if not query:
            self._effects += 1
        try:
            self.ctx.call_id = cid                   # las herramientas largas publican su avance con este id
            r = self._undo_changes(args) if name == "undo_changes" else tool["fn"](args, self.ctx)
            if extra.get("undo"):                    # para que el propio modelo pueda deshacerla (undo_changes)
                self.s.setdefault("_undo", []).append({"cid": cid, "name": name})
                del self.s["_undo"][:-200]
            if name == "update_plan":
                self.s["plan"] = [{"content": str(i.get("content", "")), "status": str(i.get("status", "pending"))} for i in args.get("items") or []]
                self.emit({"t": "plan", "items": self.s["plan"]})
            if isinstance(r, dict):
                if r.get("ui"):                          # datos para la interfaz (lienzo, archivos creados…)
                    extra.update(r["ui"])
                imgs = list(r.get("images") or ([r["image"]] if r.get("image") else []))
                return True, T.clip(r["text"], self.ctx.max_out) + note, (imgs or None), extra
            return True, T.clip(str(r), self.ctx.max_out) + note, None, extra
        except T.Abort:
            raise
        except T.ToolError as e:
            self.fails_seen[sig] += 1
            return False, str(e) + note, None, dict(getattr(e, "ui", None) or {})
        except KeyError as e:                        # la herramienta pidió un dato que no vino: se dice cuál y cómo llamarla
            self.fails_seen[sig] += 1
            return False, "Falta el parámetro %s de %s. Sus parámetros son: %s.%s" % (e, name, T.describe_params(tool), note), None, {}
        except Exception as e:
            self.fails_seen[sig] += 1
            return False, "%s: %s%s" % (type(e).__name__, e, note), None, {}

    def _undo_changes(self, args):
        """Deshace las últimas acciones del agente que cambiaron archivos (las que aún tienen su copia de antes: el usuario
        puede haber deshecho alguna desde el chat). Cada una avisa a la interfaz como si la hubiera deshecho el usuario."""
        try:
            want = max(1, min(50, int(args.get("count") or 1)))
        except (TypeError, ValueError):
            want = 1
        stack = self.s.setdefault("_undo", [])
        done = []
        while stack and len(done) < want:
            it = stack.pop()
            if not H.has_snapshot(self.sid, it["cid"]):
                continue                             # ya se deshizo (o su copia ya no existe)
            files = H.undo(self.sid, it["cid"])
            if files:
                self.emit({"t": "undo", "ids": [it["cid"]], "files": files, "by": "agent"})
                done.append("%s: %s" % (it["name"], ", ".join(os.path.relpath(f, self.ctx.workspace) if os.path.abspath(f).lower().startswith(
                    os.path.abspath(self.ctx.workspace).lower() + os.sep) else f for f in files[:8]) + (" …" if len(files) > 8 else "")))
        if not done:
            raise T.ToolError("No queda ningún cambio tuyo de archivos que se pueda deshacer en esta conversación.")
        left = sum(1 for it in stack if H.has_snapshot(self.sid, it["cid"]))
        return "Deshecho (%d):\n%s\nLos archivos están como antes de esas acciones.%s" % (
            len(done), "\n".join("- " + d for d in done), (" Quedan %d acciones anteriores que también se pueden deshacer." % left) if left else "")

    @staticmethod
    def _tree_state(root, limit=20000, seconds=3.0):
        """{ruta: (fecha, tamaño)} de los archivos bajo root (sin .git, node_modules…), o None si es demasiado grande para
        mirarlo en un momento. Sirve para ver qué cambiaron los comandos de un ayudante."""
        out, t_end = {}, time.time() + seconds
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in T._SKIP_DIRS and not d.startswith(".")]
            for f in files:
                p = os.path.join(r, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out[os.path.normcase(os.path.abspath(p))] = (st.st_mtime_ns, st.st_size)
            if len(out) > limit or time.time() > t_end:
                return None
        return out

    def _delegate(self, args):
        """Ejecuta una subtarea con un ayudante: un Run aparte, con la conversación en blanco y solo herramientas de lectura.
        Devuelve (ok, informe, None, extra) como cualquier herramienta."""
        task = str(args.get("task") or "").strip()
        if len(task) < 20:
            return False, ("Describe la subtarea con todo su contexto en 'task': el ayudante no ve esta conversación. Di qué debe "
                           "averiguar, dónde buscar y qué debe devolverte."), None, {}
        other = self.cfg.get("_slot_other")
        if callable(other):                          # motor local: lo que tenía leído de esta conversación se guarda y se recupera después
            try:
                other()
            except Exception:
                pass
        mode = sub_mode(args.get("mode"))
        roots = None
        if mode != "read":                           # dónde puede cambiar archivos: lo que diga el agente principal o, si no, el proyecto
            want = args.get("paths") or []
            want = [want] if isinstance(want, str) else list(want)
            roots = [self.ctx.path(str(p)) for p in want if str(p).strip()] or [os.path.abspath(self.ctx.workspace)]
        cfg = dict(self.cfg)
        brief = SUB_BRIEF % (SUB_MODES[mode][2] % ", ".join(roots) if roots else SUB_MODES[mode][2])
        cfg.update({"_sub": mode, "_sub_paths": roots, "_temp": True, "_before_llm": None, "_after_llm": None,
                    "max_steps": min(int(cfg.get("max_steps") or 30), 40 if mode == "read" else 60),
                    "custom_instructions": ((cfg.get("custom_instructions") or "") + brief).strip()})
        # el encargo ya pasó por los permisos del usuario: dentro de él, el ayudante no vuelve a preguntar (lo peligroso se le niega)
        data = {"messages": [], "allowed": {"read": [], "edit": ["write"], "full": ["write", "exec"]}[mode],
                "tool_groups": [g for g in self.groups if g in ("web", "navegador", "documentos", "conocimiento", "procesos")]}
        log = []
        title = str(args.get("title") or "").strip()[:60]

        def emit(ev):                                # lo que hace el ayudante se ve en el chat (y se puede deshacer) como lo del principal
            log.append(ev)
            if ev.get("t") in ("tool_call", "tool_result", "undo") and ev.get("name") != "use_tools":
                self.emit(dict(ev, sub=title or True))
        ws = os.path.abspath(self.ctx.workspace)
        before = self._tree_state(ws) if mode == "full" else None     # sus comandos pueden cambiar lo que sea
        sub = Run(data, cfg, emit, self.images_dir)
        sub.stop = self.stop                         # «Parar» detiene también al ayudante…
        sub.ctx.stop = self.stop
        sub.holder = self.holder                     # …y corta su petición en curso
        t0 = time.time()
        try:
            sub.run(task)
        except Exception as e:
            return False, "El ayudante falló: %s: %s" % (type(e).__name__, e), None, {}
        done = [it for it in data.get("_undo") or [] if H.has_snapshot(self.sid, it["cid"])]
        self.s.setdefault("_undo", []).extend(done)  # el agente principal puede deshacer lo que hizo su ayudante (undo_changes)
        if self.stop.is_set():
            return False, "Cancelado por el usuario.", None, {}
        report = next((_plain(m.get("content")).strip() for m in reversed(data["messages"])
                       if m["role"] == "assistant" and _plain(m.get("content")).strip()), "")
        used = Counter(e.get("name") for e in log if e.get("t") == "tool_call")
        errs = [str(e.get("text"))[:300] for e in log if e.get("t") == "error"]
        denied = sum(1 for e in log if e.get("t") == "tool_call" and e.get("approval") == "blocked")
        tail = "\n\n[Ayudante: %d acciones (%s) en %d s%s%s]" % (
            sum(used.values()), ", ".join("%s ×%d" % (k, v) for k, v in used.most_common(6)) or "ninguna", time.time() - t0,
            ("; %d acciones se le negaron por necesitar permiso del usuario" % denied) if denied else "",
            ("; terminó con un error: " + errs[-1]) if errs else "")
        short = lambda p: os.path.relpath(p, ws) if os.path.abspath(p).lower().startswith(ws.lower() + os.sep) else p
        tracked = {}                                 # ruta normalizada -> (cómo mostrarla, si era nuevo)
        if done:                                     # lo que cambió, para que el agente principal lo revise: responde de ello
            for it in done:
                for e in H.snapshot_files(self.sid, it["cid"]):
                    key = os.path.normcase(os.path.abspath(e["path"]))
                    if key not in tracked:           # crear y luego editar el mismo archivo es UN archivo (nuevo)
                        tracked[key] = (short(e["path"]), not e.get("existed", True))
            files = [rel + (" (nuevo)" if new else "") for rel, new in tracked.values()]
            tail += ("\n[El ayudante cambió %d %s en %d acciones: %s%s. Eres responsable de esos cambios: revísalos (read_file) antes "
                     "de darlos por buenos; undo_changes(count=%d) los deshace todos.]"
                     % (len(files), "archivo" if len(files) == 1 else "archivos", len(done), ", ".join(files[:20]),
                        " …" if len(files) > 20 else "", len(done)))
        if before is not None:                       # lo que cambiaron sus comandos: no se puede deshacer
            after = self._tree_state(ws)
            if after is not None:
                changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p) and p not in tracked)
                if changed:
                    norm_roots = [os.path.normcase(os.path.abspath(r)) for r in roots or []]
                    outside = [p for p in changed if not any(p == r or p.startswith(r + os.sep) for r in norm_roots)]
                    names = [short(p) + ("" if p in after else " (borrado)") for p in changed]
                    one = len(changed) == 1
                    where = ""
                    if outside and roots:
                        where = (" Está fuera de las carpetas que le encargaste." if one else
                                 " %d de ellos están fuera de las carpetas que le encargaste." % len(outside))
                    tail += ("\n[Con comandos, el ayudante cambió además %s que undo_changes NO puede deshacer: %s%s.%s]"
                             % ("1 archivo" if one else "%d archivos" % len(changed), ", ".join(names[:20]),
                                " …" if len(names) > 20 else "", where))
        if not report:
            return False, "El ayudante no devolvió ningún informe." + tail, None, {}
        return True, T.clip(report, max(self.ctx.max_out, 12000)) + tail, None, {}

    def _spend_check(self):
        """Modelos por API: si esta conversación o el día superan el gasto que el usuario puso como aviso, se le dice (una
        vez por límite) y, si lo pidió, la tarea espera a que diga si sigue."""
        lim_c = float(self.cfg.get("spend_alert_conv") or 0)
        lim_d = float(self.cfg.get("spend_alert_day") or 0)
        if (lim_c <= 0 and lim_d <= 0) or self.cfg.get("_sub"):
            return
        usd = lambda x: "%s US$" % i18n.number(x, 2)
        msgs = []
        try:
            if lim_c > 0:
                conv = USAGE.session_total(self.sid).get("usd") or 0.0
                if conv >= lim_c and self.s.get("_spend_warned") != lim_c:
                    self.s["_spend_warned"] = lim_c
                    msgs.append(tr("Esta conversación ya lleva ≈ %s con el modelo por API (tu aviso: %s).") % (usd(conv), usd(lim_c)))
            if lim_d > 0:
                day = USAGE.summary()["hoy"]["usd"]
                key = time.strftime("%Y-%m-%d")
                if day >= lim_d and _DAY_WARNED.get(key) != lim_d:
                    _DAY_WARNED[key] = lim_d
                    msgs.append(tr("Hoy llevas ≈ %s con modelos por API (tu aviso: %s).") % (usd(day), usd(lim_d)))
        except Exception:
            return
        if not msgs:
            return
        text = " ".join(msgs)
        self.emit({"t": "spend_alert", "text": text})
        if not self.cfg.get("spend_alert_pause"):
            return
        cid = "gasto_" + uuid.uuid4().hex[:8]
        go, halt = tr("Sí, sigue"), tr("Para aquí")
        self.emit({"t": "question", "id": cid, "question": text + " " + tr("¿Sigo con la tarea?"), "options": [go, halt]})
        d = self._wait(cid)
        ans = d[7:] if d and d.startswith("answer:") else ""
        self.emit({"t": "answer", "id": cid, "text": ans})
        if not d or ans.strip() == halt:
            self.stop.set()

    def _call_llm(self, external, base, key, payload):
        """Pide la respuesta al modelo. Con un servicio por API, un error pasajero (saturado, demasiadas peticiones por
        minuto, fallo del servidor, se cortó antes de empezar a responder) se reintenta solo, esperando cada vez más (o lo
        que pida el servicio) y diciéndolo en el chat; antes la tarea se paraba con el error tal cual. Si ya había llegado
        parte de la respuesta no se reintenta (se duplicaría): queda el error y «Reintentar»."""
        fn = ext_stream if external else llm_stream
        tries = 0
        while True:
            n0 = self._deltas
            try:
                return fn(base, key, payload, self.holder, self._delta)
            except LLMError as e:
                err, again = e, external and ERR.transient(e.status, e.body)
            except (socket.timeout, TimeoutError, ConnectionResetError, ConnectionAbortedError) as e:
                if not external:
                    raise
                err, again = e, True
            if not again or tries >= len(RETRY_WAITS) or self.stop.is_set() or self._deltas != n0 or self.holder.get("cut"):
                if isinstance(err, LLMError):
                    err.tries = tries
                raise err
            wait = float(RETRY_WAITS[tries])
            if getattr(err, "retry_after", None):
                wait = min(120.0, max(wait, err.retry_after))
            tries += 1
            k = ERR.kind(err.status, err.body) if isinstance(err, LLMError) else "timeout"
            what = {"busy": tr("El servicio está saturado"), "rate": tr("El servicio pide esperar (límite por minuto)"),
                    "server": tr("El servicio tuvo un fallo pasajero"), "timeout": tr("El servicio no responde")}.get(k, tr("El servicio falló"))
            self.emit({"t": "info", "text": tr("%s. Reintento en %d s (intento %d de %d)…") % (what, int(wait), tries + 1, len(RETRY_WAITS) + 1)})
            end = time.time() + wait
            while time.time() < end and not self.stop.is_set():
                time.sleep(0.2)
            if self.stop.is_set():
                raise err

    def _repair(self):
        """Si se corto a mitad, toda llamada a herramienta debe tener su respuesta para que el historial sea valido."""
        repair_history(self.s["messages"])

    # ---- bucle principal
    def run(self, text, image_names=(), attachments="", marker=None):
        msgs = self.s["messages"]
        self._repair()                                  # antes del mensaje nuevo: si Jayth se cerró a mitad, aquí falta algo
        body = text + (("\n\n" + attachments) if attachments else "")
        if on_demand(self.cfg):                         # grupos que seguramente hagan falta: activos desde el primer paso
            files = [l[4:].strip() for l in attachments.splitlines() if l.startswith("### ")]
            valid = {g for g, d in available_groups(self.cfg)}
            new = self._activate([g for g in detect_groups(text, self.cfg, files, image_names) if g in valid])
            guides = [group_guide(g) for g in new if group_guide(g)]
            if new:                                     # sus pautas van con el mensaje (no cambian las instrucciones fijas)
                body += "\n\n[Herramientas activadas para esta tarea: %s]%s" % (", ".join(new), ("\n" + "\n".join(guides)) if guides else "")
        note = changes_note(self._sys_now, self.s.get("_sys_seen"))
        if note:                                        # la fecha, los archivos del proyecto o la memoria cambiaron
            body += note
            self.s["_sys_seen"] = dict(self._sys_now)
        if (self.cfg.get("response_language") or "auto") == "auto":
            lang = guess_language(text)
            if lang and lang != "es":                   # en español ya están las instrucciones
                body += "\n\n[Responde en %s, el idioma de este mensaje.]" % LANG_ES[lang]
        no_net = T.offline(max_age=30)                  # ¿hay internet? (una comprobación corta; el modelo no puede saberlo solo)
        if no_net:
            body += "\n\n[Aviso de Jayth: " + T.OFFLINE_MSG + "]"
        # cómo acabó su turno anterior, si no acabó bien: el modelo no lo ve en la conversación y no puede saberlo solo
        how = "closed" if self.s.pop("_turn_open", None) else self.s.pop("_cut_short", None)
        self.s.pop("_cut_short", None)
        err = self.s.pop("_cut_err", "")
        if how in CUT_SHORT and msgs:
            body += "\n\n[Aviso de Jayth: " + CUT_SHORT[how] + ((" El error fue: «%s»." % err) if how == "error" and err else "") + "]"
        self.s["_turn_open"] = True
        self._failed = False
        content = body if not image_names else [{"type": "text", "text": body}] + [{"type": "image_ref", "name": n} for n in image_names]
        # _attach: los adjuntos tal cual, para reintentar o editar sin arrastrar los avisos que Jayth añadió al mensaje
        msgs.append({"role": "user", "content": content, "_attach": attachments or ""})
        uev = {"t": "user", "text": text, "images": list(image_names), "files": [l[4:].strip() for l in attachments.splitlines() if l.startswith("### ")]}
        if marker:                                      # p. ej. «plan»: el chat lo muestra como marca, no como mensaje tuyo
            uev["marker"] = marker
        self.emit(uev)
        if no_net:
            self.emit({"t": "info", "text": tr("Sin conexión a internet: el modelo lo sabe y trabajará con lo que hay en este equipo.")})
        external = self.cfg.get("llm_mode") == "external"
        base = self.cfg["external_url"].rstrip("/") if external else "http://127.0.0.1:%d/v1" % int(self.cfg["llm_port"])
        key = self.cfg.get("external_key") if external else ""
        e = self.cfg.get("effort") or ""
        effort = e if e in ("low", "medium", "high") else ("medium" if self.cfg.get("thinking") else "low")
        if external:                # cuánto contexto y cuánta salida admite ese modelo: se le pregunta al servicio (una vez)
            try:
                API.limits(base, key, self.cfg.get("external_model") or "", ask=True)
                self.cfg["n_ctx"] = API.context(self.cfg)
            except Exception:
                pass
        nudged = False
        # El tope de pasos por turno protege de bucles con modelos pequeños. Un modelo por API hace tareas de decenas de
        # pasos sin perderse y cada parada obliga al usuario a escribir «continúa»: si el tope sigue en su valor de fábrica
        # (30) se le dan 120; un valor elegido a mano se respeta.
        steps = int(self.cfg["max_steps"])
        if external and steps == 30 and not self.cfg.get("_sub"):
            steps = 120
        self.cfg["max_steps"] = steps
        try:
            for step in range(steps):
                if self.stop.is_set():
                    break
                self._maybe_compact(base, key)
                msgs = self.s["messages"]
                if self._deliver(msgs):                 # el usuario escribió mientras trabajaba: lo ve ahora
                    nudged = False
                self.emit({"t": "turn_start", "step": step + 1})
                sent = self._fit(self._to_llm())
                payload = {"model": (self.cfg.get("external_model") or "local") if external else "local", "stream": True,
                           "stream_options": {"include_usage": True},
                           "messages": [{"role": "system", "content": self.system}] + sent,
                           "max_tokens": self._max_out(effort)}
                if external:       # el esfuerzo, con el parámetro propio de cada servicio; la temperatura, solo a mano
                    payload.update(API.effort_params(base, effort, payload["model"]))  # (con «automático», la suya)
                    hint = API.effort_hint(base, payload["model"], effort)
                    if hint:           # el servicio no deja elegirlo: se le pide al modelo en sus instrucciones
                        payload["messages"][0] = dict(payload["messages"][0], content=payload["messages"][0]["content"] + "\n\n" + hint)
                    if self.cfg.get("sampling", "auto") != "auto":
                        payload.update({"temperature": self.sampling["temperature"], "top_p": self.sampling["top_p"]})
                else:              # parametros propios de llama.cpp (una API estricta podria rechazarlos)
                    payload.update({"temperature": self.sampling["temperature"], "top_p": self.sampling["top_p"]})
                if not external:
                    # esfuerzo según lo que trae el modelo de fábrica (local_think): niveles propios, o encender/apagar con tope
                    kw, think_extra = local_think(effort, self.cfg.get("_think_style") or "", self.cfg.get("_think_budget"))
                    payload.update({"top_k": self.sampling["top_k"], "cache_prompt": True, "min_p": self.sampling["min_p"],
                                    "repeat_penalty": float(self.cfg.get("repeat_penalty", 1.0)), "chat_template_kwargs": kw}, **think_extra)
                    if int(self.cfg.get("seed", -1)) >= 0:
                        payload["seed"] = int(self.cfg["seed"])
                    payload["return_progress"] = True       # cuánto lleva leído (el chat lo muestra mientras espera)
                payload["tools"] = self.tools
                for k in ("cut", "cut_tokens", "quiet_max", "rx", "rx_n", "t_gen"):
                    self.holder.pop(k, None)
                hook = self.cfg.get("_before_llm")
                if callable(hook) and not external:
                    try:
                        hook()
                    except Exception:
                        pass
                watched = threading.Event()
                threading.Thread(target=self._watch, args=(external, watched), daemon=True).start()
                try:
                    res = self._call_llm(external, base, key, payload)
                except (ConnectionRefusedError, socket.timeout, OSError) as e:
                    watched.set()
                    self._flush()
                    if self.stop.is_set():
                        break
                    if isinstance(e, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)) or \
                            getattr(e, "winerror", 0) in (10053, 10054):   # se cortó a mitad de la respuesta
                        self.emit({"t": "error", "text": tr("Se cortó la conexión con el modelo mientras respondía (el servidor se cerró o se "
                                                            "reinició). %s") % (
                            tr("Comprueba que siga encendido y pulsa «Reintentar».") if external else
                            tr("Si se apagó, enciéndelo con «Encender modelo» y pulsa «Reintentar»."))})
                    else:
                        self.emit({"t": "error", "text": tr("No puedo conectar con el modelo en %s (%s). %s") % (
                            base, e, tr("Comprueba que ese servidor esté encendido.") if external else tr("Enciéndelo con el botón «Encender modelo»."))})
                    break
                except LLMError as e:
                    watched.set()
                    self._flush()
                    if self.stop.is_set():
                        break
                    if external:                 # explicado igual para cualquier servicio (y con su detalle, corto)
                        self.emit({"t": "error", "text": ERR.friendly(e.status, e.body, payload.get("model"), e.tries),
                                   "detail": str(e)[:2000]})
                    else:
                        self.emit({"t": "error", "text": tr("Error del modelo: %s") % e})
                    break
                except Exception as e:
                    watched.set()
                    self._flush()
                    if self.stop.is_set():
                        break
                    self.emit({"t": "error", "text": tr("Conexión con el modelo interrumpida: %s: %s") % (type(e).__name__, e)})
                    break
                watched.set()
                self._flush()
                if self.stop.is_set():
                    break
                if res["finish"] == "cut":              # escribía sin producir nada visible: se cortó y se le pide que siga
                    self._cuts += 1
                    text_out = res["content"]
                    if text_out.strip():                # lo que sí llegó se conserva (una acción a medio escribir, no)
                        msgs.append({"role": "assistant", "content": text_out})
                    self.emit({"t": "assistant_end", "text": text_out})
                    if self._cuts > 2:
                        self.emit({"t": "error", "text": tr("El modelo se queda escribiendo sin producir respuesta ni acción. Pulsa "
                                                            "«Reintentar»; si se repite, baja el nivel de razonamiento o prueba otro modelo.")})
                        break
                    msgs.append({"role": "user", "_auto": True, "content": NUDGE_QUIET_API if external else NUDGE_QUIET})
                    self.emit({"t": "nudge", "written": "", "quiet": True, "api": bool(external), "tokens": int(self.holder.get("cut_tokens") or 0)})
                    continue
                if int(self.holder.get("quiet_max") or 0) >= self.QUIET_CUT[0] and (res["tool_calls"] or res["content"].strip()):
                    self.s["_quiet_ok"] = True          # este modelo entrega tramos largos de golpe y acaba bien: no cortarle
                # calibrar la estimacion de tokens con lo que realmente conto el servidor
                real = (res.get("usage") or {}).get("prompt_tokens")
                if real:
                    est = (self._estimate(sent) / float(self.s.get("_ratio", 1.0))) + self._fixed_tokens() / float(self.s.get("_ratio", 1.0))
                    if est > 50:
                        self.s["_ratio"] = round(max(0.5, min(3.0, 0.5 * float(self.s.get("_ratio", 1.0)) + 0.5 * real / est)), 3)
                self.truncated = res["finish"] == "length"
                # ids propios y unicos: algunos servidores repiten ids (p. ej. "call_0") entre turnos
                # (Claude por su API nativa: sus propios ids, que deben coincidir con los de su respuesta guardada)
                calls = [dict({"id": c["id"] if res.get("keep_ids") and c.get("id") else "call_" + uuid.uuid4().hex[:12], "type": "function",
                               "function": {"name": c["name"], "arguments": c["args"] or "{}"}}, **({"_x": c["extra"]} if c.get("extra") else {}))
                         for c in res["tool_calls"] if c["name"]]
                text_out = res["content"]
                if not calls and "<tool_call>" in text_out:
                    calls, text_out = parse_text_tool_calls(text_out)
                if self.truncated and calls:     # la última acción pudo quedar a medias: no se ejecuta (ver CUT_CALL)
                    self._cut_ids.add(calls[-1]["id"])
                tm = res.get("timings") or {}
                speed = self.cfg.get("_note_speed")
                if callable(speed) and not external and int(tm.get("predicted_n") or 0) >= 32 and tm.get("predicted_per_second"):
                    speed(tm["predicted_per_second"])    # para que el menú del esfuerzo diga cuánto tardaría cada nivel
                after = self.cfg.get("_after_llm")
                if callable(after) and not external:     # el motor tiene leída la conversación hasta aquí
                    try:
                        after(int((res.get("usage") or {}).get("prompt_tokens") or 0) + int(tm.get("predicted_n") or 0))
                    except Exception:
                        pass
                spent = res.get("spent") or {}       # servicio por API: tokens y coste de este paso (lo anotó ext_stream)
                self.emit({"t": "stats", "prompt_n": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"), "gen_n": tm.get("predicted_n"),
                           "tps": tm.get("predicted_per_second"), "finish": res["finish"],
                           "ctx_used": (res.get("usage") or {}).get("prompt_tokens"), "ctx_max": int(self.cfg["n_ctx"]),
                           "tok_in": spent.get("i"), "tok_out": spent.get("o"), "usd": spent.get("usd"), "usd_src": spent.get("p"),
                           # razonó sin mostrarlo (el servicio solo dice cuántos tokens dedicó a pensar)
                           "think_tok": hidden_reasoning(res.get("usage")) if external and not (res.get("reasoning") or "").strip() else None,
                           # Claude por su API muestra un resumen de su razonamiento, no el razonamiento entero: el chat lo dice
                           "think_summary": bool(res.get("blocks") and (res.get("reasoning") or "").strip()) or None})
                if external and spent.get("usd") is not None:
                    self._spend_check()
                am = {"role": "assistant", "content": text_out}
                if calls:
                    am["tool_calls"] = calls
                if res.get("blocks"):                   # Claude: su respuesta tal cual (con el razonamiento), para devolvérsela
                    am["_ant"], am["_ant_model"] = res["blocks"], payload.get("model")
                elif external and (res.get("reasoning") or "").strip():
                    am["_reasoning"] = res["reasoning"]  # DeepSeek y Kimi exigen que se les devuelva (API.prepare)
                if external and (res.get("extra") or any(c.get("_x") for c in calls)):
                    # lo propio del servicio (firmas de razonamiento…): se le devuelve a él, y solo a él (API.prepare)
                    am["_xbase"], am["_xmodel"] = base, payload.get("model")
                    if res.get("extra"):
                        am["_x"] = res["extra"]
                msgs.append(am)
                self.emit({"t": "assistant_end", "text": text_out})
                wrote = None if calls or self.cfg.get("mode") == "plan" else \
                    written_tool_call(text_out, list(T.TOOLS) + [s["function"]["name"] for s in self.tools or []])
                offer = bool(wrote) and offered_call(text_out, wrote)    # se la propone al usuario: no dice haberla hecho
                if wrote and nudged and not offer:
                    rec = parse_written_call(text_out, self.tools)
                    if rec:
                        calls = [{"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                                  "function": {"name": rec[0], "arguments": json.dumps(rec[1], ensure_ascii=False)}}]
                        am["tool_calls"] = calls                 # el mensaje ya está en el historial: que lleve la llamada
                        self.emit({"t": "recovered", "name": rec[0]})
                written = None if calls or nudged else wrote
                if written or (not calls and not nudged and self.cfg.get("mode") != "plan" and announced_action(text_out)):
                    nudged = True                   # una sola vez por mensaje del usuario
                    msgs.append({"role": "user", "content": ((NUDGE_OFFER if offer else NUDGE_WRITTEN) % written) if written else NUDGE})
                    self.emit({"t": "nudge", "written": written or "", "offer": offer})
                    continue
                if not calls and not text_out.strip() and not nudged and res["finish"] != "length":
                    nudged = True                   # respuesta vacía (gpt-oss tras una lista larga): se le pide que siga, una vez
                    msgs.append({"role": "user", "content": NUDGE_EMPTY})
                    self.emit({"t": "nudge", "written": "", "empty": True})
                    continue
                if not calls and res["finish"] == "length" and text_out.strip() and self._cut_nudges < 2:
                    self._cut_nudges += 1           # se cortó a mitad de escribir: que siga (dos veces como mucho)
                    msgs.append({"role": "user", "_auto": True, "content": CUT_TEXT})
                    self.emit({"t": "info", "text": tr("La respuesta se cortó por el límite de salida: le pido al modelo que continúe.")})
                    continue
                if not calls:
                    if self.queued():                   # te escribió mientras acababa: sigue, con su mensaje
                        continue
                    if not text_out.strip():
                        self.emit({"t": "info", "text": (tr("El modelo no escribió respuesta (se alcanzó el límite de tokens; sube «longitud máxima» o desactiva el pensamiento).")
                                                       if res["finish"] == "length" else tr("El modelo no escribió respuesta."))})
                    break
                images = []
                for call in calls:
                    if self.stop.is_set():
                        msgs.append({"role": "tool", "tool_call_id": call["id"], "content": "Cancelado por el usuario."})
                        continue
                    if call["id"] in self._cut_ids:     # llegó cortada por el límite de salida: no se hace a medias
                        self.emit({"t": "info", "text": tr("La acción «%s» llegó cortada por el límite de salida y no se ejecutó: "
                                                           "el modelo la repetirá en partes.") % T.TOOL_LABELS.get(call["function"]["name"],
                                                                                                    call["function"]["name"])})
                        msgs.append({"role": "tool", "tool_call_id": call["id"], "content": CUT_CALL})
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
            self.s.pop("_turn_open", None)
            self.s.pop("_cut_err", None)
            if self.stop.is_set() or self._failed:      # se le cuenta al modelo al empezar su siguiente turno
                self.s["_cut_short"] = "stop" if self.stop.is_set() else "error"
                if not self.stop.is_set() and self._last_err:
                    self.s["_cut_err"] = re.sub(r"\s+", " ", self._last_err)[:240]
            if T.CONTROL_RUN is self:                   # una pausa pendiente del aviso en pantalla no pasa a la siguiente tarea
                T.CONTROL_RUN = None
                T.PAUSED.clear()
            if self.stop.is_set():
                self.emit({"t": "info", "text": "Detenido."})
            if self.cfg.get("mode") == "plan" and self.s.get("plan") and not self.stop.is_set():
                self.emit({"t": "plan_ready"})
            self.emit({"t": "turn_end"})
