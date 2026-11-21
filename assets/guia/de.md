# Jayth-Anleitung

Diese Anleitung beschreibt die installierte Version von Jayth: was jeder Teil macht, wo er sich befindet und wie man ihn
benutzt. Die Namen von Schaltflächen und Menüs sind die, die in der Oberfläche angezeigt werden (in dieser Sprache). Die
Daten dieses Computers (Version, aktives Modell, Ordner, Tastenkürzel…) werden separat ergänzt und beim Nachschlagen
direkt aus der App gelesen.

## Was Jayth ist

Jayth ist eine Desktop-Anwendung für Windows, macOS und Linux, die ein lokales KI-Modell (GGUF-Format, mit llama.cpp)
in einen Agenten verwandelt, der auf dem Computer des Nutzers arbeitet: Er programmiert, erstellt und bearbeitet Dateien,
führt Befehle aus, nutzt andere Programme, surft mit seinem eigenen Browser im Web und liest und erstellt Word-, Excel-,
PowerPoint- und PDF-Dokumente. Alles geschieht auf dem Computer und funktioniert ohne Internet, sobald das Modell
heruntergeladen ist. Der Nutzer gibt jede Aktion frei (oder lässt ihm im automatischen Modus freie Hand). Jayth kann
auch Modelle über eine API nutzen (OpenAI, Claude, Gemini, Ollama…).
Erstellt von Ing. Jeison Tuiran. Freie Software unter der Lizenz GPL-3.0. Web: https://github.com/Json-Tuiran/jayth.ai

## Das Hauptfenster

- **Seitenleiste (links):** oben die Schaltfläche ≡ zum Ausblenden (Strg+Umschalt+S) und die Auswahl **Chat / Code**.
  Darunter **Neue Unterhaltung** (Strg+N), **In deinen Unterhaltungen suchen** (Strg+K) und der Verlauf, nach Datum
  gruppiert (Heute, Gestern, Letzte 7 Tage…; ein Klick auf eine Gruppe klappt sie ein). Rechtsklick auf eine
  Unterhaltung: **Umbenennen** oder **Löschen**. Ganz unten die Schaltfläche deines Profils (**Profil und
  Einstellungen**) und, wenn es eine neue Version gibt, die Update-Schaltfläche. Ist die Leiste ausgeblendet, taucht sie
  auf, wenn du mit der Maus an den linken Rand fährst.
