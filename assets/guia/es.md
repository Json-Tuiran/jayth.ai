# Guía de Jayth

Esta guía describe la versión instalada de Jayth: qué hace cada parte, dónde está y cómo se usa. Los nombres de
botones y menús son los que se ven en la interfaz (en este idioma). Los datos de este equipo (versión, modelo activo,
carpetas, atajos…) se añaden aparte, sacados de la propia app en el momento de consultarla.

## Qué es Jayth

Jayth es una aplicación de escritorio para Windows, macOS y Linux que convierte un modelo de IA local (formato GGUF,
con llama.cpp) en un agente que trabaja en el equipo del usuario: programa, crea y edita archivos, ejecuta comandos,
usa otros programas, navega por la web con su propio navegador y lee y crea documentos de Word, Excel, PowerPoint y
PDF. Todo ocurre en el equipo y funciona sin internet una vez descargado el modelo. El usuario aprueba cada acción
(o le da vía libre en el modo automático). También puede usar modelos por API (OpenAI, Claude, Gemini, Ollama…).
Creado por Ing. Jeison Tuiran. Software libre con licencia GPL-3.0. Web: https://github.com/Json-Tuiran/jayth.ai

## La ventana principal

- **Barra lateral (izquierda):** arriba, el botón ≡ para ocultarla (Ctrl+Shift+S) y el selector **Chat / Code**.
  Debajo, **Nueva conversación** (Ctrl+N), **Buscar en tus conversaciones** (Ctrl+K) y el historial agrupado por fecha
  (Hoy, Ayer, Últimos 7 días…; clic en un grupo para plegarlo). Clic derecho en una conversación: **Renombrar** o
  **Borrar**. Abajo del todo, el botón de tu perfil (**Tu perfil y ajustes**) y, cuando hay una versión nueva, el botón
  de actualización. Con la barra oculta, se asoma al pasar el ratón por el borde izquierdo.
