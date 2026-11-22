# Guida di Jayth

Questa guida descrive la versione installata di Jayth: cosa fa ogni parte, dove si trova e come si usa. I nomi di
pulsanti e menu sono quelli che si vedono nell'interfaccia (in questa lingua). I dati di questo computer (versione,
modello attivo, cartelle, scorciatoie…) vengono aggiunti a parte, presi dall'app stessa al momento della consultazione.

## Cos'è Jayth

Jayth è un'applicazione desktop per Windows, macOS e Linux che trasforma un modello di IA locale (formato GGUF, con
llama.cpp) in un agente che lavora sul computer dell'utente: programma, crea e modifica file, esegue comandi, usa altri
programmi, naviga sul web con il proprio browser e legge e crea documenti Word, Excel, PowerPoint e PDF. Tutto avviene
sul computer e funziona senza internet una volta scaricato il modello. L'utente approva ogni azione (o gli lascia campo
libero in modalità automatica). Può anche usare modelli via API (OpenAI, Claude, Gemini, Ollama…).
Creato da Ing. Jeison Tuiran. Software libero con licenza GPL-3.0. Web: https://github.com/Json-Tuiran/jayth.ai

## La finestra principale

- **Barra laterale (a sinistra):** in alto, il pulsante ≡ per nasconderla (Ctrl+Shift+S) e il selettore **Chat / Code**.
  Sotto, **Nuova conversazione** (Ctrl+N), **Cerca nelle tue conversazioni** (Ctrl+K) e la cronologia raggruppata per
  data (Oggi, Ieri, Ultimi 7 giorni…; clic su un gruppo per comprimerlo). Clic destro su una conversazione: **Rinomina**
  o **Elimina**. In fondo, il pulsante del tuo profilo (**Il tuo profilo e le impostazioni**) e, quando c'è una nuova
  versione, il pulsante di aggiornamento. Con la barra nascosta, compare passando il mouse sul bordo sinistro.