- **Obere Leiste:** links der Status des Modells (z. B. „● Bereit · lokal“). Rechts: **Temporär** (temporärer Chat),
  die Weltkugel (**Jayth-Browser**), **Anordnung der Bereiche**, der Ordner (öffnet den Arbeitsordner) und **⋯ Weitere
  Optionen** (Unterhaltung umbenennen, Arbeitsordner öffnen, Unterhaltung löschen). In Jayth Code erscheinen außerdem
  die Schaltflächen für den **Datei-Explorer** (Strg+B), das **Terminal** (Strg+`) und den **Agent-Bereich**
  (Strg+L).
- **Dein Profilmenü** (unten in der Seitenleiste): Einstellungen, Personalisierung, Gedächtnis, Assistenten und
  Fähigkeiten, Geplante Aufgaben, Modelle, API-Modelle…, Tastenkürzel, Feedback senden…, Fehler melden…, Nach Updates
  suchen, Über Jayth und Beenden.
- **Infobereich:** Anzeigen, Schnelle Frage, Agent stoppen und Beenden.

## Das Nachrichtenfeld

- **Eingabetaste** sendet; **Umschalt+Eingabetaste** fügt einen Zeilenumbruch ein. Strg+V fügt ein Bild ein.
- Schaltfläche **+**: Dateien oder Dokumente anhängen…, Bild anhängen…, Screenshot anhängen und **Assistent verwenden**.
- **Mikrofon:** mit der Stimme diktieren (wird auf dem Computer transkribiert; das Diktiermodell wird beim ersten Mal
  heruntergeladen).
- **Berechtigungs-Chip** (z. B. „Fragen“ oder „Automatisch“): ändert den Berechtigungsmodus dieser Unterhaltung.
- **Modell-Chip** (z. B. „Qwen3.8 27B · Niedrig“): wechselt das Modell, stellt den **Aufwand** ein (wie viel es vor dem
  Antworten nachdenkt: Niedrig, Mittel, Hoch), lädt Modelle herunter oder fügt sie hinzu (Modell herunterladen oder
  hinzufügen…), Modelle verwalten…, API-Modelle… und **Engine** (Modell starten oder stoppen).
- Ist das Modell aus, erscheint über dem Feld ein Hinweis mit **Modell starten** (lässt sich mit dem × schließen; er
  kommt wieder, wenn sich die Lage ändert). Schreibst du bei gestopptem Modell, startet Jayth es und sendet die
  Nachricht, sobald es bereit ist.
- Während der Agent arbeitet, wird die Senden-Schaltfläche zu **Stoppen**.

## Berechtigungsmodi

Sie werden im Berechtigungs-Chip des Nachrichtenfelds (für diese Unterhaltung) oder unter **Einstellungen › Agent und
Berechtigungen › Standardberechtigungen** geändert. Es gibt fünf: Nur lesen, Planen, Fragen, Dateien bearbeiten und
Automatisch (die genaue Liste mit Beschreibung steht in den Daten dieser Version). In den Modi, die nachfragen, zeigt
jede Aktion **Erlauben** und **Ablehnen**. Heikle Aktionen (löschen, installieren, `sudo`, Eingriffe ins System oder in
geschützte Pfade) fragen immer nach, auch im Modus Automatisch. Im Modus **Planen** recherchiert der Agent und schlägt
einen Plan vor; mit **Plan ausführen** setzt er ihn um (oder **Weiter anpassen**). Um die Maussteuerung sofort zu
stoppen: den Mauszeiger in die obere linke Ecke des Bildschirms bewegen.

## Was du siehst, während er arbeitet

- Vor jeder Aktion sagt der Agent in einem Satz, was er tun wird. Jede Aktion ist eine Zeile mit ihrem Symbol und einer
  Animation, solange sie läuft; ein Klick darauf klappt die Details auf (den genauen Befehl, die Änderung, das Ergebnis).
- **Denkprozess:** Die Zeile „… lang nachgedacht“ lässt sich aufklappen, um seine Überlegungen zu sehen.
- **Screenshots:** Wenn er etwas prüft, indem er auf den Bildschirm oder ein Fenster schaut, erscheint der Screenshot
  im Chat (ein Klick zeigt ihn groß).
- **Plan:** Bei langen Aufgaben steht eine feste Aufgabenliste über dem Nachrichtenfeld (Plan · n von m).
- **Rückfragen:** Braucht er eine Angabe, fragt er mit Optionen; du antwortest mit einem Klick oder mit **Andere
  Antwort…**.
- Dateien, die der Agent erstellt oder ändert, lassen sich aus dem Chat öffnen (Pfade als Links), und Befehle, die der
  Nutzer selbst ausführen soll, erscheinen mit den Schaltflächen **Kopieren** und **Ausführen**.

## Aktionen bei Antworten

Unter jeder Antwort: **Antwort kopieren**, **Vorlesen**, **Antwort neu generieren**, **Ein Problem mit dieser Antwort
melden** und, wenn Dateien geändert wurden, **Änderungen rückgängig machen** (stellt alle Dateien wieder her, die in
dieser Antwort geändert wurden). Jede Aktion, die Dateien ändert, hat außerdem eine eigene Schaltfläche, um nur diese
Änderung rückgängig zu machen. Rechts stehen die Tokens, die Geschwindigkeit und das genutzte Gedächtnis der
Unterhaltung.

## Aktionen bei deinen Nachrichten

Wenn du mit der Maus über eine deiner Nachrichten fährst: **Nachricht kopieren**, **Bearbeiten und erneut senden** (wird
direkt in der Nachricht bearbeitet; Strg+Eingabetaste sendet, Esc bricht ab), **Ab hier erneut versuchen** und **⋯
Weitere Aktionen**: **Zu diesem Punkt zurück** (entfernt diese Nachricht und alles danach und lässt dir den Text im
Feld) und **Neue Unterhaltung ab hier** (kopiert die Unterhaltung bis zu diesem Punkt; das Original bleibt unverändert).
Hat der Agent nach dieser Nachricht Dateien geändert, fragt Jayth, ob es **Diese Änderungen rückgängig machen** oder
**Dateien behalten** soll. Zu einer Nachricht, die schon in der Zusammenfassung einer sehr langen Unterhaltung steckt,
kann man nicht zurückkehren. Man muss warten, bis der Agent fertig ist (oder ihn stoppen).

## Unterhaltungen

- Sie werden automatisch im Verlauf gespeichert. **In deinen Unterhaltungen suchen** (Strg+K) durchsucht Titel und
  Nachrichten.
- Den Titel vergibt das Modell nach der ersten Antwort; ändern lässt er sich mit **Umbenennen**.
- **Temporärer Chat** (Schaltfläche **Temporär** in der oberen Leiste): wird nicht im Verlauf gespeichert und nutzt
  oder ändert das Gedächtnis nicht.
- Fehler im Chat (z. B. „Ich kann mich nicht mit dem Modell … verbinden“) bieten **Erneut versuchen** und **Diesen
  Hinweis entfernen**.
- Alle als Markdown exportieren oder löschen: **Einstellungen › Daten und Datenschutz**.
- Wird eine Unterhaltung sehr lang, fasst Jayth den älteren Teil zusammen, damit das Modell ihn nicht vergisst.

## Jayth Code (Projekte)

- Du gelangst dorthin mit **Code** in der Seitenleiste (Strg+2; Strg+1 führt zurück zu Chat). **Neues Projekt** oder
  **Ordner öffnen…**. Die Projekte erscheinen im Abschnitt **Projekte** der Seitenleiste, jedes mit seinen
  Unterhaltungen (Rechtsklick: **Projekt bearbeiten…** für Name, Ordner und die **Anweisungen des Projekts**; **Aus der
  Liste entfernen**).
- **Datei-Explorer** (Strg+B): Symbole nach Dateityp; Dateien, die der Agent geändert hat, tragen einen grünen Punkt.
  Rechtsklick: Öffnen, Mit Standard-App öffnen, Neue Datei…, Neuer Ordner…, Umbenennen, Pfad kopieren, Relativen Pfad
  kopieren, In den Papierkorb verschieben. **Zu einer Datei wechseln…** mit Strg+P.
- **Editor:** Tabs (Strg+S speichert, Strg+W schließt). Markdown, HTML, SVG und CSV öffnen sich in der **Vorschau**;
  zum Bearbeiten wechselst du zu **Code**. Word, Excel, PowerPoint und PDF werden schreibgeschützt angezeigt, Bilder mit
  Zoom. **Mit Standard-App öffnen** öffnet die Datei mit der App des Systems. **Zeilen umbrechen** (Alt+Z) für lange
  Zeilen.
- **Automatisches Speichern (Autospeichern):** Standardmäßig wird nach 1 Sekunde ohne Tippen gespeichert. Ändern lässt
  es sich unter **Einstellungen › Allgemein › Editor von Jayth Code** (auch beim Wechsel des Tabs oder Fensters, oder
  aus: dann mit Strg+S speichern). Ein Tab mit „●“ hat ungespeicherte Änderungen; mit „⚠“ konnte er nicht gespeichert
  werden (der Grund erscheint, wenn du mit der Maus darüberfährst).
- **Terminal** (Strg+`): das des Systems (PowerShell unter Windows, zsh/bash unter macOS und Linux), im Projektordner;
  ↑ ↓ blättert durch den Verlauf. Für Befehle, nicht für interaktive Programme.
