# Cómo contribuir a Jayth

**Español** · [English](#contributing-to-jayth)

Gracias por tu interés. Toda ayuda cuenta, también la que no es código:

- **Informar de un error o proponer una idea:** desde la app (menú del perfil › **Informar de un error…** o **Enviar
  comentarios…**) o abriendo una [incidencia en GitHub](https://github.com/Json-Tuiran/jayth.ai/issues).
- **Traducciones:** la interfaz está en 8 idiomas; si ves una frase rara en el tuyo, dínoslo.
- **Habilidades:** si creas una habilidad (`SKILL.md`) útil para Jayth, compártela.
- **Fallos de seguridad:** no los publiques; sigue [SECURITY.md](SECURITY.md).

## Antes de enviar código

1. **Acuerdo de colaborador:** la primera vez que propongas un cambio, un bot te pedirá aceptar el
   [CLA](CLA.md). Basta con comentar en tu propuesta: `He leído el CLA y lo acepto / I have read the CLA and I agree`.
2. **Licencia:** tus cambios se publican con la licencia [GPL-3.0](LICENSE) del proyecto. Respeta la
   [política de marca](MARCA.md).
3. **Idioma:** el código, los comentarios y los mensajes de commit van en español, como el resto del repositorio. Las
   propuestas y las conversaciones pueden ser en español o en inglés.

## Cómo trabajar

- **Arrancar desde el código:** `pip install -r requirements.txt` y `python app.py` (detalles en el README, «Desde el
  código»).
- **Textos de la interfaz:** envuélvelos con `tr()`. Después, `python tools_i18n/catalogo.py pendientes <idioma>` muestra
  lo que falta traducir y `python tools_i18n/catalogo.py revisar` tiene que terminar sin faltas.
- **Ajustes y menús nuevos:** añádelos a las 8 guías de `assets/guia/` (el agente las consulta para explicar la app);
  `python tools_i18n/revisar_guia.py` tiene que dar 0 problemas.
- **Pruebas:** `python -m unittest discover -s tests -v` antes de enviar. Las pruebas no deben abrir ventanas, mover
  el ratón ni capturar la pantalla real.
- **Propuestas pequeñas y con un solo tema:** son más fáciles de revisar. Explica qué cambia y cómo lo probaste.

---

# Contributing to Jayth

[Español](#cómo-contribuir-a-jayth) · **English**

Thank you for your interest. Every kind of help counts, not just code:

- **Report a bug or suggest an idea:** from the app (profile menu › **Report a bug…** or **Send feedback…**) or by opening
  a [GitHub issue](https://github.com/Json-Tuiran/jayth.ai/issues).
- **Translations:** the interface is in 8 languages; if something reads oddly in yours, let us know.
- **Skills:** if you write a useful skill (`SKILL.md`) for Jayth, share it.
- **Security issues:** don't post them publicly; follow [SECURITY.md](SECURITY.md).

## Before you send code

1. **Contributor agreement:** on your first pull request, a bot will ask you to accept the [CLA](CLA.md). Just comment on
   your pull request: `He leído el CLA y lo acepto / I have read the CLA and I agree`.
2. **License:** your changes are published under the project's [GPL-3.0](LICENSE) license. Please respect the
   [trademark policy](MARCA.md).
3. **Language:** code, comments and commit messages are in Spanish, like the rest of the repository. Pull requests and
   discussions can be in Spanish or English.

## How to work

- **Run from source:** `pip install -r requirements.txt` and `python app.py` (details in the README, "From source").
- **Interface text:** wrap it in `tr()`. Then `python tools_i18n/catalogo.py pendientes <language>` lists what still
  needs translating, and `python tools_i18n/catalogo.py revisar` must finish with nothing missing.
- **New settings and menus:** add them to the 8 guides in `assets/guia/` (the agent reads them to explain the app);
  `python tools_i18n/revisar_guia.py` must report 0 problems.
- **Tests:** run `python -m unittest discover -s tests -v` before sending. Tests must not open windows, move the mouse
  or capture the real screen.
- **Small, single-topic pull requests:** they are easier to review. Explain what changes and how you tested it.