- **Barra superior:** a la izquierda, el estado del modelo (p. ej. «● Listo · local»). A la derecha: **Temporal**
  (chat temporal), el globo (**Navegador de Jayth**), **Distribución de paneles**, la carpeta (abre la carpeta de
  trabajo) y **⋯ Más opciones** (Renombrar conversación, Abrir carpeta de trabajo, Borrar conversación). En Jayth Code
  aparecen además los botones del **Explorador de archivos** (Ctrl+B), la **Terminal** (Ctrl+`) y el **Panel del
  agente** (Ctrl+L).
- **Menú de tu perfil** (abajo en la barra lateral): Ajustes, Personalización, Memoria, Asistentes y habilidades,
  Tareas programadas, Modelos, Modelos por API…, Atajos de teclado, Enviar comentarios…, Informar de un error…,
  Buscar actualizaciones, Acerca de Jayth y Salir.
- **Bandeja del sistema:** Mostrar, Pregunta rápida, Detener agente y Salir.

## El cuadro de mensaje

- **Enter** envía; **Mayús+Enter** hace un salto de línea. Ctrl+V pega una imagen.
- Botón **+**: Adjuntar archivos o documentos…, Adjuntar imagen…, Adjuntar captura de pantalla y **Usar un asistente**.
- **Micrófono:** dictar con la voz (se transcribe en el equipo; el modelo de dictado se descarga la primera vez).
- **Chip de permisos** (p. ej. «Preguntar» o «Automático»): cambia el modo de permisos de esta conversación.
- **Chip del modelo** (p. ej. «Qwen3.8 27B · Bajo»): cambia de modelo, el **Esfuerzo** (cuánto razona antes de
  responder: Bajo, Medio, Alto), descarga o añade modelos, Gestionar modelos…, Modelos por API… y **Motor**
  (encender o apagar el modelo).
- Si el modelo está apagado, encima del cuadro sale un aviso con **Encender modelo** (se puede cerrar con la ×; vuelve
  si cambia la situación). Si escribes con el modelo apagado, Jayth lo enciende y envía el mensaje cuando está listo.
- Mientras el agente trabaja, el botón de enviar se convierte en **Detener**.

## Modos de permiso

Se cambian en el chip de permisos del cuadro de mensaje (para esa conversación) o en **Ajustes › Agente y permisos ›
Permisos por defecto**. Hay cinco: Solo lectura, Planificar, Preguntar, Editar archivos y Automático (la lista exacta
con su descripción va en los datos de esta versión). En los modos que preguntan, cada acción muestra **Permitir** y
**Denegar**. Las acciones delicadas (borrar, instalar, `sudo`, tocar el sistema o rutas protegidas) piden permiso
siempre, también en Automático. En **Planificar** el agente investiga y propone un plan; con **Ejecutar el plan** lo
lleva a cabo (o **Seguir ajustando**). Para detener al instante el control del ratón: llevar el puntero a la esquina
superior izquierda de la pantalla.

## Lo que se ve mientras trabaja

- Antes de cada acción el agente dice en una frase qué va a hacer. Cada acción es una línea con su icono y una
  animación mientras se ejecuta; al pulsarla se despliega el detalle (el comando exacto, el cambio, el resultado).
- **Pensamiento:** la línea «Pensó durante…» se despliega para ver su razonamiento.
- **Capturas:** cuando comprueba algo mirando la pantalla o una ventana, la captura sale en el chat (clic para verla en
  grande).
- **Plan:** en tareas largas, una lista de tareas fija sobre el cuadro de mensaje (Plan · n de m).
- **Preguntas:** si necesita un dato, pregunta con opciones; se responde con un clic o con **Otra respuesta…**.
- Los archivos que el agente crea o cambia se pueden abrir desde el chat (rutas como enlaces) y los comandos que deba
  ejecutar el usuario salen con botones **Copiar** y **Ejecutar**.

## Acciones sobre las respuestas

Debajo de cada respuesta: **Copiar respuesta**, **Leer en voz alta**, **Regenerar respuesta**, **Informar de un
problema con esta respuesta** y, si cambió archivos, **Deshacer cambios** (restaura todos los archivos que cambió en esa
respuesta). Cada acción que cambia archivos también tiene su propio botón para deshacer solo ese cambio. A la derecha,
los tokens, la velocidad y la memoria de la conversación usada.

## Acciones sobre tus mensajes

Al pasar el ratón por un mensaje tuyo: **Copiar mensaje**, **Editar y volver a enviar** (se edita en el propio
mensaje; Ctrl+Enter envía, Esc cancela), **Reintentar desde aquí** y **⋯ Más acciones**: **Volver a este punto** (quita
ese mensaje y lo posterior y te deja el texto en el cuadro) y **Nueva conversación desde aquí** (copia la conversación
hasta ese punto, la original no cambia). Si después de ese mensaje el agente cambió archivos, Jayth pregunta si
**Deshacer esos cambios** o **Mantener los archivos**. No se puede volver a un mensaje que ya quedó dentro del resumen
de una conversación muy larga. Hay que esperar a que el agente termine (o detenerlo).

## Conversaciones

- Se guardan solas en el historial. **Buscar en tus conversaciones** (Ctrl+K) busca en títulos y mensajes.
- El título lo pone el modelo tras la primera respuesta; se cambia con **Renombrar**.
- **Chat temporal** (botón **Temporal** de la barra superior): no se guarda en el historial y no usa ni cambia la memoria.
- Los errores del chat (p. ej. «No puedo conectar con el modelo») traen **Reintentar** y **Quitar este aviso**.
- Exportar todas a Markdown o borrarlas: **Ajustes › Datos y privacidad**.
- Cuando una conversación es muy larga, Jayth resume la parte antigua para que el modelo no la olvide.

## Jayth Code (proyectos)

- Se entra con **Code** en la barra lateral (Ctrl+2; Ctrl+1 vuelve a Chat). **Nuevo proyecto** o **Abrir carpeta…**.
  Los proyectos aparecen en la sección **Proyectos** de la barra lateral, cada uno con sus conversaciones (clic derecho:
  **Editar proyecto…** para el nombre, la carpeta y las **instrucciones del proyecto**; **Quitar de la lista**).
- **Explorador de archivos** (Ctrl+B): iconos por tipo; los archivos que cambió el agente llevan un punto verde. Clic
  derecho: Abrir, Abrir con su programa, Nuevo archivo…, Nueva carpeta…, Renombrar, Copiar ruta, Copiar ruta relativa,
  Mover a la papelera. **Ir a un archivo…** con Ctrl+P.
- **Editor:** pestañas (Ctrl+S guarda, Ctrl+W cierra). Markdown, HTML, SVG y CSV se abren con **Vista previa** y se
  cambia a **Código** para editar. Word, Excel, PowerPoint y PDF se ven en modo lectura; las imágenes, con zoom.
  **Abrir con su programa** abre el archivo con la app del sistema. **Ajustar líneas** (Alt+Z) para las líneas largas.
- **Guardado automático (autoguardado):** por defecto guarda tras 1 segundo sin escribir. Se cambia en **Ajustes › General › Editor
  de Jayth Code** (también al cambiar de pestaña o de ventana, o desactivado: guardar con Ctrl+S). Una pestaña con «●»
  tiene cambios sin guardar; con «⚠», no se pudo guardar (el motivo sale al pasar el ratón).
- **Terminal** (Ctrl+`): la del sistema (PowerShell en Windows, zsh/bash en macOS y Linux), dentro de la carpeta del
  proyecto; ↑ ↓ recorre el historial. Para comandos, no para programas interactivos.