- **Agent-Bereich** (Strg+L): der Chat des Projekts; der Agent arbeitet im Projektordner und liest die Regeln aus
  AGENTS.md, JAYTH.md oder CLAUDE.md, falls vorhanden.
- **Anordnung der Bereiche** (obere Leiste): Bereiche ein- oder ausblenden, Agent links oder rechts, Terminal unter
  oder rechts neben dem Editor und **Fokusmodus (nur Editor)** (Strg+Umschalt+M). Die Trennlinien lassen sich ziehen;
  ein Doppelklick auf eine klappt den Bereich daneben ein. Alles wird gespeichert.

## Jayth-Browser

Die Weltkugel-Schaltfläche in der oberen Leiste. Der Nutzer kann darin surfen oder den Agenten bitten, eine Website zu
nutzen (innerhalb einer Seite suchen, Formulare ausfüllen, Seiten mit JavaScript). Der Agent bedient ihn sichtbar, mit
seinem eigenen Mauszeiger und einem Leuchten an den Rändern, solange er die Kontrolle hat; der Nutzer kann jederzeit
eingreifen. Passwörter gibt immer der Nutzer selbst ein, und der Agent bittet um Bestätigung, bevor er etwas kauft,
bezahlt, veröffentlicht oder persönliche Daten sendet.

## Canvas

Für Webseiten, lange Dokumente, SVG-Diagramme oder Programme, die der Nutzer sehen möchte: Der Agent zeigt sie in einem
Bereich neben dem Chat („Im Canvas ansehen“), mit Vorschau und Code, Versionen (v1 von n) und der Möglichkeit, sie zu
speichern.

## Bilder

Der Agent kann neue Bilder (Fotos, Illustrationen, Logos, Symbole, Hintergründe, Titelbilder) direkt auf dem Computer
erstellen: wenn du ihn darum bittest oder wenn eine Aufgabe sie braucht (eine Website, eine Präsentation oder ein
Dokument bebildern). Er kann auch ein vorhandenes Bild bearbeiten (mit FLUX.2 [klein]). Während er es erstellt, siehst
du den aktuellen Schritt, die verbleibende Zeit und eine Vorschau; danach erscheint es groß im Chat mit **Öffnen** und
**Im Ordner anzeigen**. Es wird im Ordner „Bilder“ des Arbeitsordners (oder des Projekts) gespeichert oder in dem
Ordner, der in den Einstellungen gewählt ist.

- Es funktioniert ohne Internet und ohne externe Dienste, mit stable-diffusion.cpp (MIT) und einem Bildmodell mit
  freier Lizenz (Apache-2.0 oder MIT): **FLUX.2 [klein] 4B** (vielseitig und mit Text im Bild, die Empfehlung mit
  Grafikkarte), **Z-Image Turbo** (realistischer, besser mit Grafikkarte) oder **Segmind Vega RT** (das schnellste
  ohne Grafikkarte, in 4 Schritten, mit weniger Details). Bei „Automatisch“ wählt Jayth passend zum Computer.
  Ohne Grafikkarte braucht FLUX.2 etwa 11 Minuten pro Bild (gemessen auf einem Laptop mit einem i5 mit 4 Kernen).
- Beim ersten Mal muss es installiert werden (etwa 5 GB, nur einmal): mit **Installieren** auf der Karte, die im Chat
  erscheint, wenn der Agent es braucht (danach **Weiter**), oder unter **Einstellungen › Bilder**. Der Fortschritt ist
  sichtbar, der Vorgang lässt sich abbrechen und wird fortgesetzt, wenn er unterbrochen wird. **Entfernen** löscht
  seine Dateien.
