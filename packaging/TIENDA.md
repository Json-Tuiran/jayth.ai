# Jayth en la Microsoft Store

Publicar en la Store da dos cosas: más gente encuentra Jayth (la tienda viene con Windows) y **la tienda firma el
paquete**, así que no aparece el aviso «Windows protegió su PC». Las versiones de GitHub siguen igual.

Cómo funciona por dentro:

- La compilación de cada versión crea, además de lo de siempre, un paquete **MSIX sin firmar** con
  `packaging/tienda/crear_msix.py` (la tienda lo firma al publicarlo). Queda como artefacto de la ejecución en
  GitHub Actions («tienda-msix»), no en la Release, porque sin firma no se puede instalar fuera de la tienda.
- Instalado desde la tienda, Jayth **no se actualiza solo**: lo hace la tienda (`osys.store_package()` lo detecta y el
  actualizador se aparta; «Buscar actualizaciones» lo explica).
- Los datos del usuario se guardan como siempre en `%LOCALAPPDATA%\Jayth` (Windows los guarda dentro del paquete) y se
  borran al desinstalar desde la tienda.

## 1. Cuenta de desarrollador (una vez, lo haces tú)

1. Entra en https://partner.microsoft.com/dashboard/registration con tu cuenta de Microsoft y elige **cuenta
   individual**. Para particulares el registro es gratis.
2. Rellena tus datos y verifica tu identidad (la tienda lo pide; puede tardar unos días).

## 2. Reservar el nombre y copiar la identidad

1. En Partner Center: **Apps y juegos › Nueva aplicación** y reserva el nombre **Jayth**.
2. En la app: **Gestión de productos › Identidad del producto**. Copia estos tres datos:
   - `Package/Identity/Name` (algo como `12345JeisonTuiran.Jayth`);
   - `Package/Identity/Publisher` (empieza por `CN=`);
   - `Package/Properties/PublisherDisplayName`.
3. En GitHub: **Settings › Secrets and variables › Actions › Variables › New repository variable**, crea tres variables
   (no son secretos):
   - `STORE_IDENTITY_NAME` con el primero;
   - `STORE_PUBLISHER` con el segundo;
   - `STORE_PUBLISHER_NAME` con el tercero.

Desde la siguiente versión, la compilación de Windows deja el paquete en **Actions › (la ejecución de esa versión) ›
Artifacts › tienda-msix**.

## 3. Primer envío

En Partner Center, **Envíos › Iniciar envío**:

- **Precios y disponibilidad:** gratis, todos los mercados.
- **Propiedades:**
  - categoría *Herramientas de desarrollo* (o *Productividad*);
  - URL de privacidad: https://github.com/Json-Tuiran/jayth.ai/blob/main/PRIVACY.md;
  - sitio web: https://json-tuiran.github.io/jayth.ai/;
  - contacto de soporte: https://github.com/Json-Tuiran/jayth.ai/issues.
- **Clasificación por edades:** el cuestionario. Jayth no tiene contenido propio, pero el modelo genera texto y puede
  usar la web, así que responde que hay contenido generado por los usuarios o la IA y acceso sin filtrar a internet.
- **Paquetes:** sube el `.msix` del artefacto «tienda-msix».
- **Capacidad restringida `runFullTrust`:** la tienda pregunta por qué. Texto sugerido:
  > Jayth is a desktop AI agent built with Python and Qt. It runs a local language model engine (llama.cpp) as a child
  > process, reads and writes the user's files, and controls other applications (UI Automation, mouse and keyboard)
  > only when the user asks and approves each action. These features require a full-trust desktop process.
- **Ficha de la tienda** (en español y en inglés): textos de abajo, y como capturas las de `docs/img`:
  `chat_*.png`, `lienzo_*.png`, `code_*.png` y `navegador_*.png` (1280×720).

### Ficha en español

**Descripción breve:** Tu agente de IA local: programa, crea documentos y usa tus programas y la web. Sin internet y
sin tarjeta gráfica. Tú apruebas cada acción.

**Descripción:**

