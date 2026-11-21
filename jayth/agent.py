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


NUDGE_WRITTEN = ("[Aviso automático de Jayth, no lo escribió el usuario] Escribiste la llamada a «%s» como texto, así que no se "
                 "ejecutó y lo que digas de su resultado no es cierto. Si hace falta, llámala de verdad como herramienta; si no, "
                 "corrige lo que le dijiste al usuario y termina, en el idioma del usuario. No respondas a este aviso ni lo menciones.")


NUDGE_EMPTY = ("[Aviso automático de Jayth, no lo escribió el usuario] Tu última respuesta llegó vacía. Sigue con la tarea donde "
               "la dejaste, con las herramientas que hagan falta, o, si ya terminaste, da el resultado al usuario, en su idioma. "
               "No respondas a este aviso ni lo menciones.")
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
    if not t or t.endswith(("?", "？")):
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
    elif not can_see(cfg):         # sin ver la captura no sabe qué hay en unas coordenadas: ui_elements + click_element
        off |= {"click", "drag", "move_mouse"}
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
        # solo si el modelo de verdad ve (tiene proyector de visión): si no, el motor rechaza la petición entera (HTTP 500)
        see = can_see(self.cfg)
        keep = set(refs[-int(self.cfg["keep_images"]):]) if see and self.cfg["keep_images"] else set()
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
                        parts.append({"type": "text", "text": "[imagen anterior omitida para ahorrar contexto]" if see else
                                      "[imagen: el usuario la ve en el chat; tú no puedes ver imágenes]"})
                m = dict(m, content=parts)
            out.append({k: v for k, v in m.items() if not k.startswith("_")})   # claves internas (_auto) no van al modelo
        return out

    # ---- memoria de la conversación (contexto): recortar y resumir antes de llegar al tope
    TRIM_AT = 0.70      # a partir de aquí se recortan las salidas antiguas de las herramientas (sin llamar al modelo)
    SUMMARY_AT = 0.85   # y si aun así no baja, el modelo resume lo antiguo

    def ctx_used(self, msgs=None):
        """Tokens que ocupa la conversación (estimados) y el máximo del modelo."""
        msgs = self.s["messages"] if msgs is None else msgs
        return int(self._fixed_tokens() + self._estimate(msgs)), int(self.cfg["n_ctx"])

    def _emit_ctx(self):
        used, mx = self.ctx_used()
        self.emit({"t": "ctx", "used": used, "max": mx})

    def _trim_old_results(self, msgs, keep=3):
        """Sin llamar al modelo: las salidas largas de herramientas antiguas (todas menos las últimas `keep`) se quedan en
        su principio, con una nota. Es lo que más ocupa (archivos, páginas web) y casi nunca vuelve a hacer falta entera.
        Se hace de una vez al cruzar el umbral, no en cada paso (así no se pierde la caché del motor a cada rato)."""
        idx = [i for i, m in enumerate(msgs) if m["role"] == "tool"]
        cut = 0
        for i in idx[:-keep] if keep else idx:
            c = msgs[i].get("content")
            if isinstance(c, str) and len(c) > 700 and not msgs[i].get("_trimmed"):
                msgs[i] = dict(msgs[i], content=c[:400] + "\n[… salida antigua recortada para ahorrar memoria (%d caracteres en total). "
                                                        "Si la necesitas entera, vuelve a pedirla.]" % len(c), _trimmed=True)
                cut += len(c) - 400
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
        payload = {"model": "local", "stream": True, "max_tokens": out_tok * 2, "temperature": 0.2, "cache_prompt": False,
                   "messages": [{"role": "system", "content": "Resumes conversaciones de trabajo de forma fiel y compacta."},
                                {"role": "user", "content": ask}]}
        if self.cfg.get("llm_mode") == "external":
            payload["model"] = self.cfg.get("external_model") or "local"
            payload.pop("cache_prompt")
        else:                                             # sin razonar: el resumen sale antes (en CPU cada token cuenta)
            payload["chat_template_kwargs"] = {"enable_thinking": False, "reasoning_effort": "low"}
        try:
            return (llm_stream(base, key, payload, self.holder, lambda k, t: None)["content"] or "").strip()
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
            cut = self._trim_old_results(msgs)
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
                said = d[5:].strip() if d and d.startswith("deny:") else ""
                if said:                                 # «no, y haz esto otro»: lo que dijo manda sobre lo que iba a hacer
                    return False, ("El usuario no permitió esta acción y te dice qué hacer en su lugar: «%s». Hazle caso y "
                                   "sigue la tarea así." % said), None, {}
                return False, "El usuario denegó esta acción.", None, {}
        extra = {}
        if name in T.WRITE_TOOLS:
            try:
                H.snapshot(self.sid, cid, self._files_of(name, args))
                extra["undo"] = True
            except Exception:
                pass
        if tool["category"] == "control":
            T.CONTROL_RUN = self                     # el botón «Parar» del aviso en pantalla detiene esta tarea
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
    def run(self, text, image_names=(), attachments="", marker=None):
        msgs = self.s["messages"]
        body = text + (("\n\n" + attachments) if attachments else "")
        if on_demand(self.cfg):                         # grupos que seguramente hagan falta: activos desde el primer paso
            files = [l[4:].strip() for l in attachments.splitlines() if l.startswith("### ")]
            valid = {g for g, d in available_groups(self.cfg)}
            new = self._activate([g for g in detect_groups(text, self.cfg, files, image_names) if g in valid])
            guides = [group_guide(g) for g in new if group_guide(g)]
            if new:                                     # sus pautas van con el mensaje (no cambian las instrucciones fijas)
                body += "\n\n[Herramientas activadas para esta tarea: %s]%s" % (", ".join(new), ("\n" + "\n".join(guides)) if guides else "")
        if (self.cfg.get("response_language") or "auto") == "auto":
            lang = guess_language(text)
            if lang and lang != "es":                   # en español ya están las instrucciones
                body += "\n\n[Responde en %s, el idioma de este mensaje.]" % LANG_ES[lang]
        content = body if not image_names else [{"type": "text", "text": body}] + [{"type": "image_ref", "name": n} for n in image_names]
        msgs.append({"role": "user", "content": content})
        uev = {"t": "user", "text": text, "images": list(image_names), "files": [l[4:].strip() for l in attachments.splitlines() if l.startswith("### ")]}
        if marker:                                      # p. ej. «plan»: el chat lo muestra como marca, no como mensaje tuyo
            uev["marker"] = marker
        self.emit(uev)
        external = self.cfg.get("llm_mode") == "external"
        base = self.cfg["external_url"].rstrip("/") if external else "http://127.0.0.1:%d/v1" % int(self.cfg["llm_port"])
        key = self.cfg.get("external_key") if external else ""
        e = self.cfg.get("effort") or ""
        effort = e if e in ("low", "medium", "high") else ("medium" if self.cfg.get("thinking") else "low")
        nudged = False
        try:
            for step in range(int(self.cfg["max_steps"])):
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
            if T.CONTROL_RUN is self:                   # una pausa pendiente del aviso en pantalla no pasa a la siguiente tarea
                T.CONTROL_RUN = None
                T.PAUSED.clear()
            if self.stop.is_set():
                self.emit({"t": "info", "text": "Detenido."})
            if self.cfg.get("mode") == "plan" and self.s.get("plan") and not self.stop.is_set():
                self.emit({"t": "plan_ready"})
            self.emit({"t": "turn_end"})