- **Panel del agente** (Ctrl+L): el chat del proyecto; el agente trabaja dentro de la carpeta del proyecto y lee las
  normas de AGENTS.md, JAYTH.md o CLAUDE.md si existen.
- **Distribución de paneles** (barra superior): mostrar u ocultar paneles, agente a la izquierda o a la derecha,
  terminal debajo o a la derecha del editor y **Modo enfoque (solo el editor)** (Ctrl+Shift+M). Los divisores se
  arrastran; doble clic en uno pliega el panel de al lado. Todo se recuerda.

## Navegador de Jayth

Botón del globo en la barra superior. El usuario puede navegar en él o pedir al agente que use una web (buscar dentro
de un sitio, rellenar formularios, páginas con JavaScript). El agente lo maneja a la vista, con su propio puntero y un
brillo en los bordes mientras tiene el control; el usuario puede intervenir cuando quiera. Las contraseñas las escribe
siempre el usuario, y el agente pide confirmación antes de comprar, pagar, publicar o enviar datos personales.

## Lienzo

Para páginas web, documentos largos, diagramas SVG o programas que el usuario quiera ver: el agente los muestra en un
panel junto al chat («Ver en el lienzo»), con vista previa y código, versiones (v1 de n) y opción de guardarlos.

## Imágenes

El agente puede crear imágenes nuevas (fotos, ilustraciones, logotipos, iconos, fondos, portadas) en el propio equipo:
cuando se lo pides o cuando una tarea las necesita (ilustrar una web, una presentación o un documento). También
modifica una imagen que ya tienes (con FLUX.2 [klein]). Mientras la crea se ve el paso en el que va, lo que queda y una
vista previa; al terminar aparece en grande en el chat con **Abrir** y **Mostrar en la carpeta**. Se guarda en la
carpeta «imagenes» de la carpeta de trabajo (o del proyecto), o en la que se elija en Ajustes.

- Funciona sin internet ni servicios externos, con stable-diffusion.cpp (MIT) y un modelo de imagen de licencia libre
  (Apache-2.0 o MIT): **FLUX.2 [klein] 4B** (versátil y con texto dentro de la imagen, el recomendado con tarjeta
  gráfica), **Z-Image Turbo** (más realista, mejor con tarjeta gráfica) o **Segmind Vega RT** (el más rápido sin
  tarjeta gráfica, en 4 pasos, con menos detalle). En «Automático», Jayth elige según el equipo.
  Sin tarjeta gráfica, FLUX.2 tarda unos 11 minutos por imagen (medido en un portátil con un i5 de 4 núcleos).
- La primera vez hay que instalarlo (unos 5 GB, una sola vez): con **Instalar** en la tarjeta que aparece en el chat
  cuando el agente lo necesita (después, **Continuar**), o en **Ajustes › Imágenes**. Se ve el avance, se puede
  cancelar y se reanuda si se corta. **Quitar** borra sus archivos.