- **Barra superiore:** a sinistra, lo stato del modello (ad es. «● Pronto · locale»). A destra: **Temporanea**
  (chat temporanea), il globo (**Browser di Jayth**), **Disposizione dei pannelli**, la cartella (apre la cartella di
  lavoro) e **⋯ Altre opzioni** (Rinomina conversazione, Apri cartella di lavoro, Elimina conversazione). In Jayth Code
  compaiono anche i pulsanti di **Esplora file** (Ctrl+B), del **Terminale** (Ctrl+`) e del **Pannello
  dell'agente** (Ctrl+L).
- **Menu del tuo profilo** (in basso nella barra laterale): Impostazioni, Personalizzazione, Memoria, Assistenti e
  abilità, Attività pianificate, Modelli, Modelli via API…, Scorciatoie da tastiera, Invia feedback…, Segnala un
  errore…, Cerca aggiornamenti, Informazioni su Jayth ed Esci.
- **Area di notifica:** Mostra, Domanda rapida, Interrompi agente ed Esci.

## La casella del messaggio

- **Invio** invia; **Maiusc+Invio** va a capo. Ctrl+V incolla un'immagine.
- Pulsante **+**: Allega file o documenti…, Allega immagine…, Allega screenshot e **Usa un assistente**.
- **Microfono:** detta con la voce (la trascrizione avviene sul computer; il modello di dettatura viene scaricato la
  prima volta).
- **Chip delle autorizzazioni** (ad es. «Chiedi» o «Automatico»): cambia la modalità di autorizzazione di questa
  conversazione.
- **Chip del modello** (ad es. «Qwen3.8 27B · Basso»): cambia modello, l'**Impegno** (quanto ragiona prima di
  rispondere: Basso, Medio, Alto), scarica o aggiunge modelli, Gestisci modelli…, Modelli via API… e **Motore**
  (avvia o arresta il modello).
- L'**Impegno** fa ciò che ogni modello consente di fabbrica, e il menu stesso lo spiega. Modelli locali: quelli con
  livelli propri (gpt-oss) li usano così come sono; in quelli che possono solo attivare o disattivare il ragionamento
  (Qwen, Gemma, GLM…), «Basso» lo disattiva e «Medio» e «Alto» lo lasciano pensare fino a un limite che cresce con le
  dimensioni del modello (un 2B pensa poco; uno da centinaia di miliardi di parametri non ha limite in «Alto»), e il
  menu dice quanto ci vorrebbe sul tuo computer. Via API: ogni servizio lo riceve con la propria impostazione (Claude,
  OpenAI, Gemini, OpenRouter, DeepSeek, Kimi, GLM, Qwen…) e il suo ragionamento si vede nella chat; se un servizio non
  lo mostra, le cifre di ogni passo dicono quanto ha pensato, e se non permette di scegliere l'impegno, Jayth lo chiede
  al modello nelle sue istruzioni.
- Se il modello è spento, sopra la casella compare un avviso con **Avvia modello** (si può chiudere con la ×; ricompare
  se la situazione cambia). Se scrivi con il modello spento, Jayth lo avvia e invia il messaggio quando è pronto.
- Mentre l'agente lavora, il pulsante di invio diventa **Interrompi**.

## Modalità di autorizzazione

Si cambiano nel chip delle autorizzazioni della casella del messaggio (per quella conversazione) o in **Impostazioni ›
Agente e autorizzazioni › Autorizzazioni predefinite**. Sono cinque: Sola lettura, Pianifica, Chiedi, Modifica file e
Automatico (l'elenco esatto con la descrizione è nei dati di questa versione). Nelle modalità che chiedono, ogni azione
mostra **Consenti** e **Nega**. Le azioni delicate (eliminare, installare, `sudo`, toccare il sistema o percorsi
protetti) chiedono sempre il permesso, anche in Automatico. In **Pianifica** l'agente indaga e propone un piano; con
**Esegui il piano** lo mette in pratica (oppure **Continua a perfezionare**). Per fermare all'istante il controllo del
mouse: porta il puntatore nell'angolo in alto a sinistra dello schermo.

## Cosa si vede mentre lavora

- Prima di ogni azione l'agente dice in una frase cosa sta per fare. Ogni azione è una riga con la sua icona e
  un'animazione mentre è in esecuzione; facendo clic si espande il dettaglio (il comando esatto, la modifica, il
  risultato).
- **Ragionamento:** la riga «Ha ragionato per…» si espande per mostrare il suo ragionamento.
- **Screenshot:** quando verifica qualcosa guardando lo schermo o una finestra, lo screenshot compare nella chat (clic
  per vederlo in grande).
- **Piano:** nelle attività lunghe, un elenco di attività fisso sopra la casella del messaggio (Piano · n di m).
- **Domande:** se ha bisogno di un'informazione, chiede con delle opzioni; si risponde con un clic o con **Altra
  risposta…**.
- I file che l'agente crea o modifica si possono aprire dalla chat (percorsi come link) e i comandi che deve eseguire
  l'utente compaiono con i pulsanti **Copia** ed **Esegui**.

## Azioni sulle risposte

Sotto ogni risposta: **Copia risposta**, **Leggi ad alta voce**, **Rigenera risposta** e **Segnala un problema con questa risposta**; a destra, i token scritti e la loro velocità. Se
la risposta ha modificato dei file, sotto compare la scheda **Ha cambiato 2 file** con ogni file, le righe aggiunte e tolte e una
nota («nuovo», «nel Cestino», «spostato in …»): un clic lo apre e il suo pulsante lo riporta com'era prima di quella risposta; con
due o più, **Annulla tutto**. Ogni azione che modifica file ha anche un proprio pulsante per annullare solo quella modifica.
Quando l'agente ha usato strumenti, la riga «Ha lavorato per 3 min 12 s» separa quello che ha fatto dalla risposta.

## Mentre lavora: scrivergli, permessi e avvisi

- **Scrivergli senza fermarlo:** mentre lavora si può scrivere e inviare (Invio o il pulsante di invio che compare
  accanto a **Interrompi**). Il messaggio resta in coda sopra la casella di testo (con × per toglierlo) e l'agente lo vede al
  passo successivo; nella chat compare con la nota «L'hai scritto mentre lavorava; l'ha visto qui». Se viene fermato prima, il testo torna nella casella.
- **Passi raggruppati:** ciò che pensa tra un'azione e l'altra («Ha ragionato un attimo») sta dentro il gruppo di azioni; alla fine, il
  gruppo si chiude in una riga che si apre con un clic. In alto, lo stato dice da quanto sta lavorando («Al lavoro · locale · 1:12»).
- **Permessi:** oltre a **Consenti** e **Nega**, il campo «Oppure digli cosa fare invece e premi Invio…» nega l'azione e passa l'indicazione all'agente;
  sotto l'azione resta «Gli hai chiesto: «…»». «Sempre «…» qui» non viene offerto per le azioni delicate né per le azioni su account
  collegati: quelle si confermano ogni volta.
- **Piano:** premendo **Esegui il piano**, la chat mostra il segno «Hai approvato il piano: viene eseguito passo per passo».
- **Controllo del computer:** mentre usa mouse e tastiera, in alto sullo schermo c'è un avviso con **Pausa** (l'agente
  aspetta e l'utente può usare il mouse; poi, **Riprendi**) e **Ferma**. Se l'agente sta per cliccare dove si trova
  l'avviso, questo si sposta. Si ferma anche portando il puntatore nell'angolo in alto a sinistra.
- **Avvisi fuori dalla finestra:** se aspetta un permesso o una risposta mentre Jayth è in secondo piano, l'icona della
  barra delle applicazioni lampeggia e compare un avviso; se un'attività di più di 15 secondi finisce mentre l'utente
  guarda altro, avvisa anche (cliccando l'avviso si apre quella conversazione).

## Memoria della conversazione (contesto)

Accanto al microfono della casella del messaggio, un anello mostra quanta memoria del modello occupa la conversazione:
del colore di accento se c'è spazio, ambra dal 70 % (con la percentuale) e rosso dall'85 %. Al 70 % Jayth accorcia i
vecchi output degli strumenti (ne lascia l'inizio; gli ultimi tre restano interi). Se non basta, all'85 % il modello
riassume la parte vecchia: ciò che precede l'ultimo messaggio dell'utente o, in un'unica attività molto lunga, i suoi
primi passi (gli ultimi restano com'erano). La lunghezza del riassunto si adatta alla memoria del modello. Cliccando
l'anello: quanto occupa, cosa farà Jayth, **Riassumi ora** e **Inizia una nuova conversazione**. L'avviso lasciato dal riassunto ha
**Vedi il riassunto**. Sui computer senza scheda grafica, riassumere può richiedere qualche minuto.

## Azioni sui tuoi messaggi

Passando il mouse su un tuo messaggio: **Copia messaggio**, **Modifica e invia di nuovo** (si modifica direttamente nel
messaggio; Ctrl+Invio invia, Esc annulla), **Riprova da qui** e **⋯ Altre azioni**: **Torna a questo punto** (rimuove
quel messaggio e tutto ciò che segue e ti lascia il testo nella casella) e **Nuova conversazione da qui** (copia la
conversazione fino a quel punto, l'originale non cambia). Se dopo quel messaggio l'agente ha modificato dei file, Jayth
chiede cosa fare: **Annulla quelle modifiche** o **Mantieni i file**. Non si può tornare a un messaggio che è già finito
nel riassunto di una conversazione molto lunga. Bisogna aspettare che l'agente finisca (o interromperlo).

## Conversazioni

- Si salvano da sole nella cronologia. **Cerca nelle tue conversazioni** (Ctrl+K) cerca nei titoli e nei messaggi.
- Il titolo lo assegna il modello dopo la prima risposta; si cambia con **Rinomina**.
- **Chat temporanea** (pulsante **Temporanea** della barra superiore): non viene salvata nella cronologia e non usa né
  modifica la memoria.
- Gli errori della chat (ad es. «Non riesco a connettermi al modello») includono **Riprova** e **Rimuovi questo avviso**.
- Esportarle tutte in Markdown o eliminarle: **Impostazioni › Dati e privacy**.
- Quando una conversazione è molto lunga, Jayth riassume la parte più vecchia perché il modello non la dimentichi.

## Jayth Code (progetti)

- Ci si entra con **Code** nella barra laterale (Ctrl+2; Ctrl+1 torna a Chat). **Nuovo progetto** o **Apri cartella…**.
  I progetti compaiono nella sezione **Progetti** della barra laterale, ognuno con le sue conversazioni (clic destro:
  **Modifica progetto…** per il nome, la cartella e le **istruzioni del progetto**; **Rimuovi dall'elenco**).
- **Esplora file** (Ctrl+B): icone per tipo; i file modificati dall'agente hanno un punto verde. Clic destro: Apri, Apri
  con la sua app, Nuovo file…, Nuova cartella…, Rinomina, Copia percorso, Copia percorso relativo, Sposta nel cestino.
  **Vai a un file…** con Ctrl+P.
- **Editor:** schede (Ctrl+S salva, Ctrl+W chiude). Markdown, HTML, SVG e CSV si aprono in **Anteprima** e si passa a
  **Codice** per modificarli. Word, Excel, PowerPoint e PDF si vedono in sola lettura; le immagini, con lo zoom.
  **Apri con la sua app** apre il file con l'app del sistema. **A capo automatico** (Alt+Z) per le righe lunghe.
- **Salvataggio automatico (autosalvataggio):** di default salva dopo 1 secondo senza scrivere. Si cambia in
  **Impostazioni › Generale › Editor di Jayth Code** (anche al cambio di scheda o di finestra, oppure disattivato: salva
  con Ctrl+S). Una scheda con «●» ha modifiche non salvate; con «⚠», non è stato possibile salvarla (il motivo compare
  passando il mouse).
- **Terminale** (Ctrl+`): quello del sistema (PowerShell su Windows, zsh/bash su macOS e Linux), nella cartella del
  progetto; ↑ ↓ scorre la cronologia. Per i comandi, non per i programmi interattivi.