- Zeit: mit Grafikkarte weniger als eine Minute pro Bild, ohne mehrere Minuten (deshalb werden Bilder ohne Grafikkarte
  mit 512 px erstellt). Ändern lässt sich das unter Einstellungen › Bilder › „Bildgröße“.
- Es wird nur genutzt, wenn das aktive Textmodell nicht selbst Bilder erstellen kann (derzeit kann das keines der
  Modelle, die mit llama.cpp laufen). Abschalten lässt es sich mit „Dem Agenten erlauben, Bilder zu erstellen“.
- Jedes Bild ist eine Schreibaktion: Je nach Berechtigungsmodus wird es vor dem Erstellen freigegeben, und es lässt sich
  rückgängig machen.
- Für Datendiagramme nutzt der Agent Python, für Diagramme SVG im Canvas.

## Wissen

Unter **Einstellungen › Wissen** wählst du Ordner (Notizen, Dokumente, Projekte), und der Agent durchsucht sie nach
Bedeutung, nicht nur nach exakten Wörtern („Was hat die Reparatur vom Wagen gekostet?“ findet die Notiz zur Rechnung
fürs Auto), ohne sie ganz lesen zu müssen: ideal für lokale Modelle, die nur wenig Gedächtnis der Unterhaltung haben.
Dafür nutzt er eine kleine Suche, die auf dem Computer läuft (Qwen3-Embedding 0.6B, 640 MB, einmaliger Download) und
Deutsch, Spanisch, Englisch, Portugiesisch und viele weitere Sprachen versteht. Unterstützt werden Text, Code, Markdown,
Word, PDF, PowerPoint und Excel.

- **Suche nach Bedeutung:** **Installieren** (einmalig).
- **Wissensordner:** **Ordner hinzufügen…** und **Entfernen**.
- **Index:** wie viele Dateien und Fragmente er enthält und wann er aktualisiert wurde; **Index aktualisieren** (liest
  nur Neues oder Geändertes erneut) und „Index beim Öffnen von Jayth aktualisieren“.
- Der Agent nutzt es nur, wenn es nötig ist (z. B. „laut meinen Notizen…“), und nennt, aus welcher Datei jede Angabe
  stammt.

## Computersteuerung und andere Programme

Der Agent kann Programme und Dateien öffnen, die Schaltflächen und Felder jedes Fensters lesen (Barrierefreiheit des
Systems), klicken, ziehen, tippen, Tastenkürzel drücken, Fenster verwalten, die Zwischenablage nutzen und Screenshots
vom Bildschirm oder von einem Fenster machen. Während er steuert, siehst du ein Leuchten an den Bildschirmrändern und
seinen Mauszeiger. Ein- oder ausschalten lässt es sich unter **Einstellungen › Werkzeuge › Computersteuerung
erlauben**. Unter macOS braucht Jayth die Berechtigungen **Bildschirmaufnahme** und **Bedienungshilfen**
(Systemeinstellungen › Datenschutz & Sicherheit). Unter Linux funktioniert es in X11-Sitzungen (unter Wayland ist die
globale Steuerung eingeschränkt); zum Auflisten von Fenstern wird `wmctrl` benötigt.

## Modelle

- **Modelle** (Profilmenü oder Einstellungen › Modelle › Modelle verwalten…): Liste der installierten Modelle mit Typ,
  Variante und Größe. **Dieses verwenden**, **Modell hinzufügen…**, **Finden…** (wenn du die Datei verschoben hast),
  **In einem Ordner suchen…**, **Ordner öffnen**, **Aus der Liste entfernen** und **Dateien löschen…**.
- **Modell hinzufügen** (Assistent): ein Katalog offener Modelle von Hugging Face, markiert danach, ob sie auf den
  Computer passen (Agent = nutzt Werkzeuge; Vision = versteht Bilder; Denkt nach = überlegt vor der Antwort), ein von
  Hand eingegebenes Repository (nutzer/Modell-GGUF), eine eigene .gguf-Datei oder ein Ordner mit dem Originalmodell
  (config.json + .safetensors), das Jayth auf dem Computer in GGUF umwandelt. Du wählst die Quantisierung (die
  empfohlene ist markiert) und, falls vorhanden, **Vision**, damit das Modell Bilder und Screenshots sieht.
- **API-Modelle…**: OpenAI, Claude, Gemini, Ollama, LM Studio oder ein anderer OpenAI-kompatibler Server. Auch unter
  **Einstellungen › Modelle › Anbieter** (URL, Modellname und Schlüssel).
- **Modell starten oder stoppen:** Modell-Chip › **Engine** oder die Schaltfläche **Modell starten** im Hinweis.
  Gestartet belegt es Speicher und antwortet sofort; gestoppt gibt es den Speicher frei.
- Downloads zeigen Prozent, Geschwindigkeit und Restzeit, werden fortgesetzt, wenn sie abbrechen, und mit SHA-256
  geprüft.
