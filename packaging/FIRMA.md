# Firmar los paquetes de Windows con SignPath (gratis para código abierto)

Mientras no se configure, los paquetes salen **sin firmar** y Windows muestra «Editor desconocido». La compilación ya
está preparada: en cuanto existan las claves de abajo, cada versión se firma sola (tras tu aprobación en SignPath).

## 1. Solicitarlo (lo haces tú, una vez)

1. Activa la **verificación en dos pasos** en tu cuenta de GitHub (SignPath la exige a todo el equipo).
2. Entra en <https://signpath.org/> y rellena la solicitud para proyectos de código abierto con:
   - Proyecto: **Jayth** · repositorio <https://github.com/Json-Tuiran/jayth.ai>
   - Licencia: **GPL-3.0** (archivo `LICENSE` del repositorio)
   - Política de firma: [`CODE_SIGNING_POLICY.md`](../CODE_SIGNING_POLICY.md)
   - Compilación: GitHub Actions ([`.github/workflows/release.yml`](../.github/workflows/release.yml))
3. Espera la aprobación (la revisa SignPath Foundation; puede tardar unos días o semanas).

### Respuestas preparadas para el formulario (<https://signpath.org/apply>)

Tus datos personales (nombre, correo), el reCAPTCHA y las casillas de consentimiento los rellenas tú.

| Campo | Respuesta |
|---|---|
| Project Name | `Jayth` |
| Repository URL | `https://github.com/Json-Tuiran/jayth.ai` |
| Homepage URL | `https://github.com/Json-Tuiran/jayth.ai` |
| Download URL | `https://github.com/Json-Tuiran/jayth.ai#descargar-e-instalar` (el README menciona a SignPath Foundation, como piden) |
| Privacy Policy URL | `https://github.com/Json-Tuiran/jayth.ai/blob/main/PRIVACY.md` |
| Tagline | `Open-source desktop AI agent that runs local models (llama.cpp) and works on your computer: files, commands, apps, web and documents.` |
| Category | la más cercana a «Developer tools» o «Productivity» |
| Description | `Jayth is a free, open-source (GPL-3.0) desktop app for Windows, macOS and Linux that turns a local AI model (GGUF via llama.cpp) or an API model into an agent that works on the user's computer: it writes and edits files, runs commands, uses other programs through accessibility APIs, browses the web with its own browser, and reads and creates Word, Excel, PowerPoint and PDF documents. Every action is visible and can require the user's approval; it works offline with local models.` |
| Reputation | enlaces honestos: el repositorio, sus Releases (`https://github.com/Json-Tuiran/jayth.ai/releases`), [`SECURITY.md`](../SECURITY.md) y la ficha de winget si ya está aceptada. Es un proyecto nuevo: dilo tal cual. |
| Maintainer Type | individual |
| Build System | GitHub Actions |

## 2. Configurar el proyecto en SignPath (cuando te aprueben)

1. Crea (o revisa) el proyecto con el *slug* **`jayth`**.
2. En *Trusted build systems*, conecta **GitHub.com** y añade el repositorio.
3. En *Artifact configurations*, crea una con el contenido de
   [`packaging/signpath-artifact-configuration.xml`](signpath-artifact-configuration.xml) y márcala como predeterminada
   (o anota su *slug*).
4. En *Signing policies*, usa la de publicación con el *slug* **`release-signing`** y exige **aprobación manual**
   (así nada se firma sin que lo apruebes tú).
5. Crea un usuario de CI y genera su **API token**.

## 3. Darle las claves a GitHub

En el repositorio: *Settings → Secrets and variables → Actions*.

| Tipo | Nombre | Valor |
|---|---|---|
| Secret | `SIGNPATH_API_TOKEN` | el API token del usuario de CI de SignPath |
| Variable | `SIGNPATH_ORGANIZATION_ID` | el ID de tu organización en SignPath |
| Variable (opcional) | `SIGNPATH_PROJECT_SLUG` | si tu proyecto no se llama `jayth` |
| Variable (opcional) | `SIGNPATH_SIGNING_POLICY_SLUG` | si tu política no se llama `release-signing` |
| Variable (opcional) | `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | si tu configuración de artefacto no es `initial` |

## 4. Publicar una versión firmada

Igual que siempre: sube la etiqueta `vX.Y.Z`. La compilación de Windows sube el paquete sin firmar a SignPath, tú
apruebas la firma en SignPath, y la compilación sigue con los archivos ya firmados. En el registro del paso «Usar los
paquetes firmados» se ve el resultado (`Valid` y el certificado de SignPath Foundation).

**A tener en cuenta**
- El firmante que verá Windows será **SignPath Foundation**; tu nombre aparece en la licencia, el README, «Acerca de» y
  las propiedades del programa.
- Al principio, Windows puede seguir avisando un tiempo: la reputación de SmartScreen crece con las descargas.
- macOS es aparte: para que el Mac no avise hace falta el programa de desarrolladores de Apple (de pago).