- Tiempo: con tarjeta gráfica, menos de un minuto por imagen; sin ella, varios minutos (por eso, sin tarjeta gráfica se
  crean a 512 px). Se cambia en Ajustes › Imágenes › «Tamaño de las imágenes».
- Solo se usa si el modelo de texto activo no crea imágenes por sí mismo (hoy ninguno de los que funcionan con
  llama.cpp lo hace). Se apaga con «Permitir que el agente cree imágenes».
- Cada imagen es una acción de escritura: según el modo de permisos se aprueba antes de crearla, y se puede deshacer.
- Para gráficos de datos el agente usa Python, y para diagramas, SVG en el lienzo.

## Conocimiento

En **Ajustes › Conocimiento** se eligen carpetas (notas, documentos, proyectos) y el agente busca en ellas por
significado, no solo por palabras exactas («¿cuánto costó arreglar el carro?» encuentra la nota de la factura del
coche), sin tener que leerlas enteras: ideal con modelos locales, que tienen poca memoria de conversación. Lo hace
con un buscador pequeño que funciona en el equipo (Qwen3-Embedding 0.6B, 640 MB, una sola descarga) y entiende
español, inglés, portugués y muchos más idiomas. Admite texto, código, Markdown, Word, PDF, PowerPoint y Excel.

- **Buscador por significado:** **Instalar** (una vez).
- **Carpetas de conocimiento:** **Añadir carpeta…** y **Quitar**.
- **Índice:** cuántos archivos y fragmentos tiene y cuándo se actualizó; **Actualizar el índice** (solo relee lo nuevo
  o cambiado) y «Actualizar el índice al abrir Jayth».
- El agente lo usa solo cuando hace falta (p. ej. «según mis notas…») y cita de qué archivo sale cada dato.

## Control del ordenador y otros programas

El agente puede abrir programas y archivos, leer los botones y campos de cualquier ventana (accesibilidad del sistema),
hacer clic, arrastrar, escribir, pulsar atajos, manejar ventanas, usar el portapapeles y hacer capturas de la pantalla o
de una ventana. Mientras controla, se ven un brillo en los bordes de la pantalla y su puntero. Se activa o desactiva en
**Ajustes › Herramientas › Permitir el control del ordenador**. En macOS hay que dar a Jayth los permisos de
**Grabación de pantalla** y **Accesibilidad** (Ajustes del Sistema › Privacidad y seguridad). En Linux funciona en
sesiones X11 (en Wayland el control global está limitado); para listar ventanas hace falta `wmctrl`.

## Modelos

- **Modelos** (menú del perfil, o Ajustes › Modelos › Gestionar modelos…): lista de modelos instalados con su tipo,
  variante y tamaño. **Usar este**, **Añadir modelo…**, **Localizar…** (si moviste el archivo), **Buscar en una
  carpeta…**, **Abrir carpeta**, **Quitar de la lista** y **Borrar archivos…**.
- **Añadir un modelo** (asistente): catálogo de modelos abiertos de Hugging Face marcados según quepan en el equipo
  (Agente = usa herramientas; Visión = entiende imágenes; Razona = piensa antes de responder), un repositorio escrito a
  mano (usuario/Modelo-GGUF), un archivo .gguf propio o una carpeta con el modelo original (config.json +
  .safetensors), que Jayth convierte a GGUF en el equipo. Se elige la cuantización (la recomendada va marcada) y, si
  existe, la **visión** para que el modelo vea imágenes y capturas.
- **Modelos por API…**: OpenAI, Claude, Gemini, Ollama, LM Studio u otro servidor compatible con OpenAI. También en
  **Ajustes › Modelos › Proveedor** (URL, nombre del modelo y clave).
- **Encender o apagar el modelo:** chip del modelo › **Motor**, o el botón **Encender modelo** del aviso. Encendido
  ocupa memoria y responde al momento; apagado la libera.
- Las descargas muestran porcentaje, velocidad y tiempo, se reanudan si se cortan y se comprueban con SHA-256.
- Si se publica una versión nueva de uno de tus modelos, Jayth avisa (se desactiva en Ajustes › Acerca de › Novedades).

