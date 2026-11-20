# Política de firma del código

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