- **Pannello dell'agente** (Ctrl+L): la chat del progetto; l'agente lavora nella cartella del progetto e legge le
  regole di AGENTS.md, JAYTH.md o CLAUDE.md se esistono.
- **Disposizione dei pannelli** (barra superiore): mostrare o nascondere i pannelli, agente a sinistra o a destra,
  terminale sotto o a destra dell'editor e **Modalità focus (solo l'editor)** (Ctrl+Shift+M). I divisori si
  trascinano; un doppio clic su uno comprime il pannello accanto. Tutto viene ricordato.

## Browser di Jayth

Pulsante del globo nella barra superiore. L'utente può navigare al suo interno o chiedere all'agente di usare un sito
web (cercare all'interno di un sito, compilare moduli, pagine con JavaScript). L'agente lo usa sotto gli occhi
dell'utente, con il proprio puntatore e un bagliore sui bordi mentre ha il controllo; l'utente può intervenire quando
vuole. Le password le scrive sempre l'utente, e l'agente chiede conferma prima di acquistare, pagare, pubblicare o
inviare dati personali.

Nella sua barra: indietro, avanti, ricarica (o interrompi durante il caricamento), l'indirizzo (o ciò che si vuole
cercare), **Cerca nella pagina** (Ctrl+F), aprire la pagina nel browser di sistema e un menu con **Ingrandisci** e
**Riduci** (Ctrl++ e Ctrl+-), **Copia l'indirizzo**, **Salva la pagina come PDF** (Ctrl+P; va in Download) e
**Cancella i dati del browser** (cookie, accessi e cache). Il tasto destro offre le opzioni tipiche di link,
immagini e testo. Le pagine vengono richieste nella lingua dell'interfaccia. All'apertura del browser gli altri
pannelli si restringono e alla chiusura recuperano la loro larghezza.

## Canvas

Per pagine web, documenti lunghi, diagrammi SVG o programmi che l'utente vuole vedere: l'agente li mostra in un
pannello accanto alla chat («Visualizza nel canvas»), con anteprima e codice, versioni (v1 di n) e la possibilità di
salvarli.