> Jayth convierte un modelo de IA que corre en tu ordenador en un agente que hace el trabajo: programa y comprueba su
> código, crea documentos de Word, Excel, PowerPoint y PDF, usa tus programas y navega por la web a la vista. Después de
> descargar el modelo funciona sin internet, y va en portátiles sin tarjeta gráfica.
>
> Tú tienes el control: apruebas cada acción o le das vía libre, y lo delicado (borrar, instalar programas, actuar en tus
> cuentas) siempre te lo pregunta. Si una web intenta darle órdenes, te avisa.
>
> - Modelos GGUF gratis desde la propia app, o los tuyos, Ollama, LM Studio, Claude o Gemini.
> - Lienzo para ver, editar y exportar las webs y documentos que crea.
> - Jayth Code para proyectos: explorador, editor y terminal.
> - Habilidades, asistentes y conexión con Gmail, Drive, Notion y más.
> - En 8 idiomas. Sin cuentas ni estadísticas de uso. Software libre (GPL-3.0).
>
> La rapidez del agente depende de tu equipo: el modelo trabaja con tu procesador o tu tarjeta gráfica. Sin gráfica
> funciona con modelos pequeños y más despacio (mínimo: 4 núcleos, 8 GB de RAM y unos 10 GB libres); con una gráfica de
> 8 GB o más va varias veces más rápido y admite modelos más capaces. También puedes usar un modelo por API.

**Funciones destacadas:** Agente de IA que funciona sin internet · Programa, ejecuta y comprueba su trabajo · Crea
documentos de Word, Excel, PowerPoint y PDF · Usa tus programas y la web · Tú apruebas cada acción · Software libre, sin
cuentas.

**Palabras clave:** agente de IA, IA local, LLM, GGUF, llama.cpp, asistente de programación, sin internet.

### Ficha en inglés

**Short description:** Your local AI agent: it codes, creates documents, and uses your apps and the web. Offline and
without a graphics card. You approve every action.

**Description:**

> Jayth turns an AI model running on your computer into an agent that does the work: it writes and checks code,
> creates Word, Excel, PowerPoint and PDF documents, uses your apps and browses the web in plain sight. Once the model is
> downloaded it works offline, and it runs on laptops without a graphics card.
>
> You're in charge: approve every action or give it free rein, and sensitive actions (deleting, installing software,
> acting on your accounts) always ask first. If a website tries to give it orders, it warns you.
>
> - Free GGUF models from inside the app, or your own, Ollama, LM Studio, Claude or Gemini.
> - A canvas to see, edit and export the websites and documents it creates.
> - Jayth Code for projects: explorer, editor and terminal.
> - Skills, assistants and connections to Gmail, Drive, Notion and more.
> - In 8 languages. No accounts, no usage tracking. Free software (GPL-3.0).
>
> How fast the agent is depends on your computer: the model runs on your processor or graphics card. Without a GPU it
> works with small models and more slowly (minimum: 4 cores, 8 GB of RAM and about 10 GB free); with a graphics card of
> 8 GB or more it's several times faster and can run more capable models. You can also use an API model.

**Features:** AI agent that works offline · Writes, runs and checks code · Creates Word, Excel, PowerPoint and PDF
documents · Uses your apps and the web · You approve every action · Free software, no accounts.

**Keywords:** AI agent, local AI, LLM, GGUF, llama.cpp, coding assistant, offline.

### Requisitos del sistema (Propiedades › Requisitos del sistema)

| | Mínimo | Recomendado |
|---|---|---|
| Memoria | 8 GB | 16 GB |
| Memoria de vídeo | — (funciona sin gráfica) | 8 GB |
| Procesador | 4 núcleos, x64 | — |
| Teclado y ratón | Sí | Sí |
| Micrófono | No (opcional, para dictar) | — |

En «Notas adicionales sobre requisitos» (es/en): «La rapidez depende del equipo: sin tarjeta gráfica funciona con
modelos pequeños y más despacio; con una gráfica de 8 GB o más, o con un modelo por API, va varias veces más rápido.» /
«Speed depends on the hardware: without a graphics card it works with small models and more slowly; with an 8 GB+
graphics card, or with an API model, it's several times faster.»

## 4. Versiones siguientes

Con cada versión nueva: descarga el artefacto «tienda-msix» de esa ejecución y, en Partner Center, **Actualizar** el
envío con el paquete nuevo. La certificación suele tardar de unas horas a unos días.

## Lo que puede preguntar la certificación

- **El motor que descarga.** En el primer arranque Jayth descarga llama.cpp (la versión para tu procesador o tu gráfica)
  desde sus versiones oficiales en GitHub. Si la tienda lo pone en duda, la alternativa es incluir el motor para
  procesador dentro del paquete y descargar solo las versiones para gráfica.
- **Contenido generado por IA.** Puede pedir cómo informa un usuario de un problema: desde la app, menú del perfil ›
  *Informar de un error…*, o en las incidencias de GitHub.

Ninguna de las dos está comprobada todavía: lo sabremos con el primer envío.
