# Privacidad en Jayth

Jayth es un programa de escritorio. **No tiene cuentas, no tiene servidor propio que guarde tus datos y no envía
estadísticas de uso.** Tus conversaciones, archivos, memoria y ajustes se quedan en tu ordenador.

*English summary at the end.*

## Qué sale de tu ordenador, y solo cuando

| Cuándo | A dónde | Qué se envía |
|---|---|---|
| Al buscar actualizaciones (se puede desactivar en Ajustes) | GitHub | La petición de la última versión publicada. Nada tuyo. |
| Al descargar el motor o un modelo | GitHub y Hugging Face | La petición del archivo. Nada tuyo. |
| Si usas un **modelo por API** (Claude, OpenAI, Gemini…) | Ese servicio | La conversación, los archivos que el agente lea para responder y las capturas que haga. Se rige por la política de privacidad de ese servicio. |
| Si el agente **busca en internet o abre webs** | DuckDuckGo, Bing, Wikipedia (o Brave, si pones su clave) y las webs que visite | La búsqueda y las peticiones a esas webs, como cualquier navegador. |
| Si **conectas un servicio** (Gmail, Drive, Notion…) | Ese servicio | Lo que el agente lea o haga allí, con el permiso que concediste al conectarlo. |
| Si **envías un comentario o un informe de error** | Un repositorio privado del autor (a través de un servicio de Cloudflare) | Solo el texto que ves antes de enviarlo. Nunca se envía nada sin tu clic. |

Con un **modelo local** y sin pedir búsquedas en internet, Jayth funciona sin conexión y nada de tu trabajo sale del
equipo.

## Lo que se guarda en tu ordenador

En la carpeta de datos de Jayth (ver «Dónde se guarda todo» en el README): conversaciones, memoria, ajustes, modelos y
las claves de los servicios. Las claves van en la bóveda de Jayth (cifradas con DPAPI en Windows; en macOS y Linux, en
un archivo que solo puede leer tu usuario). Puedes borrar todo eso cuando quieras: desinstalar Jayth no lo borra, para que
no pierdas nada por accidente.

## Contacto

Para cualquier duda sobre privacidad: «Hacer una pregunta» dentro de Jayth o una incidencia en
[GitHub](https://github.com/Json-Tuiran/jayth.ai/issues).

---

## English summary

Jayth is a desktop app with **no accounts, no server storing your data and no usage analytics.** Your conversations,
files, memory and settings stay on your computer. Data leaves it only when you use an API model (sent to that provider),
when the agent searches or browses the web, when you connect a service, when it checks for updates or downloads models
(GitHub, Hugging Face; nothing personal), or when you send feedback or a bug report (only the text you see, to the
author's private repository, never without your click). With a local model and no web searches, nothing about your
work leaves the computer. Keys are stored in Jayth's vault (DPAPI-encrypted on Windows, a user-only file on macOS/Linux).