## Immagini

L'agente può creare immagini nuove (foto, illustrazioni, loghi, icone, sfondi, copertine) direttamente sul computer:
quando glielo chiedi o quando un'attività ne ha bisogno (illustrare un sito web, una presentazione o un documento).
Modifica anche un'immagine che hai già (con FLUX.2 [klein]). Mentre la crea si vedono il passaggio in corso, quanto
manca e un'anteprima; alla fine compare in grande nella chat con **Apri** e **Mostra nella cartella**. Viene salvata
nella cartella «immagini» della cartella di lavoro (o del progetto), o in quella scelta nelle Impostazioni.

- Funziona senza internet né servizi esterni, con stable-diffusion.cpp (MIT) e un modello per immagini con licenza
  libera (Apache-2.0 o MIT): **FLUX.2 [klein] 4B** (versatile e con testo all'interno dell'immagine, quello consigliato
  con una scheda grafica), **Z-Image Turbo** (più realistico, meglio con una scheda grafica) o **Segmind Vega RT** (il
  più veloce senza scheda grafica, in 4 passaggi, con meno dettagli). In «Automatico», Jayth sceglie in base al computer.
  Senza scheda grafica, FLUX.2 impiega circa 11 minuti per immagine (misurato su un portatile con un i5 a 4 core).
- La prima volta bisogna installarlo (circa 5 GB, una sola volta): con **Installa** nel riquadro che compare nella chat
  quando l'agente ne ha bisogno (poi, **Continua**), o in **Impostazioni › Immagini**. Si vede l'avanzamento, si può
  annullare e riprende se si interrompe. **Rimuovi** elimina i suoi file.
- Tempo: con una scheda grafica, meno di un minuto per immagine; senza, diversi minuti (per questo, senza scheda grafica
  si creano a 512 px). Si cambia in Impostazioni › Immagini › «Dimensione delle immagini».
- Si usa solo se il modello di testo attivo non crea immagini da sé (oggi nessuno di quelli che funzionano con
  llama.cpp lo fa). Si disattiva con «Consenti all'agente di creare immagini».
- Ogni immagine è un'azione di scrittura: a seconda della modalità di autorizzazione si approva prima di crearla, e si
  può annullare.
- Per i grafici di dati l'agente usa Python, e per i diagrammi, SVG nel canvas.

## Conoscenza

In **Impostazioni › Conoscenza** si scelgono delle cartelle (note, documenti, progetti) e l'agente cerca al loro interno
per significato, non solo per parole esatte («quanto è costato riparare la macchina?» trova la nota della fattura
dell'auto), senza doverle leggere per intero: ideale con i modelli locali, che hanno poca memoria di conversazione. Lo
fa con un piccolo motore di ricerca che funziona sul computer (Qwen3-Embedding 0.6B, 640 MB, un solo download) e
capisce italiano, spagnolo, inglese, portoghese e molte altre lingue. Supporta testo, codice, Markdown, Word, PDF,
PowerPoint ed Excel.

- **Ricerca per significato:** **Installa** (una volta).
- **Cartelle di conoscenza:** **Aggiungi cartella…** e **Rimuovi**.
- **Indice:** quanti file e frammenti contiene e quando è stato aggiornato; **Aggiorna l'indice** (rilegge solo ciò che
  è nuovo o cambiato) e «Aggiorna l'indice all'apertura di Jayth».
- L'agente lo usa solo quando serve (ad es. «secondo le mie note…») e cita da quale file viene ogni dato.

## Controllo del computer e altri programmi

L'agente può aprire programmi e file, leggere i pulsanti e i campi di qualsiasi finestra (accessibilità del sistema),
fare clic, trascinare, scrivere, premere scorciatoie, gestire le finestre, usare gli appunti e fare screenshot dello
schermo o di una finestra. Mentre ha il controllo, si vedono un bagliore sui bordi dello schermo e il suo puntatore. Si
attiva o disattiva in **Impostazioni › Strumenti › Consenti il controllo del computer**. Su macOS bisogna concedere a
Jayth i permessi di **Registrazione schermo** e **Accessibilità** (Impostazioni di Sistema › Privacy e sicurezza). Su
Linux funziona nelle sessioni X11 (su Wayland il controllo globale è limitato); per elencare le finestre serve `wmctrl`.

## Modelli

- **Modelli** (menu del profilo, o Impostazioni › Modelli › Gestisci modelli…): elenco dei modelli installati con tipo,
  variante e dimensione. **Usa questo**, **Aggiungi modello…**, **Individua…** (se hai spostato il file), **Cerca in
  una cartella…**, **Apri cartella**, **Rimuovi dall'elenco** ed **Elimina file…**.
- **Aggiungere un modello** (configurazione guidata): catalogo di modelli aperti di Hugging Face contrassegnati a seconda
  che entrino o no nel computer (Agente = usa strumenti; Visione = capisce le immagini; Ragiona = pensa prima di
  rispondere), un repository scritto a mano (utente/Modello-GGUF), un tuo file .gguf o una cartella con il modello
  originale (config.json + .safetensors), che Jayth converte in GGUF sul computer. Si sceglie la quantizzazione (quella
  consigliata è contrassegnata) e, se esiste, la **visione** perché il modello veda immagini e screenshot.
