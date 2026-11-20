# Política de firma del código (Code signing policy)

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

(Firma de código gratuita proporcionada por SignPath.io, certificado de SignPath Foundation.)

## Qué se firma

- Los instaladores y paquetes de Windows de cada versión publicada en
  [Releases](https://github.com/Json-Tuiran/jayth.ai/releases): el instalador `Jayth-Setup-<versión>-x64.exe` y el
  programa `Jayth.exe` del paquete portátil.
- Solo se firma lo que compila GitHub Actions a partir del código de este repositorio
  ([`.github/workflows/release.yml`](.github/workflows/release.yml)). Nada se compila ni se firma a mano.
- Cada versión firmada la aprueba a mano su responsable antes de firmarse.

## Equipo y funciones

| Función | Personas |
|---|---|
| Autor, colaboradores con permiso de escritura y revisores | [Json-Tuiran](https://github.com/Json-Tuiran) (Ing. Jeison Tuiran) |
| Aprobación de cada firma | [Json-Tuiran](https://github.com/Json-Tuiran) (Ing. Jeison Tuiran) |

Todas las personas del equipo usan autenticación en dos pasos en GitHub y en SignPath.

## Privacidad

Jayth funciona en tu equipo y **no envía telemetría ni datos de uso**. Tus conversaciones, archivos y modelos se quedan en tu equipo.

Por su cuenta, solo se conecta a internet para comprobar si hay versiones nuevas, y las dos cosas se pueden desactivar en
*Ajustes → Acerca de*:
- de Jayth: consulta la lista de versiones de este repositorio en GitHub;
- de tus modelos: busca en Hugging Face versiones más recientes de los modelos que tienes instalados.

Todo lo demás ocurre solo cuando el usuario lo pide o lo aprueba:
- descargar el motor (llama.cpp, desde GitHub) y los modelos (desde Hugging Face);
- que el agente busque o lea páginas web, use el navegador integrado o descargue archivos;
- usar un modelo en la nube de un proveedor que el propio usuario configure con su clave;
- enviar comentarios (se abre una incidencia en GitHub con un texto que el usuario revisa antes de enviarlo).

Este programa no transfiere ninguna información a otros sistemas de la red salvo en los casos anteriores, que se
producen a petición o con la aprobación del usuario o de la persona que lo instala o lo usa.

---

## English summary

**Code signing policy.** Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).

- **What is signed:** the Windows installer (`Jayth-Setup-<version>-x64.exe`) and `Jayth.exe` inside the portable package
  of each release published on [GitHub Releases](https://github.com/Json-Tuiran/jayth.ai/releases). Binaries are built
  only by GitHub Actions from the source code in this repository
  ([`.github/workflows/release.yml`](.github/workflows/release.yml)); nothing is built or signed manually.
- **Team roles:** committers and reviewers: [Json-Tuiran](https://github.com/Json-Tuiran) (Ing. Jeison Tuiran).
  Approvers: [Json-Tuiran](https://github.com/Json-Tuiran) (Ing. Jeison Tuiran). Every signing request is approved
  manually. All team members use multi-factor authentication on GitHub and SignPath.
- **License:** [GNU GPL-3.0](LICENSE) for all components; no commercial dual-licensing.

**Privacy policy.** Jayth runs on the user's computer and collects no telemetry or usage data. On its own it only checks
for new versions of Jayth (GitHub releases of this repository) and of the user's installed models (Hugging Face); both
checks can be turned off in *Settings → About*. Everything else (downloading the engine and models, web search and
browsing by the agent, cloud model providers configured by the user, sending feedback) happens only when the user
requests or approves it. This program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it, except for the optional update checks described above.