## Motor y rendimiento

Jayth descarga la versión oficial de llama.cpp adecuada al equipo: Metal en Mac con Apple Silicon, CUDA para NVIDIA,
Vulkan para AMD o Intel Arc, o CPU. En **Ajustes › Rendimiento**: **Cambiar o actualizar el motor…**, **Precalentar al
encender el modelo**, **Memoria de la conversación (contexto)** (por defecto **Automático**: todo el contexto que admite
el modelo de fábrica, reducido si su memoria no cabe en el equipo; con **Contexto comprimido** cabe el doble o más),
**Apagar el modelo si no se usa durante**, y en
**Ajustes del motor**: Hilos de CPU, Capas en la GPU (automático reparte el modelo entre GPU y RAM), Tamaño de lote,
Contexto comprimido, Flash attention, Aceleración al escribir, mmap, bloquear en la RAM y el puerto local. Los cambios del motor se aplican al
reiniciar el modelo (**Reiniciar modelo**). El registro del motor está en **Ajustes › Registro del modelo**.

- **Optimizar para este equipo** (Ajustes › Rendimiento): en vez de estimar, mide de verdad con el modelo activo (unos
  minutos, con el modelo apagado mientras tanto): prueba hilos y flash attention con llama-bench y la «Aceleración al
  escribir» (decodificación especulativa: **MTP**, para modelos que traen esas capas como Qwen 3.5 y 3.8, y
  **n-gramas**, que acelera al reescribir código o texto), y deja lo más rápido. Debajo se ve el resultado («lee … tok/s
  · escribe … tok/s»). «Aceleración al escribir» también se elige a mano en Ajustes del motor.
- **Memoria:** al encender el modelo, Jayth avisa si no cabe en el equipo (irá muy lento y conviene una variante más
  pequeña) o si en ese momento otros programas ocupan la memoria. La memoria que guarda llama.cpp de conversaciones
  anteriores se ajusta sola a lo que sobra, para no quitársela al modelo.

## Ajustes

Se abren desde el menú del perfil (**Ajustes**). Los cambios se guardan solos. Páginas y opciones (con su nombre exacto):
- **General:** «Idioma de la interfaz», «Tema», «Tamaño del texto», «Animaciones (aparición de mensajes, barra
  lateral, avisos)», «Barra de título integrada en la ventana» (solo Windows).
  - **Editor de Jayth Code:** «Guardado automático de los archivos».
  - **Inicio y ventana:** abrir Jayth al iniciar el sistema (minimizado en la bandeja), «Encender el modelo al abrir
    Jayth», «Al cerrar la ventana, seguir funcionando en la bandeja del sistema», «Avisarme cuando el agente necesite mi
    aprobación», «Atajo de la ventana rápida».
- **Personalización:** «¿Cómo quieres que te llame?», «¿Qué debería saber Jayth de ti?», «¿Cómo quieres que responda?»,
  «Idioma de las respuestas», «Instrucciones adicionales para el agente».
  - **Voz:** «Precisión del dictado», «Idioma del dictado».
  - **Memoria:** «Usar la memoria (recordar cosas entre conversaciones)», la lista de recuerdos (añadir, editar o
    borrar) y **Borrar toda la memoria**.
- **Modelos:** el modelo activo, **Gestionar modelos…**, **Añadir modelo…**, **Asistente de configuración…** y «Carpeta
  donde se descargan los modelos».
  - **Proveedor:** «¿Qué motor usa el agente?» (local o servidor externo), «URL del servidor externo (termina en /v1)»,
    «Nombre del modelo en ese servidor», «Clave de API (si el servidor la pide)» y **Probar conexión**.
- **Generación:** «Pensar a fondo por defecto (mejores respuestas, más lento)», «Parámetros de muestreo» (recomendados
  para el modelo activo o personalizados), «Temperatura», «Longitud máxima de cada respuesta (tokens)».
  - **Muestreo avanzado:** «Top-p», «Top-k», «Min-p», «Penalización por repetición», «Semilla» y **Restablecer valores
    recomendados**.