- Erscheint eine neue Version eines deiner Modelle, gibt Jayth Bescheid (abschalten unter Einstellungen › Über ›
  Neuigkeiten).

## Engine und Leistung

Jayth lädt die offizielle llama.cpp-Version herunter, die zum Computer passt: Metal auf Macs mit Apple Silicon, CUDA für
NVIDIA, Vulkan für AMD oder Intel Arc, oder CPU. Unter **Einstellungen › Leistung**: **Engine wechseln oder
aktualisieren…**, **Beim Starten des Modells vorwärmen**, **Gedächtnis der Unterhaltung (Kontext)** (standardmäßig
**Automatisch**: der gesamte Kontext, den das Modell ab Werk unterstützt, verringert, wenn sein Speicher nicht auf den
Computer passt; mit **Kontext komprimiert** passt doppelt so viel oder mehr hinein), **Modell stoppen nach Inaktivität
von**, und in den
**Engine-Einstellungen**: CPU-Threads, Layer auf der GPU (automatisch verteilt das Modell auf GPU und RAM), Batch-Größe,
Kontext komprimiert, Flash attention, Beschleunigung beim Schreiben, mmap, im RAM halten und der lokale Port. Änderungen
an der Engine werden beim Neustart des Modells wirksam (**Modell neu starten**). Das Log der Engine steht unter
**Einstellungen › Modell-Log**.

- **Für diesen Computer optimieren** (Einstellungen › Leistung): Statt zu schätzen, misst Jayth tatsächlich mit dem
  aktiven Modell (ein paar Minuten, währenddessen ist das Modell gestoppt): Es testet Threads und Flash attention mit
  llama-bench sowie die „Beschleunigung beim Schreiben“ (spekulatives Decoding: **MTP** für Modelle, die solche Layer
  mitbringen, wie Qwen 3.5 und 3.8, und **N-Gramme**, das das Umschreiben von Code oder Text beschleunigt) und übernimmt
  das Schnellste. Darunter steht das Ergebnis („liest … tok/s · schreibt … tok/s“). „Beschleunigung beim Schreiben“
  lässt sich in den Engine-Einstellungen auch von Hand wählen.
- **Speicher:** Beim Starten des Modells warnt Jayth, wenn es nicht auf den Computer passt (es wird sehr langsam, und
  eine kleinere Variante ist ratsam) oder wenn gerade andere Programme den Speicher belegen. Der Speicher, den llama.cpp
  für frühere Unterhaltungen vorhält, passt sich von selbst an das an, was übrig ist, damit er dem Modell nichts
  wegnimmt.

## Einstellungen

Du öffnest sie über das Profilmenü (**Einstellungen**). Änderungen werden automatisch gespeichert. Seiten und Optionen
(mit ihrem genauen Namen):
- **Allgemein:** „Sprache der Oberfläche“, „Design“, „Textgröße“, „Animationen (Einblenden von Nachrichten,
  Seitenleiste, Hinweise)“, „Titelleiste ins Fenster integriert“ (nur Windows).
  - **Editor von Jayth Code:** „Dateien automatisch speichern“.
  - **Start und Fenster:** Jayth beim Systemstart öffnen (minimiert im Infobereich), „Modell beim Öffnen von Jayth
    starten“, „Beim Schließen des Fensters im Infobereich weiterlaufen“, „Benachrichtige mich, wenn der Agent meine
    Freigabe braucht“, „Tastenkürzel für das Schnellfenster“.
- **Personalisierung:** „Wie möchtest du genannt werden?“, „Was sollte Jayth über dich wissen?“, „Wie soll geantwortet
  werden?“, „Sprache der Antworten“, „Zusätzliche Anweisungen für den Agenten“.
  - **Spracheingabe:** „Genauigkeit des Diktats“, „Sprache des Diktats“.
  - **Gedächtnis:** „Gedächtnis nutzen (Dinge über Unterhaltungen hinweg merken)“, die Liste der Erinnerungen
    (hinzufügen, bearbeiten oder löschen) und **Gesamtes Gedächtnis löschen**.
- **Modelle:** das aktive Modell, **Modelle verwalten…**, **Modell hinzufügen…**, **Einrichtungsassistent…** und
  „Ordner, in den Modelle heruntergeladen werden“.
  - **Anbieter:** „Welche Engine nutzt der Agent?“ (lokal oder externer Server), „URL des externen Servers (endet auf
    /v1)“, „Modellname auf diesem Server“, „API-Schlüssel (falls der Server einen verlangt)“ und **Verbindung testen**.
- **Generierung:** „Standardmäßig gründlich nachdenken (bessere Antworten, langsamer)“, „Sampling-Parameter“ (empfohlen
  für das aktive Modell oder benutzerdefiniert), „Temperatur“, „Maximale Länge jeder Antwort (Tokens)“.
  - **Erweitertes Sampling:** „Top-p“, „Top-k“, „Min-p“, „Wiederholungsstrafe“, „Seed“ und **Empfohlene Werte
    wiederherstellen**.