- **Modelli via API…**: OpenAI, Claude, Gemini, Ollama, LM Studio o un altro server compatibile con OpenAI. Anche in
  **Impostazioni › Modelli › Provider** (URL, nome del modello e chiave). Con un modello via API, Jayth chiede al
  servizio quanto contesto e quanto output ammette quel modello e li usa (con un tetto di 200.000 token per passo
  per contenere la spesa), si adatta da solo se il servizio rifiuta qualche parametro, consente turni più lunghi
  (120 passi) e offre all'agente gli **aiutanti**: sottoattività svolte da un'altra copia del modello, di cui torna
  solo il resoconto. L'agente decide che cosa può fare ogni aiutante (solo leggere e cercare, anche modificare file
  di alcune cartelle precise, oppure in più eseguire comandi) e ne risponde: ciò che fa l'aiutante si vede nella
  chat, si può annullare e, se serve un'autorizzazione dell'utente, gli viene negata e lo fa l'agente. L'incarico
  chiede l'autorizzazione all'utente come la chiederebbe l'azione equivalente. La stessa finestra mostra il
  **consumo** di ogni servizio salvato: richieste, token e costo approssimativo di oggi, degli ultimi 30 giorni e
  in totale, per modello; i limiti dell'account secondo l'ultima risposta del servizio; il saldo, se il servizio lo
  fornisce (OpenRouter, DeepSeek); e segnala i modelli nuovi o ritirati. **Consumo ufficiale** apre la pagina del
  servizio con la cifra e il piano reali (Jayth conta solo ciò che è stato inviato da questo computer) e **Prezzo
  di un modello…** serve a scrivere il prezzo di un modello che Jayth non conosce. Nella chat, ogni turno con un
  modello via API termina indicando quanti token ha consumato e il loro costo approssimativo. Questi servizi
  ragionano senza mostrarlo e consegnano ogni azione in una volta sola, quindi la chat può passare un po' di tempo
  a dire che il servizio sta preparando la risposta; se una richiesta resta bloccata, Jayth la interrompe e chiede
  al modello di continuare.
- **Avviare o arrestare il modello:** chip del modello › **Motore**, o il pulsante **Avvia modello** dell'avviso.
  Avviato occupa memoria e risponde subito; arrestato la libera.
- I download mostrano percentuale, velocità e tempo, riprendono se si interrompono e vengono verificati con SHA-256.
- Se esce una nuova versione di uno dei tuoi modelli, Jayth ti avvisa (si disattiva in Impostazioni › Informazioni ›
  Novità).

## Motore e prestazioni

Jayth scarica la versione ufficiale di llama.cpp adatta al computer: Metal sui Mac con Apple Silicon, CUDA per NVIDIA,
Vulkan per AMD o Intel Arc, oppure CPU. In **Impostazioni › Prestazioni**: **Cambia o aggiorna il motore…**,
**Preriscalda all'avvio del modello**, **Memoria della conversazione (contesto)** (di default **Automatico**: tutto il
contesto che il modello supporta di fabbrica, ridotto se la sua memoria non entra nel computer; con **Contesto
compresso** ne entra il doppio o più), **Arresta il modello se non viene usato per**, e in
**Impostazioni del motore**: Thread della CPU, Thread in lettura (automatico: senza scheda grafica legge con tutti i thread del processore), Layer sulla GPU (in automatico il modello viene ripartito tra GPU e RAM),
Dimensione del batch, Contesto compresso, Flash attention, Accelerazione in scrittura, mmap, blocco nella RAM e la porta
locale. Le modifiche del motore si applicano al riavvio del modello (**Riavvia modello**). Il registro del motore è in
**Impostazioni › Registro del modello**.

- **Accelerazione con scheda grafica:** Jayth rileva la scheda del computer e sceglie da solo il motore adatto: CUDA per
  NVIDIA (la versione 13 o 12 in base al driver e all'età della scheda), Vulkan per le schede AMD e Intel Arc dedicate,
  Metal sui Mac con Apple Silicon, oppure il processore se non c'è una scheda che aiuti (quelle integrate di solito sono
  più lente). Il motore ripartisce da solo il modello tra la scheda e la RAM. Se in seguito il computer ha una scheda
  che il motore non sfrutta, Jayth propone di installare il motore accelerato con un clic (si può disattivare con
  «Proponi il motore accelerato»). Se la scheda non riesce a caricare un modello (per esempio, per mancanza di memoria),
  Jayth lo avvia sul processore e avvisa. In questa pagina si vede cosa accelera il modello e quanti layer sono sulla
  scheda. «Cambia o aggiorna il motore…» permette di sceglierlo a mano e di aggiornarlo all'ultima versione.
- **Ottimizza per questo computer** (Impostazioni › Prestazioni): invece di stimare, misura davvero con il modello
  attivo (qualche minuto, con il modello arrestato nel frattempo): prova i thread e la flash attention con llama-bench e
  l'«Accelerazione in scrittura» (decodifica speculativa: **MTP**, per i modelli che includono quei layer come Qwen 3.5
  e 3.8, e **n-grammi**, che accelerano la riscrittura di codice o testo), e mantiene la combinazione più veloce. Sotto
  si vede il risultato («legge … tok/s · scrive … tok/s»). L'«Accelerazione in scrittura» si può scegliere anche a mano
  in Impostazioni del motore.