- **Rendimiento:** **Cambiar o actualizar el motor…**, «Precalentar al encender el modelo», «Memoria de la conversación
  (contexto)», «Apagar el modelo si no se usa durante».
  - **Ajustes del motor:** «Hilos de CPU», «Capas en la GPU», «Tamaño de lote», «Contexto comprimido», «Flash
    attention», «Cargar el modelo con mmap (arranque más rápido)», «Bloquear el modelo en la RAM (evita que el sistema lo
    mueva al disco)», «Puerto local del motor».
  - **Descargas:** «Conexiones simultáneas al descargar modelos».
- **Agente y permisos:** «Permisos por defecto», «Carpeta de trabajo del modo Chat», «Comandos que se permiten sin
  preguntar».
  - **Límites:** «Máximo de pasos por tarea», «Tiempo máximo de cada comando», «Máximo de texto que recibe el modelo de
    cada acción», «Enviar capturas e imágenes al modelo (si tiene visión)», «Imágenes recientes que recuerda».
- **Herramientas:** «Permitir el acceso a internet (buscar, leer páginas y descargar)», «Permitir el control del
  ordenador (ratón, teclado, capturas)», «Herramientas que se cargan» (por defecto, solo las que necesita cada tarea:
  el agente tiene a mano las básicas y activa los demás grupos —web, navegador, control del PC, documentos, Python,
  imágenes, agenda y cada conector— cuando le hacen falta; así el modelo local tiene más memoria y responde antes).
  - **Herramientas disponibles:** cada herramienta del agente se puede apagar por separado.
  - **Búsqueda web:** «Buscador» (automático con DuckDuckGo y Bing, sin clave; Brave Search o SearXNG), «Clave de Brave
    Search», «URL de SearXNG».
  - **Servicios con tu cuenta:** fichas para conectar servicios en línea (**Conectar**, **Desconectar**, **Configurar
    Google…**).
  - **Conectores MCP:** plantillas, añadir (**Añadir y probar**), probar y quitar conectores.
- **Conocimiento:** buscador por significado (**Instalar**), carpetas (**Añadir carpeta…**, **Quitar**), índice
  (**Actualizar el índice**) y «Actualizar el índice al abrir Jayth».
- **Imágenes:** «Permitir que el agente cree imágenes».
  - **Modelo de imagen:** «Modelo elegido» (Automático, FLUX.2 [klein] 4B, Z-Image Turbo o Segmind Vega RT), su estado y **Instalar**, **Cancelar** o
    **Quitar**.
  - **Imágenes creadas:** «Tamaño de las imágenes» (Automático, 512, 768 o 1024 px) y «Carpeta donde se guardan».
- **Datos y privacidad:** la carpeta de datos (**Abrir carpeta**).
  - **Conversaciones:** **Exportar conversaciones (Markdown)…**, liberar espacio de imágenes sin usar y borrar todas las
    conversaciones.
- **Registro del modelo:** el registro del motor llama.cpp (para diagnosticar) y **Actualizar**.
- **Atajos de teclado:** la lista de atajos.
- **Acerca de:** versión, autor y licencia (**Ver la licencia**, **Política de marca**), **Buscar actualizaciones**,
  **Abrir en GitHub**.
  - **Novedades:** «Avisarme cuando haya una versión nueva de Jayth», «Descargar las actualizaciones en segundo plano e
    instalarlas al cerrar Jayth», «Avisarme cuando se publique una versión nueva de mis modelos».
  - **Comentarios:** **Informar de un error…** y **Sugerir una mejora…**.

## Personalización y memoria

En **Personalización** se le dice al agente cómo llamarte, qué saber de ti, cómo responder (estilo), en qué idioma
responder (Automático = el idioma de tu mensaje) e instrucciones adicionales. La **memoria** guarda preferencias
duraderas entre conversaciones (el agente las guarda cuando se las dices, p. ej. «uso pnpm»); se revisa, edita o borra
en Personalización › Memoria y se puede apagar. El chat temporal no la usa.

## Asistentes y habilidades