- **Leistung:** **Engine wechseln oder aktualisieren…**, „Beim Starten des Modells vorwärmen“, „Gedächtnis der
  Unterhaltung (Kontext)“, „Modell stoppen nach Inaktivität von“.
  - **Engine-Einstellungen:** „CPU-Threads“, „Layer auf der GPU“, „Batch-Größe“, „Kontext komprimiert“, „Flash
    attention“, „Modell mit mmap laden (schnellerer Start)“, „Modell im RAM halten (verhindert, dass das System es auf
    die Festplatte auslagert)“, „Lokaler Port der Engine“.
  - **Downloads:** „Gleichzeitige Verbindungen beim Herunterladen von Modellen“.
- **Agent und Berechtigungen:** „Standardberechtigungen“, „Arbeitsordner im Chat-Modus“, „Befehle, die ohne Nachfrage
  erlaubt sind“.
  - **Limits:** „Maximale Schritte pro Aufgabe“, „Maximale Zeit pro Befehl“, „Maximaler Text, den das Modell von jeder
    Aktion erhält“, „Screenshots und Bilder an das Modell senden (falls es Vision hat)“, „Letzte Bilder, die es sich
    merkt“.
- **Werkzeuge:** „Internetzugriff erlauben (suchen, Seiten lesen und herunterladen)“, „Computersteuerung erlauben (Maus,
  Tastatur, Screenshots)“, „Geladene Werkzeuge“ (standardmäßig nur die, die jede Aufgabe braucht: Der Agent hat die
  grundlegenden zur Hand und aktiviert die übrigen Gruppen – Web, Browser, PC-Steuerung, Dokumente, Python, Bilder,
  Kalender und jeden Connector –, wenn er sie braucht; so hat das lokale Modell mehr Gedächtnis und antwortet schneller).
  - **Verfügbare Werkzeuge:** Jedes Werkzeug des Agenten lässt sich einzeln abschalten.
  - **Websuche:** „Suchmaschine“ (automatisch mit DuckDuckGo und Wikipedia, Brave Search oder SearXNG),
    „Brave-Search-Schlüssel“, „SearXNG-URL“.
  - **Dienste mit deinem Konto:** Karten, um Online-Dienste zu verbinden (**Verbinden**, **Trennen**, **Google
    einrichten…**).
  - **MCP-Connectors:** Vorlagen, Connectors hinzufügen (**Hinzufügen und testen**), testen und entfernen.
- **Wissen:** Suche nach Bedeutung (**Installieren**), Ordner (**Ordner hinzufügen…**, **Entfernen**), Index (**Index
  aktualisieren**) und „Index beim Öffnen von Jayth aktualisieren“.
- **Bilder:** „Dem Agenten erlauben, Bilder zu erstellen“.
  - **Bildmodell:** „Gewähltes Modell“ (Automatisch, FLUX.2 [klein] 4B, Z-Image Turbo oder Segmind Vega RT), sein Status und **Installieren**, **Abbrechen** oder
    **Entfernen**.
  - **Erstellte Bilder:** „Bildgröße“ (Automatisch, 512, 768 oder 1024 px) und „Ordner, in dem sie gespeichert werden“.
- **Daten und Datenschutz:** der Datenordner (**Ordner öffnen**).
  - **Unterhaltungen:** **Unterhaltungen exportieren (Markdown)…**, Platz von ungenutzten Bildern freigeben und alle
    Unterhaltungen löschen.
- **Modell-Log:** das Log der llama.cpp-Engine (zur Diagnose) und **Aktualisieren**.
- **Tastenkürzel:** die Liste der Tastenkürzel.
- **Über:** Version, Autor und Lizenz (**Lizenz ansehen**, **Markenrichtlinie**), **Nach Updates suchen**, **Auf
  GitHub öffnen**.
  - **Neuigkeiten:** „Benachrichtige mich, wenn es eine neue Version von Jayth gibt“, „Updates im Hintergrund
    herunterladen und beim Schließen von Jayth installieren“, „Benachrichtige mich, wenn eine neue Version meiner Modelle
    erscheint“.
  - **Feedback:** **Fehler melden…** und **Verbesserung vorschlagen…**.

## Personalisierung und Gedächtnis

Unter **Personalisierung** sagst du dem Agenten, wie er dich nennen soll, was er über dich wissen soll, wie er antworten
soll (Stil), in welcher Sprache er antworten soll (Automatisch = die Sprache deiner Nachricht) und gibst ihm zusätzliche
Anweisungen. Das **Gedächtnis** bewahrt dauerhafte Vorlieben über Unterhaltungen hinweg (der Agent speichert sie, wenn
du sie ihm sagst, z. B. „ich nutze pnpm“); ansehen, bearbeiten oder löschen lassen sie sich unter Personalisierung ›
Gedächtnis, und es lässt sich abschalten. Der temporäre Chat nutzt es nicht.

## Assistenten und Fähigkeiten

Profilmenü › **Assistenten und Fähigkeiten**. Ein **Assistent** ist ein Agent mit eigenen Anweisungen und
Referenzdateien (z. B. „Stilkorrektur“); du wählst ihn mit **+ › Assistent verwenden** im Nachrichtenfeld. Eine
**Fähigkeit** ist ein Ablauf, den der Agent nutzt, wenn er zur Aufgabe passt (z. B. „Managementberichte verfassen und
als Word-Datei liefern“); im Tab Fähigkeiten lassen sie sich erstellen, importieren, aktivieren oder deaktivieren
(**Beispiele hinzufügen** bringt einige Muster mit).

