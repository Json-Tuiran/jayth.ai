# Primeros pasos con Jayth

Una guía corta para empezar, sin conocimientos técnicos. *English: [getting-started.md](getting-started.md).*

## 1. Qué es

Jayth es un asistente de IA que **trabaja en tu ordenador**: no solo responde, también hace cosas. Por ejemplo:

- «Ordena las fotos de mi carpeta Descargas por fecha.»
- «Hazme un Word con el informe de ventas de este Excel.»
- «Busca en internet el mejor precio de este portátil.»
- «Crea una página web para mi negocio y enséñamela.»

Puede usar una IA **local** (en tu ordenador, gratis y sin internet) o una IA **por internet** (Claude, Gemini, ChatGPT…),
más rápida y lista, pero de pago y enviando la conversación a ese servicio.

## 2. Instalar

1. Descarga el instalador de tu sistema desde la [página de descargas](https://github.com/Json-Tuiran/jayth.ai/releases/latest).
2. **Windows:** ábrelo. Si sale «Windows protegió su PC», pulsa **Más información → Ejecutar de todas formas** (sale
   porque el instalador aún no está firmado; es normal en programas nuevos).
   **Mac:** abre el `.dmg`, arrastra Jayth a Aplicaciones y, la primera vez, clic derecho sobre Jayth → **Abrir**.
3. Al abrir Jayth por primera vez, un **asistente** mira tu ordenador y te propone una IA que quepa en él. Acepta y
   espera a que se descargue (unos minutos; solo la primera vez).

## 3. Elegir la IA

**Lo rápido que trabaje depende de tu ordenador.** La IA piensa con tu procesador o tu tarjeta gráfica: sin gráfica
funciona, pero más despacio y con modelos pequeños; con una gráfica o un Mac con chip Apple va varias veces más rápido.
Como mínimo: un procesador de 4 núcleos (de 2018 o posterior), 8 GB de memoria y unos 10 GB libres en el disco.

- **Tu ordenador tiene poca memoria (8 GB) o no tiene tarjeta gráfica:** usa un modelo pequeño (el asistente lo elige
  solo). Responderá despacio: es normal. Si quieres rapidez, añade una IA por internet en **Tu perfil → Modelos por API…**
  (necesitas una clave de pago de ese servicio).
- **16 GB o más, o una tarjeta gráfica:** puedes usar modelos más grandes y listos (**Tu perfil → Modelos**).

Puedes cambiar de IA cuando quieras con el **chip del modelo**, junto al cuadro donde escribes.

## 4. Pedirle cosas

Escribe lo que quieres como se lo dirías a una persona y pulsa **Enter**. Verás cada paso que da: qué archivo lee, qué
comando ejecuta, qué crea. Si algo no te convence, pulsa **Detener**.

Consejos:

- **Sé concreto:** «haz una lista de la compra para 4 personas en un Excel» funciona mejor que «ayúdame con la compra».
- **Arrastra archivos** al chat (o usa **+**) para que trabaje con ellos.
- Lo que crea (páginas, documentos, Word, Excel, PDF…) puedes **verlo en el lienzo**, a la derecha, con **Ver**, y
  guardar una copia con **Descargar una copia…**.

## 5. Permisos: quién decide

Junto al cuadro de mensaje está el **chip de permisos**:

- **Preguntar** (recomendado al principio): Jayth te pide permiso antes de cambiar nada. Pulsas **Permitir** o **Denegar**.
- **Automático:** trabaja sin preguntar, salvo en lo delicado (borrar, instalar programas, tocar el sistema…), que
  siempre te pregunta.

Si el agente lee una página web que intenta darle órdenes escondidas, Jayth te avisa y te pide permiso para todo lo que
siga en esa respuesta.

## 6. Si algo va mal

- **Va muy lento:** con IA local en un portátil es normal. Prueba un modelo más pequeño o una IA por internet.
- **Se equivocó:** debajo de cada respuesta está **Regenerar respuesta**, y en la tarjeta de cambios, **Deshacer todo**
  devuelve tus archivos a como estaban.
- **Un error de Jayth:** **Tu perfil → Informar de un error…** (ves exactamente qué se envía antes de enviarlo).
- **Dudas sobre cómo se hace algo en Jayth:** pregúntaselo al propio Jayth («¿cómo cambio el idioma?»): consulta su guía.

## 7. Tus datos

Con una IA local, tus archivos y conversaciones no salen del ordenador. Con una IA por internet, la conversación se
envía a ese servicio. Las claves se guardan protegidas en tu ordenador. Más detalles en [SECURITY.md](../SECURITY.md).