Menú del perfil › **Asistentes y habilidades**. Un **asistente** es un agente con instrucciones y archivos de referencia
propios (p. ej. «Corrector de estilo»); se elige con **+ › Usar un asistente** en el cuadro de mensaje. Una
**habilidad** es un procedimiento que el agente usa cuando encaja con la tarea (p. ej. «Redactar informes ejecutivos y
entregarlos en Word»); se crean, importan, activan o desactivan en la pestaña Habilidades (**Añadir ejemplos** trae
algunas de muestra).

## Tareas programadas

Menú del perfil › **Tareas programadas**. Una tarea es un encargo que el agente hace solo a su hora (Una vez, Cada día,
De lunes a viernes, Cada semana en los días elegidos o Cada cierto tiempo) y avisa al terminar: **Nueva tarea**, nombre, qué debe hacer, cuándo, cómo actúa (permisos),
**Ejecutar ahora** y **Ver último resultado**. Las tareas se ejecutan mientras Jayth esté abierto (también en la bandeja).
El agente también puede programarlas si se le pide.

## Ventana rápida

Una barrita para preguntar a Jayth desde cualquier programa: atajo **Ctrl+Alt+J** (se cambia o desactiva en Ajustes ›
General › Atajo de la ventana rápida) o **Pregunta rápida** en la bandeja. **Con captura** adjunta una imagen de lo que
había en la pantalla (Ctrl+S). Enter envía, Esc cierra.

## Conectores MCP y búsqueda web

- **Conectores MCP** (Ajustes › Herramientas): amplían las herramientas del agente con el estándar Model Context
  Protocol (archivos, memoria, navegador Playwright, Git, Fetch, GitHub…). Hay plantillas que rellenan el formulario;
  pueden ser un programa del equipo (comando y argumentos, muchos necesitan Node.js o uv) o un servicio remoto
  (dirección y clave). **Añadir y probar** los conecta; si el servicio pide iniciar sesión, se abre su página
  (después, **Iniciar sesión** o **Cerrar sesión** en su fila).
- **Servicios con tu cuenta** (Ajustes › Herramientas): todo es opcional; Jayth funciona en local y sin internet. Hay
  fichas para Higgsfield (imágenes y vídeo con IA en la nube, con tus créditos), Notion, Canva, Gmail, Google Drive,
  Google Calendar, Linear, Jira y Confluence, y Hugging Face (sin cuenta). **Conectar** abre la página del servicio en
  el navegador: el usuario inicia sesión allí y autoriza; Jayth nunca ve la contraseña y guarda el permiso cifrado en
  el equipo (se renueva solo). **Desconectar** lo olvida. Gmail, Drive y Calendar piden antes **Configurar Google…**:
  crear una vez un «ID de cliente de OAuth» de tipo «App de escritorio» en Google Cloud (con las API de MCP activadas y
  el correo como usuario de prueba) y pegar su ID y su secreto; sirve para los tres.
- Si una tarea lo necesita, el agente puede proponer conectar un servicio: aparece su ficha en el chat con
  **Conectar** y, al terminar, **Continuar**. Lo que cambie algo en la cuenta (enviar, publicar, gastar créditos)
  siempre pide aprobación, también en modo Automático; leer no.
- **Búsqueda web:** funciona sin configurar nada: DuckDuckGo y, si pide verificación (Jayth no se la salta), Bing a través del motor del navegador integrado, sin mostrarlo. Wikipedia queda como último recurso. Una clave de Brave Search o una instancia propia de SearXNG son opcionales.

## Idioma de la interfaz

Jayth está en español, inglés, portugués (Brasil), francés, alemán, italiano,
japonés y chino simplificado. La primera vez usa el idioma del
sistema (si no es ninguno de estos, inglés); se cambia en **Ajustes ›
General › Idioma de la interfaz** y Jayth ofrece reiniciarse para aplicarlo. El idioma en que responde el agente es
aparte: por defecto, el del mensaje del usuario (Ajustes › Personalización › Idioma de las respuestas).

## Actualizaciones

Cuando hay una versión nueva, Jayth la descarga en segundo plano (el botón de la barra lateral muestra «Descargando
actualización… %») sin interrumpir nada. Al terminar, el botón pasa a **Reiniciar para actualizar**: al pulsarlo, Jayth se
cierra, se instala la versión nueva (con una ventanita «Actualizando…») y se vuelve a abrir. Si no se pulsa, se instala
sola al cerrar Jayth. Al abrir la versión nueva sale un aviso con enlace a las **Novedades**. Se puede buscar a mano en el
menú del perfil › **Buscar actualizaciones** y desactivar la descarga automática en Ajustes › Acerca de › Novedades.
Conversaciones, ajustes y modelos se conservan al actualizar.

