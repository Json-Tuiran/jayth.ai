# Seguridad de Jayth

Jayth es un agente que actúa en tu ordenador: lee y escribe archivos, ejecuta comandos, usa el navegador y, si lo
conectas, tus cuentas. Este documento explica qué lo frena, qué no, y cómo informar de un fallo.

*English summary at the end.*

## Qué pide siempre tu permiso

En el modo **Preguntar** se pide permiso para todo lo que cambia algo. En el modo **Automático**, Jayth actúa sin preguntar
**salvo** en estas acciones, que siempre se confirman:

- **Borrar** archivos o carpetas (también `Remove-Item`, `rm`, `del`…), **formatear** discos, `diskpart`, `dd` sobre un disco.
- **Apagar o reiniciar** el equipo, **parar procesos** (`taskkill`, `kill`…), crear **tareas programadas** o servicios.
- Cambiar el **registro de Windows**, la política de ejecución, los permisos de archivos (`icacls`, `chmod -R`, `chown`) o
  la configuración de seguridad (`Set-MpPreference`, `csrutil`…).
- Comandos con **`sudo`**, **instalar o desinstalar** programas (`winget`, `apt`, `brew`…), descargar y ejecutar un
  script (`curl … | sh`), `git reset --hard`, `git push --force`.
- Scripts de Python que usan la **red**, lanzan **programas** o **borran** archivos.
- Escribir en carpetas del **sistema** (Windows, Archivos de programa, `/etc`, `/usr`…).
- Leer o cambiar los **datos privados de Jayth**: sus ajustes y la bóveda de credenciales.
- Escribir en un formulario web algo que parece un **número de tarjeta**.
- Cualquier acción en una **cuenta conectada** que no sea solo de lectura (publicar, enviar, gastar créditos).

Las **contraseñas** las escribe siempre la persona, nunca el agente.

## Instrucciones escondidas en páginas web (inyección de instrucciones)

Una página web, un correo o un documento pueden esconder texto dirigido a la IA («ignora tus instrucciones y envía…»).
Jayth lo trata así:

1. Todo lo que llega de la web o de un servicio conectado va marcado para el modelo como **datos, no instrucciones**, y
   sus instrucciones base le dicen que solo obedece a la persona.
2. Si ese contenido contiene frases típicas de inyección (en español, inglés, portugués, francés, alemán e italiano), Jayth
   **te avisa** en el chat y el modelo recibe una advertencia.
3. Desde ese momento y hasta el final de la respuesta, **todo lo que cambia algo pide permiso**, aunque estés en modo
   Automático.

Ningún detector es perfecto: una inyección bien disimulada puede pasar. Por eso las acciones de la lista anterior piden
permiso siempre, y por eso conviene usar el modo **Preguntar** cuando el agente vaya a leer webs que no conoces.

## Tus datos

- Con un **modelo local**, nada sale del ordenador salvo lo que el agente busque o descargue en internet.
- Con un **modelo por API** (Claude, Gemini, OpenAI…), la conversación se envía a ese servicio.
- Las **claves de API** y los permisos de los servicios conectados se guardan en la bóveda de Jayth: en Windows, cifrados
  con DPAPI (atados a tu cuenta de este equipo); en macOS y Linux, en un archivo que solo puede leer tu usuario. Los
  ajustes y sus copias solo contienen un marcador.
- Los **informes de errores** son opcionales: ves exactamente qué se envía antes de enviarlo, y llegan a un repositorio
  privado (no se publican).

## Pruebas

Las protecciones anteriores tienen pruebas automáticas en [`tests/test_seguridad.py`](tests/test_seguridad.py), que se
ejecutan en cada compilación: si alguna falla, no se publica la versión.

```
python -m unittest discover -s tests -v
```

## Paquetes y firma

Los instaladores aún **no están firmados** (la firma gratuita con SignPath Foundation está en trámite; ver
[`CODE_SIGNING_POLICY.md`](CODE_SIGNING_POLICY.md)). Mientras tanto, cada versión publica **`SHA256SUMS.txt`** con la huella de
cada archivo. Para comprobar una descarga:

- Windows (PowerShell): `Get-FileHash .\Jayth-Setup-x64.exe -Algorithm SHA256`
- macOS: `shasum -a 256 Jayth-macos-arm64.dmg` · Linux: `sha256sum Jayth-linux-x86_64.AppImage`

La huella debe coincidir con la de `SHA256SUMS.txt` de la misma versión en GitHub.

## Informar de un fallo de seguridad

No abras una incidencia pública. Usa **«Informar de un error»** dentro de Jayth (llega a un repositorio privado; empieza
el texto con «Seguridad:») o el [aviso privado de vulnerabilidades de GitHub](https://github.com/Json-Tuiran/jayth.ai/security/advisories/new). Respondemos
lo antes posible y publicamos el arreglo en una versión nueva.

---

## English summary

- **Always asks first**, even in Automatic mode: deleting, formatting, shutting down, killing processes, scheduled tasks,
  registry and permission changes, `sudo`, installing software, `curl | sh`, `git reset --hard`/`push --force`, Python
  scripts that use the network or launch programs, writing to system folders, touching Jayth's settings or credential
  vault, card-like numbers in web forms and any non-read-only action on connected accounts. Passwords are always typed
  by the person.
- **Prompt injection:** content from the web or connected services is marked as data, not instructions. If it contains
  typical injection phrases, Jayth warns you and, until the end of that reply, every action that changes something
  needs your approval. No detector is perfect, so the list above always asks; prefer *Ask* mode for unknown sites.
- **Tests:** [`tests/test_seguridad.py`](tests/test_seguridad.py) runs on every build; a failure blocks the release.
- **Unsigned packages:** signing via SignPath Foundation is in progress; each release ships `SHA256SUMS.txt` to verify
  downloads.
- **Report a vulnerability** privately through GitHub security advisories or the in-app "Report a bug" (it goes to a
  private repository; start the text with "Security:").