- **Memoria:** all'avvio del modello, Jayth avvisa se non entra nel computer (andrà molto lento e conviene una variante
  più piccola) o se in quel momento altri programmi occupano la memoria. La memoria che llama.cpp conserva delle
  conversazioni precedenti si adatta da sola a quella che avanza, per non toglierla al modello.

## Impostazioni

Si aprono dal menu del profilo (**Impostazioni**). Le modifiche si salvano da sole. In alto, «Cerca impostazione» trova qualsiasi opzione per nome o per spiegazione. Pagine e opzioni (con il loro nome
esatto):
- **Generale:** «Lingua dell'interfaccia», «Tema», «Dimensione del testo», «Animazioni (comparsa dei messaggi, barra
  laterale, avvisi)», «Barra del titolo integrata nella finestra» (solo Windows).
  - **Editor di Jayth Code:** «Salvataggio automatico dei file».
  - **Avvio e finestra:** aprire Jayth all'avvio del sistema (ridotto nell'area di notifica), «Avvia il modello
    all'apertura di Jayth», «Alla chiusura della finestra, continua a funzionare nell'area di notifica», «Avvisami
    quando l'agente ha bisogno della mia approvazione», «Scorciatoia della finestra rapida».
- **Personalizzazione:** «Come vuoi che ti chiami?», «Cosa dovrebbe sapere Jayth di te?», «Come vuoi che risponda?»,
  «Lingua delle risposte», «Istruzioni aggiuntive per l'agente».
  - **Voce:** «Precisione della dettatura», «Lingua della dettatura».
  - **Memoria:** «Usa la memoria (ricorda cose tra una conversazione e l'altra)», l'elenco dei ricordi (aggiungere,
    modificare o eliminare) e **Cancella tutta la memoria**.
- **Modelli:** il modello attivo, **Gestisci modelli…**, **Aggiungi modello…**, **Configurazione guidata…** e «Cartella
  in cui vengono scaricati i modelli».
  - **Provider:** «Quale motore usa l'agente?» (locale o server esterno), «URL del server esterno (termina con /v1)»,
    «Nome del modello su quel server», «Chiave API (se il server la richiede)» e **Prova connessione**. La chiave viene salvata cifrata sul computer, non nel file delle impostazioni.
  - **Spesa per i modelli via API:** «Avvisa se una conversazione supera (US$)», «Avvisa se la spesa del giorno supera (US$)» e «Quando avvisa, metti in pausa l'attività finché non dici se continuare».
- **Generazione:** «Ragiona a fondo di default (risposte migliori, più lento)», «Parametri di campionamento» (consigliati
  per il modello attivo o personalizzati), «Temperatura», «Lunghezza massima di ogni risposta (token)».
  - **Campionamento avanzato:** «Top-p», «Top-k», «Min-p», «Penalità di ripetizione», «Seme» e **Ripristina i valori
    consigliati**.
- **Prestazioni:** **Cambia o aggiorna il motore…**, «Preriscalda all'avvio del modello», «Memoria della conversazione
  (contesto)», «Arresta il modello se non viene usato per».
  - **Impostazioni del motore:** «Thread della CPU», «Thread in lettura», «Layer sulla GPU», «Dimensione del batch», «Contesto compresso»,
    «Flash attention», «Carica il modello con mmap (avvio più rapido)», «Blocca il modello nella RAM (evita che il
    sistema lo sposti su disco)», «Porta locale del motore».
  - **Download:** «Connessioni simultanee per scaricare i modelli».
- **Agente e autorizzazioni:** «Autorizzazioni predefinite», «Cartella di lavoro della modalità Chat», «Comandi
  consentiti senza chiedere».
  - **Limiti:** «Passaggi massimi per attività», «Tempo massimo per ogni comando», «Testo massimo che il modello riceve
    da ogni azione», «Invia screenshot e immagini al modello (se ha la visione)», «Immagini recenti che ricorda».
- **Strumenti:** «Consenti l'accesso a internet (cercare, leggere pagine e scaricare)», «Consenti il controllo del
  computer (mouse, tastiera, screenshot)», «Strumenti caricati» (di default, solo quelli che servono a ogni attività:
  l'agente ha a portata di mano quelli di base e attiva gli altri gruppi —web, browser, controllo del PC, documenti,
  Python, immagini, agenda e ogni connettore— quando gli servono; così il modello locale ha più memoria e risponde prima).
  - **Strumenti disponibili:** ogni strumento dell'agente si può disattivare separatamente.
  - **Ricerca web:** «Motore di ricerca» (automatico con DuckDuckGo e Bing, senza chiave; Brave Search o SearXNG), «Chiave di
    Brave Search», «URL di SearXNG».
  - **Servizi con il tuo account:** riquadri per collegare servizi online (**Connetti**, **Disconnetti**, **Configura
    Google…**).
  - **Connettori MCP:** template, aggiungere (**Aggiungi e prova**), provare e rimuovere connettori.
- **Conoscenza:** ricerca per significato (**Installa**), cartelle (**Aggiungi cartella…**, **Rimuovi**), indice
  (**Aggiorna l'indice**) e «Aggiorna l'indice all'apertura di Jayth».
- **Immagini:** «Consenti all'agente di creare immagini».
  - **Modello per immagini:** «Modello scelto» (Automatico, FLUX.2 [klein] 4B, Z-Image Turbo o Segmind Vega RT), il suo
    stato e **Installa**, **Annulla** o **Rimuovi**.
  - **Immagini create:** «Dimensione delle immagini» (Automatico, 512, 768 o 1024 px) e «Cartella in cui vengono
    salvate».
- **Dati e privacy:** la cartella dei dati (**Apri cartella**).
  - **Conversazioni:** **Esporta conversazioni (Markdown)…**, liberare lo spazio delle immagini non usate ed eliminare
    tutte le conversazioni.
- **Registro del modello:** il registro del motore llama.cpp (per la diagnosi) e **Aggiorna**.
- **Scorciatoie da tastiera:** l'elenco delle scorciatoie.
- **Informazioni:** versione, autore e licenza (**Visualizza la licenza**, **Politica sul marchio**), **Cerca
  aggiornamenti**, **Apri su GitHub**.
  - **Novità:** «Avvisami quando c'è una nuova versione di Jayth», «Scarica gli aggiornamenti in background e installali
    alla chiusura di Jayth», «Avvisami quando esce una nuova versione dei miei modelli».
  - **Feedback:** **Segnala un errore…** e **Suggerisci un miglioramento…**.

## Personalizzazione e memoria

In **Personalizzazione** dici all'agente come chiamarti, cosa sapere di te, come rispondere (stile), in che lingua
rispondere (Automatico = la lingua del tuo messaggio) e istruzioni aggiuntive. La **memoria** conserva preferenze
durature tra una conversazione e l'altra (l'agente le salva quando gliele dici, ad es. «uso pnpm»); si rivede, modifica
o elimina in Personalizzazione › Memoria e si può disattivare. La chat temporanea non la usa.

## Assistenti e abilità

Menu del profilo › **Assistenti e abilità**. Un **assistente** è un agente con istruzioni e file di riferimento propri
(ad es. «Correttore di stile»); si sceglie con **+ › Usa un assistente** nella casella del messaggio. Un'**abilità** è
una procedura che l'agente usa quando è adatta all'attività (ad es. «Redigere report esecutivi e consegnarli in Word»);
si creano, importano, attivano o disattivano nella scheda Abilità (**Aggiungi esempi** ne aggiunge alcune di esempio).

## Attività pianificate

Menu del profilo › **Attività pianificate**. Un'attività è un incarico che l'agente svolge da solo all'ora stabilita (Una
volta, Ogni giorno, Dal lunedì al venerdì, Ogni settimana nei giorni scelti o A intervalli) e avvisa quando ha finito:
**Nuova attività**, nome, cosa deve fare, quando, come agisce (autorizzazioni), **Esegui ora** e **Visualizza ultimo
risultato**. Le attività vengono eseguite mentre Jayth è aperto (anche nell'area di notifica). L'agente può anche
pianificarle se glielo chiedi.

## Finestra rapida

Una piccola barra per chiedere a Jayth da qualsiasi programma: scorciatoia **Ctrl+Alt+J** (si cambia o disattiva in
Impostazioni › Generale › Scorciatoia della finestra rapida) o **Domanda rapida** nell'area di notifica. **Con
screenshot** allega un'immagine di ciò che c'era sullo schermo (Ctrl+S). Invio invia, Esc chiude.

## Connettori MCP e ricerca web

- **Connettori MCP** (Impostazioni › Strumenti): ampliano gli strumenti dell'agente con lo standard Model Context
  Protocol (file, memoria, browser Playwright, Git, Fetch, GitHub…). Ci sono template che compilano il modulo; possono
  essere un programma del computer (comando e argomenti, molti richiedono Node.js o uv) o un servizio remoto (indirizzo
  e chiave). **Aggiungi e prova** li collega; se il servizio chiede di accedere, si apre la sua pagina (poi, **Accedi**
  o **Esci dall'account** nella sua riga).
- **Servizi con il tuo account** (Impostazioni › Strumenti): è tutto facoltativo; Jayth funziona in locale e senza
  internet. Ci sono riquadri per Higgsfield (immagini e video con IA nel cloud, con i tuoi crediti), Notion, Canva,
  Gmail, Google Drive, Google Calendar, Linear, Jira e Confluence, e Hugging Face (senza account). **Connetti** apre la
  pagina del servizio nel browser: l'utente accede lì e autorizza; Jayth non vede mai la password e conserva
  l'autorizzazione cifrata sul computer (si rinnova da sola). **Disconnetti** la dimentica. Gmail, Drive e Calendar
  richiedono prima **Configura Google…**: creare una volta un «ID client OAuth» di tipo «App desktop» in Google Cloud
  (con le API MCP attivate e il proprio indirizzo email come utente di test) e incollarne l'ID e il segreto; vale per
  tutti e tre.
- Se un'attività lo richiede, l'agente può proporre di collegare un servizio: compare il suo riquadro nella chat con
  **Connetti** e, alla fine, **Continua**. Ciò che modifica qualcosa nell'account (inviare, pubblicare, spendere crediti)
  chiede sempre l'approvazione, anche in modalità Automatico; leggere no.
- **Ricerca web:** funziona senza configurare nulla: DuckDuckGo e, se chiede una verifica (Jayth non la aggira), Bing tramite il motore del browser integrato, senza mostrarlo. Wikipedia resta l'ultima risorsa. Una chiave di Brave Search o un'istanza propria di SearXNG sono facoltative.

## Lingua dell'interfaccia

Jayth è disponibile in spagnolo, inglese, portoghese (Brasile), francese, tedesco, italiano,
giapponese e cinese semplificato. La prima volta usa la
lingua del sistema (altrimenti l'inglese); si cambia in **Impostazioni › Generale › Lingua dell'interfaccia** e Jayth propone di riavviarsi per
applicarla. La lingua in cui risponde l'agente è a parte: di default, quella del messaggio dell'utente (Impostazioni ›
Personalizzazione › Lingua delle risposte).

## Aggiornamenti

Quando c'è una nuova versione, Jayth la scarica in background (il pulsante della barra laterale mostra «Download
dell'aggiornamento… %») senza interrompere nulla. Al termine, il pulsante diventa **Riavvia per aggiornare**: premendolo,
Jayth si chiude, viene installata la nuova versione (con una piccola finestra «Aggiornamento di Jayth…») e si riapre. Se
non lo premi, si installa da sola alla chiusura di Jayth. All'apertura della nuova versione compare un avviso con un
link alle **Novità**. Si può controllare a mano dal menu del profilo › **Cerca aggiornamenti** e disattivare il download
automatico in Impostazioni › Informazioni › Novità. Conversazioni, impostazioni e modelli si conservano con
l'aggiornamento.

## Dove viene salvato tutto

- **Impostazioni, conversazioni, motore e modelli:** Windows `%LOCALAPPDATA%\Jayth`, macOS `~/Library/Application
  Support/Jayth`, Linux `~/.local/share/jayth` (il percorso reale di questo computer è nei dati di questa versione).
- **Cartella di lavoro della modalità Chat:** di default `Documenti/Jayth`; si cambia in Impostazioni › Agente e
  autorizzazioni.
- **Cartella dei modelli:** si cambia in Impostazioni › Modelli. I modelli per immagini vanno nella sua sottocartella
  `imagen`, e il motore delle immagini accanto a quello di llama.cpp (`runtime/imagen`).
- **Modalità portatile:** un file `portable.txt` accanto al programma salva tutto in `userdata/` lì accanto (per una
  chiavetta USB).
- **Privacy:** tutto resta sul computer; Jayth non invia conversazioni né file a nessun server. Usa internet solo per
  scaricare modelli e motori, cercare aggiornamenti e per gli strumenti web che l'utente consente (o quando si usa un
  modello via API, che riceve i messaggi di quella conversazione). Feedback e rapporti lasciano il computer solo quando l'utente preme **Invia**.
- **Disinstallare:** Windows, Impostazioni › App › Jayth › Disinstalla; macOS, trascina Jayth nel Cestino; Linux,
  elimina l'AppImage. I dati e i modelli non vengono eliminati con la disinstallazione.

## Feedback e aiuto

Menu del profilo › **Invia feedback…** o **Segnala un errore…** (anche in Impostazioni › Informazioni): l'utente
rivede il testo prima di inviarlo. Sotto ogni risposta, **Segnala un problema con questa risposta**. Con **Invia**, il feedback arriva direttamente e in privato al team di Jayth (non viene pubblicato e non serve un account); **Pubblica su GitHub** apre invece una segnalazione pubblica su GitHub. Se Jayth ha un errore imprevisto, lo salva sul computer (senza percorsi personali) e propone **Invia rapporto…**; non lo invia mai da solo. Il progetto è su
https://github.com/Json-Tuiran/jayth.ai (download in Releases).

## Problemi frequenti

- **«Il modello è spento» o non risponde:** premi **Avvia modello** (o scrivi: Jayth lo avvia da solo). Se non parte,
  il motivo compare nell'avviso e in Impostazioni › Registro del modello; di solito è memoria insufficiente: scegli una
  quantizzazione più piccola, riduci la **Memoria della conversazione (contesto)** o usa il **Contesto compresso**.
- **È lento:** sui computer senza GPU i modelli grandi richiedono tempo; prova un modello più piccolo, abbassa l'impegno
  a Basso o, con una GPU NVIDIA, controlla che il motore sia CUDA (Impostazioni › Prestazioni › Cambia o aggiorna il
  motore…).
- **Non trova il modello («Non trovo il file…»):** premi **Cercalo** o, in Modelli, **Individua…** o **Cerca in una
  cartella…**.
- **Non vede le immagini:** il modello ha bisogno della visione (proiettore); quando lo aggiungi, seleziona **Includi la
  visione**. Controlla Impostazioni › Agente e autorizzazioni › Invia screenshot e immagini al modello.
- **Non crea immagini o non riesce a crearle:** installa il generatore in Impostazioni › Immagini e controlla che
  «Consenti all'agente di creare immagini» sia selezionato. Se esaurisce la memoria, scegli una dimensione minore o
  FLUX.2 [klein] e chiudi altri programmi; il dettaglio dell'ultimo tentativo è nel registro `imagen.log` della cartella
  dei dati.
- **Non può usare internet o il mouse:** controlla Impostazioni › Strumenti (accesso a internet, controllo del computer
  e l'elenco degli strumenti).
- **Windows mostra «Windows ha protetto il PC»:** il programma di installazione non è ancora firmato: Ulteriori
  informazioni › Esegui comunque. **macOS:** la prima volta, clic destro su Jayth › Apri.
- **L'agente non permette di tornare a un messaggio:** aspetta che finisca o interrompilo; i messaggi già riassunti non
  si possono riavvolgere (usa Nuova conversazione).
- **Una scheda dell'editor mostra ⚠:** non è stato possibile salvarla (file di sola lettura o cartella protetta); il
  motivo compare passando il mouse sulla scheda.