## Dónde se guarda todo

- **Ajustes, conversaciones, motor y modelos:** Windows `%LOCALAPPDATA%\Jayth`, macOS `~/Library/Application
  Support/Jayth`, Linux `~/.local/share/jayth` (la ruta real de este equipo va en los datos de esta versión).
- **Carpeta de trabajo del modo Chat:** por defecto `Documentos/Jayth`; se cambia en Ajustes › Agente y permisos.
- **Carpeta de modelos:** se cambia en Ajustes › Modelos. Los modelos de imagen van en su subcarpeta `imagen`, y el
  motor de imágenes, junto al de llama.cpp (`runtime/imagen`).
- **Modo portátil:** un archivo `portable.txt` junto al programa guarda todo en `userdata/` a su lado (para un USB).
- **Privacidad:** todo se queda en el equipo; Jayth no envía conversaciones ni archivos a ningún servidor. Solo usa
  internet para descargar modelos y motores, buscar actualizaciones y las herramientas web que el usuario permita (o al
  usar un modelo por API, que recibe los mensajes de esa conversación).
- **Desinstalar:** Windows, Configuración › Aplicaciones › Jayth › Desinstalar; macOS, arrastrar Jayth a la Papelera;
  Linux, borrar el AppImage. Los datos y modelos no se borran al desinstalar.

## Comentarios y ayuda

Menú del perfil › **Enviar comentarios…** o **Informar de un error…** (también en Ajustes › Acerca de): el usuario
revisa el texto antes de enviarlo. Debajo de cada respuesta, **Informar de un problema con esta respuesta**. El
proyecto está en https://github.com/Json-Tuiran/jayth.ai (descargas en Releases).

## Problemas frecuentes

- **«El modelo está apagado» o no responde:** pulsar **Encender modelo** (o escribir: Jayth lo enciende solo). Si no
  arranca, el motivo sale en el aviso y en Ajustes › Registro del modelo; suele ser memoria insuficiente: elegir una
  cuantización más pequeña, bajar la **Memoria de la conversación (contexto)** o usar **Contexto comprimido**.
- **Va lento:** en equipos sin GPU los modelos grandes tardan; probar un modelo más pequeño, bajar el esfuerzo a Bajo
  o, con GPU NVIDIA, comprobar que el motor es CUDA (Ajustes › Rendimiento › Cambiar o actualizar el motor…).
- **No encuentra el modelo («No encuentro el archivo…»):** pulsar **Buscarlo** o, en Modelos, **Localizar…** o
  **Buscar en una carpeta…**.
- **No ve las imágenes:** el modelo necesita visión (proyector); al añadirlo, marcar **Incluir visión**. Comprobar
  Ajustes › Agente y permisos › Enviar capturas e imágenes al modelo.
- **No crea imágenes o falla al crearlas:** instalar el generador en Ajustes › Imágenes y comprobar que «Permitir que el
  agente cree imágenes» está marcado. Si se queda sin memoria, elegir un tamaño menor o FLUX.2 [klein] y cerrar otros
  programas; el detalle del último intento está en el registro `imagen.log` de la carpeta de datos.
- **No puede usar internet o el ratón:** revisar Ajustes › Herramientas (acceso a internet, control del ordenador y la
  lista de herramientas).
- **Windows muestra «Windows protegió su PC»:** el instalador aún no está firmado: Más información › Ejecutar de todas
  formas. **macOS:** la primera vez, clic derecho sobre Jayth › Abrir.
- **El agente no deja volver a un mensaje:** esperar a que termine o detenerlo; los mensajes ya resumidos no se pueden
  rebobinar (usar Nueva conversación).
- **Una pestaña del editor marca ⚠:** no se pudo guardar (archivo de solo lectura o carpeta protegida); el motivo sale
  al pasar el ratón por la pestaña.