## Geplante Aufgaben

Profilmenü › **Geplante Aufgaben**. Eine Aufgabe ist ein Auftrag, den der Agent zur festgelegten Zeit selbstständig
erledigt (Einmal, Täglich, Montag bis Freitag, Wöchentlich an den gewählten Tagen oder In Abständen), und er meldet sich, wenn er fertig ist: **Neue Aufgabe**, Name, was zu tun ist, wann, wie er handelt (Berechtigungen),
**Jetzt ausführen** und **Letztes Ergebnis ansehen**. Die Aufgaben laufen, solange Jayth geöffnet ist (auch im
Infobereich). Der Agent kann sie auch selbst planen, wenn du ihn darum bittest.

## Schnellfenster

Eine kleine Leiste, um Jayth aus jedem Programm heraus etwas zu fragen: Tastenkürzel **Strg+Alt+J** (ändern oder
deaktivieren unter Einstellungen › Allgemein › Tastenkürzel für das Schnellfenster) oder **Schnelle Frage** im
Infobereich. **Mit Screenshot** hängt ein Bild dessen an, was auf dem Bildschirm zu sehen war (Strg+S). Eingabetaste
sendet, Esc schließt.

## MCP-Connectors und Websuche

- **MCP-Connectors** (Einstellungen › Werkzeuge): erweitern die Werkzeuge des Agenten über den Standard Model Context
  Protocol (Dateien, Gedächtnis, Playwright-Browser, Git, Fetch, GitHub…). Es gibt Vorlagen, die das Formular
  ausfüllen; ein Connector kann ein Programm auf dem Computer sein (Befehl und Argumente, viele brauchen Node.js oder uv)
  oder ein entfernter Dienst (Adresse und Schlüssel). **Hinzufügen und testen** verbindet ihn; verlangt der Dienst eine
  Anmeldung, öffnet sich seine Seite (danach **Anmelden** oder **Abmelden** in seiner Zeile).
- **Dienste mit deinem Konto** (Einstellungen › Werkzeuge): alles optional; Jayth funktioniert lokal und ohne Internet.
  Es gibt Karten für Higgsfield (KI-Bilder und -Videos in der Cloud, mit deinen Credits), Notion, Canva, Gmail, Google
  Drive, Google Calendar, Linear, Jira und Confluence sowie Hugging Face (ohne Konto). **Verbinden** öffnet die Seite
  des Dienstes im Browser: Der Nutzer meldet sich dort an und erteilt die Berechtigung; Jayth sieht das Passwort nie und
  speichert die Berechtigung verschlüsselt auf dem Computer (sie erneuert sich von selbst). **Trennen** vergisst sie.
  Gmail, Drive und Calendar brauchen vorher **Google einrichten…**: einmalig in Google Cloud eine „OAuth-Client-ID“ vom
  Typ „Desktop-App“ erstellen (mit aktivierten MCP-APIs und der E-Mail-Adresse als Testnutzer) und die Client-ID und
  den Clientschlüssel einfügen; das gilt für alle drei.
- Wenn eine Aufgabe es erfordert, kann der Agent vorschlagen, einen Dienst zu verbinden: Seine Karte erscheint im Chat
  mit **Verbinden** und danach **Weiter**. Alles, was etwas im Konto ändert (senden, veröffentlichen, Credits
  ausgeben), braucht immer eine Freigabe, auch im Modus Automatisch; Lesen nicht.
- **Websuche:** standardmäßig DuckDuckGo; verlangt es ein Captcha, umgeht Jayth es nicht und nutzt Wikipedia. Für
  vollständige Suchen kannst du einen Brave-Search-Schlüssel oder eine eigene SearXNG-Instanz eintragen.

## Sprache der Oberfläche

Jayth gibt es auf Spanisch, Englisch, Portugiesisch (Brasilien), Französisch, Deutsch,
Italienisch, Japanisch und vereinfachtem Chinesisch. Beim ersten Start
nutzt es die Sprache des Systems (sonst Englisch); ändern lässt sie sich unter **Einstellungen › Allgemein › Sprache der Oberfläche**,
und Jayth bietet einen Neustart an, um sie anzuwenden. Die Sprache, in der der Agent antwortet, ist davon unabhängig:
standardmäßig die der Nachricht des Nutzers (Einstellungen › Personalisierung › Sprache der Antworten).

## Updates

Gibt es eine neue Version, lädt Jayth sie im Hintergrund herunter (die Schaltfläche in der Seitenleiste zeigt „Update
wird geladen… %“), ohne etwas zu unterbrechen. Danach wird die Schaltfläche zu **Zum Aktualisieren neu starten**:
Klickst du darauf, schließt sich Jayth, die neue Version wird installiert (mit einem kleinen Fenster „Jayth wird auf
Version … aktualisiert…“) und Jayth öffnet sich wieder. Klickst du nicht darauf, wird sie beim Schließen von Jayth
automatisch installiert. Beim Öffnen der neuen Version erscheint ein Hinweis mit einem Link zu den **Neuigkeiten**. Von
Hand suchen kannst du über Profilmenü › **Nach Updates suchen**, und den automatischen Download schaltest du unter
Einstellungen › Über › Neuigkeiten ab. Unterhaltungen, Einstellungen und Modelle bleiben beim Aktualisieren erhalten.

