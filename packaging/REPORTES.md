# Comentarios e informes de los usuarios

Los usuarios envían errores, ideas, preguntas e informes de errores inesperados desde Jayth (menú del perfil › **Enviar
comentarios…**, **Informar de un error…**, el botón bajo cada respuesta y el aviso tras un error inesperado). Antes de
enviar ven todo el texto y pueden quitar lo que no quieran compartir. Nada se envía sin su clic.

```
Jayth ──(POST /reporte, sin claves)──▶ puente en Cloudflare ──(clave de GitHub)──▶ repositorio PRIVADO jayth-reportes
                                        packaging/reportes/worker.js                  (aquí lo ves y lo gestionas tú)
```

- La clave de GitHub vive solo en el puente, como secreto. Nunca va dentro de Jayth, donde cualquiera podría sacarla.
- El puente frena los envíos repetidos (5 cada 10 minutos por dirección, 60 por hora en total), rechaza lo que no
  viene de Jayth y neutraliza las menciones (@usuario) para que nadie reciba avisos por un texto pegado.
- Sin puente configurado, Jayth funciona como antes: abre una incidencia pública en GitHub o deja copiar el texto.
- Coste: nada. El plan gratuito de Cloudflare Workers admite 100 000 peticiones al día.

## Puesta en marcha (una sola vez)

### 1. Repositorio privado

En GitHub: **New repository** → nombre `jayth-reportes` → **Private** → **Create repository**.
Las etiquetas (bug, enhancement, question, «desde Jayth», «cierre inesperado») se crean solas con el primer informe.

### 2. Clave de GitHub solo para ese repositorio

GitHub › **Settings** › **Developer settings** › **Personal access tokens** › **Fine-grained tokens** › **Generate new
token**:

- Nombre: `Puente de comentarios de Jayth`. Caducidad: 1 año (apúntate renovarla).
- **Repository access** › **Only select repositories** › `jayth-reportes`.
- **Permissions** › **Repository permissions** › **Issues: Read and write** (Metadata: Read se añade solo).
- **Generate token** y cópiala. Solo se pega en el paso 3; no la compartas con nadie.

### 3. El puente en Cloudflare (sin instalar nada)

1. Crea una cuenta gratuita en https://dash.cloudflare.com/sign-up.
2. **Workers & Pages** › **Create** › **Create Worker** › nombre `jayth-reportes` › **Deploy**.
3. **Edit code**: borra el ejemplo, pega todo el contenido de `packaging/reportes/worker.js` y pulsa **Deploy**.
4. Del Worker, **Settings** › **Variables and Secrets** › **Add**:
   - Tipo **Text**, nombre `REPO`, valor `Json-Tuiran/jayth-reportes`.
   - Tipo **Secret**, nombre `GITHUB_TOKEN`, valor: la clave del paso 2.
   - **Deploy** para guardar.
5. Abre la dirección del Worker (algo como `https://jayth-reportes.TU-SUBDOMINIO.workers.dev`): debe responder
   `{"ok":true,"servicio":"jayth-reportes"}`.

Con la consola, en vez del panel: `cd packaging/reportes`, `npx wrangler login`, `npx wrangler deploy` y
`npx wrangler secret put GITHUB_TOKEN`.

### 4. Conectar Jayth al puente

Pon la dirección del Worker en `REPORT_URL` (`jayth/feedback.py`), sin barra final, y publica una versión. La actual es
`https://jayth-reportes.jsontuiran.workers.dev` (puesta en marcha el 21/11/2026; la clave caduca el 20/11/2027). Para
probar antes sin tocar el código: variable de entorno `JAYTH_REPORT_URL`.

## Dónde ves todo y cómo gestionarlo

- **Todo en un sitio:** https://github.com/Json-Tuiran/jayth-reportes/issues. Cada informe trae el tipo, la versión de
  Jayth, el sistema, el idioma y la fecha, además del texto del usuario.
- **Avisos:** en el repositorio, **Watch** › **All Activity**: te llega un correo por cada informe. Con la app GitHub
  del móvil también recibes avisos.
- **Filtrar:** por etiqueta: `label:bug`, `label:enhancement`, `label:question`, `label:"cierre inesperado"`.
- **Responder:** los usuarios no tienen cuenta en ese repositorio y no ven tus respuestas. Si dejaron un correo en el
  texto, contesta por correo; si no, el comentario te sirve como nota interna.
- **Cerrar al corregir:** en el commit del arreglo en jayth.ai, escribe `Corrige Json-Tuiran/jayth-reportes#12`, o
  ciérrala a mano con un comentario que diga en qué versión quedó.
- **Hacerlo público:** si un error interesa a todos, **Transfer issue** a `jayth.ai`. Antes, revisa que no lleve datos
  personales.
- **Cada usuario** guarda en su equipo la lista de lo que envió, con su número (`data/informes_enviados.json`).

## Si algo falla

- **Jayth dice «No hay conexión con el servicio de comentarios»:** el Worker está caído o la dirección es incorrecta.
  Ábrela en el navegador; debe responder `ok`.
- **«No se pudo guardar el informe»:** la clave caducó o no tiene permiso **Issues: Read and write** sobre el
  repositorio. Crea otra y cámbiala en **Variables and Secrets**.
- **Llega basura:** en Cloudflare, **Security** › **WAF** › una regla de límite de peticiones para la ruta `/reporte`.
  También puedes bajar los límites al principio de `worker.js`.