## Wo alles gespeichert wird

- **Einstellungen, Unterhaltungen, Engine und Modelle:** Windows `%LOCALAPPDATA%\Jayth`, macOS `~/Library/Application
  Support/Jayth`, Linux `~/.local/share/jayth` (der tatsächliche Pfad auf diesem Computer steht in den Daten dieser
  Version).
- **Arbeitsordner im Chat-Modus:** standardmäßig `Dokumente/Jayth`; ändern unter Einstellungen › Agent und
  Berechtigungen.
- **Modellordner:** ändern unter Einstellungen › Modelle. Bildmodelle liegen in dessen Unterordner `imagen`, die
  Bild-Engine neben der von llama.cpp (`runtime/imagen`).
- **Portabler Modus:** Eine Datei `portable.txt` neben dem Programm speichert alles in `userdata/` daneben (für einen
  USB-Stick).
- **Datenschutz:** Alles bleibt auf dem Computer; Jayth sendet keine Unterhaltungen oder Dateien an irgendeinen Server.
  Das Internet nutzt es nur, um Modelle und Engines herunterzuladen, nach Updates zu suchen und für die Web-Werkzeuge,
  die der Nutzer erlaubt (oder bei Nutzung eines API-Modells, das die Nachrichten dieser Unterhaltung erhält).
- **Deinstallieren:** Windows: Einstellungen › Apps › Jayth › Deinstallieren; macOS: Jayth in den Papierkorb ziehen;
  Linux: das AppImage löschen. Daten und Modelle werden beim Deinstallieren nicht gelöscht.

## Feedback und Hilfe

Profilmenü › **Feedback senden…** oder **Fehler melden…** (auch unter Einstellungen › Über): Der Nutzer prüft den Text,
bevor er ihn sendet. Unter jeder Antwort: **Ein Problem mit dieser Antwort melden**. Das Projekt liegt auf
https://github.com/Json-Tuiran/jayth.ai (Downloads unter Releases).

## Häufige Probleme

- **„Das Modell ist aus.“ oder es antwortet nicht:** auf **Modell starten** klicken (oder einfach schreiben: Jayth
  startet es selbst). Startet es nicht, steht der Grund im Hinweis und unter Einstellungen › Modell-Log; meist reicht
  der Speicher nicht: eine kleinere Quantisierung wählen, das **Gedächtnis der Unterhaltung (Kontext)** verringern oder
  **Kontext komprimiert** nutzen.
- **Es ist langsam:** Auf Computern ohne GPU brauchen große Modelle lange; ein kleineres Modell ausprobieren, den
  Aufwand auf Niedrig senken oder, mit einer NVIDIA-GPU, prüfen, ob die Engine CUDA ist (Einstellungen › Leistung ›
  Engine wechseln oder aktualisieren…).
- **Es findet das Modell nicht („Ich finde die Datei von … nicht mehr dort, wo sie war“):** auf **Danach suchen**
  klicken oder unter Modelle **Finden…** bzw. **In einem Ordner suchen…** verwenden.
- **Es sieht keine Bilder:** Das Modell braucht Vision (Vision-Projektor); beim Hinzufügen **Vision einschließen**
  ankreuzen. Einstellungen › Agent und Berechtigungen › Screenshots und Bilder an das Modell senden prüfen.
- **Es erstellt keine Bilder oder scheitert dabei:** den Generator unter Einstellungen › Bilder installieren und prüfen,
  ob „Dem Agenten erlauben, Bilder zu erstellen“ angehakt ist. Reicht der Speicher nicht, eine kleinere Größe oder
  FLUX.2 [klein] wählen und andere Programme schließen; Details zum letzten Versuch stehen im Log `imagen.log` im
  Datenordner.
- **Es kann das Internet oder die Maus nicht nutzen:** Einstellungen › Werkzeuge prüfen (Internetzugriff,
  Computersteuerung und die Liste der Werkzeuge).
- **Windows zeigt „Der Computer wurde durch Windows geschützt“:** Das Installationsprogramm ist noch nicht signiert:
  Weitere Informationen › Trotzdem ausführen. **macOS:** beim ersten Mal Rechtsklick auf Jayth › Öffnen.
- **Der Agent lässt nicht zu einer Nachricht zurückkehren:** warten, bis er fertig ist, oder ihn stoppen; bereits
  zusammengefasste Nachrichten lassen sich nicht zurückspulen (Neue Unterhaltung verwenden).
- **Ein Tab im Editor zeigt ⚠:** Er konnte nicht gespeichert werden (schreibgeschützte Datei oder geschützter Ordner);
  der Grund erscheint, wenn du mit der Maus über den Tab fährst.
