# Guide de Jayth

Ce guide décrit la version installée de Jayth : ce que fait chaque partie, où elle se trouve et comment l'utiliser. Les
noms des boutons et des menus sont ceux qui apparaissent dans l'interface (dans cette langue). Les données de cet
ordinateur (version, modèle actif, dossiers, raccourcis…) sont ajoutées à part, tirées de l'application elle-même au
moment de la consultation.

## Ce qu'est Jayth

Jayth est une application de bureau pour Windows, macOS et Linux qui transforme un modèle d'IA local (format GGUF, avec
llama.cpp) en un agent qui travaille sur l'ordinateur de l'utilisateur : il programme, crée et modifie des fichiers,
exécute des commandes, utilise d'autres programmes, navigue sur le web avec son propre navigateur, et lit et crée des
documents Word, Excel, PowerPoint et PDF. Tout se passe sur l'ordinateur et fonctionne sans internet une fois le modèle
téléchargé. L'utilisateur approuve chaque action (ou lui laisse carte blanche en mode automatique). Il peut aussi
utiliser des modèles par API (OpenAI, Claude, Gemini, Ollama…).
Créé par Ing. Jeison Tuiran. Logiciel libre sous licence GPL-3.0. Web : https://github.com/Json-Tuiran/jayth.ai

## La fenêtre principale

- **Barre latérale (à gauche) :** en haut, le bouton ≡ pour la masquer (Ctrl+Maj+S) et le sélecteur **Chat / Code**. En
  dessous, **Nouvelle conversation** (Ctrl+N), **Rechercher dans vos conversations** (Ctrl+K) et l'historique groupé par
  date (Aujourd'hui, Hier, 7 derniers jours… ; cliquez sur un groupe pour le replier). Clic droit sur une conversation :
  **Renommer** ou **Supprimer**. Tout en bas, le bouton de votre profil (**Votre profil et vos paramètres**) et, quand
  une nouvelle version est disponible, le bouton de mise à jour. Quand la barre est masquée, elle apparaît en survolant
  le bord gauche avec la souris.
- **Barre supérieure :** à gauche, l'état du modèle (p. ex. « ● Prêt · local »). À droite : **Temporaire** (chat
  temporaire), le globe (**Navigateur de Jayth**), **Disposition des panneaux**, le dossier (ouvre le dossier de
  travail) et **⋯ Plus d'options** (Renommer la conversation, Ouvrir le dossier de travail, Supprimer la conversation).
  Dans Jayth Code apparaissent aussi les boutons **Explorateur de fichiers** (Ctrl+B), **Terminal** (Ctrl+`) et
  **Panneau de l'agent** (Ctrl+L).
- **Menu de votre profil** (en bas de la barre latérale) : Paramètres, Personnalisation, Mémoire, Assistants et
  compétences, Tâches planifiées, Modèles, Modèles par API…, Raccourcis clavier, Envoyer des commentaires…, Signaler un
  bug…, Rechercher des mises à jour, À propos de Jayth et Quitter.
- **Zone de notification :** Afficher, Question rapide, Arrêter l'agent et Quitter.

## La zone de texte

- **Entrée** envoie ; **Maj+Entrée** insère un saut de ligne. Ctrl+V colle une image.
- Bouton **+** : Joindre des fichiers ou des documents…, Joindre une image…, Joindre une capture d'écran et **Utiliser
  un assistant**.
- **Micro :** dicter à la voix (la transcription se fait sur l'ordinateur ; le modèle de dictée se télécharge la
  première fois).
- **Pastille des autorisations** (p. ex. « Demander » ou « Automatique ») : change le mode d'autorisation de cette
  conversation.
- **Pastille du modèle** (p. ex. « Qwen3.8 27B · Faible ») : change de modèle, règle l'**Effort** (combien il réfléchit
  avant de répondre : Faible, Moyen, Élevé), télécharge ou ajoute des modèles (Télécharger ou ajouter un modèle…), Gérer
  les modèles…, Modèles par API… et **Moteur** (démarrer ou arrêter le modèle).
- Si le modèle est arrêté, un avis apparaît au-dessus de la zone de texte avec **Démarrer le modèle** (il peut se fermer
  avec la × ; il revient si la situation change). Si vous écrivez alors que le modèle est arrêté, Jayth le démarre et
  envoie le message dès qu'il est prêt.
- Pendant que l'agent travaille, le bouton d'envoi devient **Arrêter**.

## Modes d'autorisation

Ils se changent dans la pastille des autorisations de la zone de texte (pour cette conversation) ou dans **Paramètres ›
Agent et autorisations › Autorisations par défaut**. Il y en a cinq : Lecture seule, Planifier, Demander, Modifier les
fichiers et Automatique (la liste exacte avec leur description figure dans les données de cette version). Dans les modes
qui demandent, chaque action affiche **Autoriser** et **Refuser**. Les actions sensibles (supprimer, installer, `sudo`,
toucher au système ou à des chemins protégés) demandent toujours l'autorisation, même en Automatique. En **Planifier**,
l'agent étudie et propose un plan ; **Exécuter le plan** le met en œuvre (ou **Continuer à affiner**). Pour arrêter
instantanément le contrôle de la souris : amener le pointeur dans le coin supérieur gauche de l'écran.

## Ce que l'on voit pendant qu'il travaille

- Avant chaque action, l'agent dit en une phrase ce qu'il va faire. Chaque action est une ligne avec son icône et une
  animation pendant qu'elle s'exécute ; un clic dessus déplie le détail (la commande exacte, la modification, le
  résultat).
- **Réflexion :** la ligne « A réfléchi pendant… » se déplie pour afficher son raisonnement.
- **Captures :** quand il vérifie quelque chose en regardant l'écran ou une fenêtre, la capture apparaît dans le chat
  (cliquez dessus pour l'agrandir).
- **Plan :** dans les tâches longues, une liste de tâches fixée au-dessus de la zone de texte (Plan · n sur m).
- **Questions :** s'il a besoin d'une information, il pose une question avec des options ; on répond d'un clic ou avec
  **Autre réponse…**.
- Les fichiers que l'agent crée ou modifie peuvent s'ouvrir depuis le chat (chemins sous forme de liens), et les
  commandes que l'utilisateur doit exécuter apparaissent avec les boutons **Copier** et **Exécuter**.

## Actions sur les réponses

Sous chaque réponse : **Copier la réponse**, **Lire à voix haute**, **Régénérer la réponse**, **Signaler un problème
avec cette réponse** et, si elle a modifié des fichiers, **Annuler les modifications** (restaure tous les fichiers
modifiés dans cette réponse). Chaque action qui modifie des fichiers a aussi son propre bouton pour annuler uniquement
cette modification. À droite, les tokens, la vitesse et la mémoire de la conversation utilisée.

## Actions sur vos messages

En survolant l'un de vos messages avec la souris : **Copier le message**, **Modifier et renvoyer** (la modification se
fait dans le message même ; Ctrl+Entrée envoie, Échap annule), **Réessayer d'ici** et **⋯ Plus d'actions** : **Revenir à
ce point** (supprime ce message et tout ce qui suit et vous laisse le texte dans la zone de texte) et **Nouvelle
conversation à partir d'ici** (copie la conversation jusqu'à ce point ; l'originale ne change pas). Si l'agent a modifié
des fichiers après ce message, Jayth demande s'il faut **Annuler ces modifications** ou **Conserver les fichiers**. On
ne peut pas revenir à un message qui fait déjà partie du résumé d'une conversation très longue. Il faut attendre que
l'agent termine (ou l'arrêter).

## Conversations

- Elles s'enregistrent automatiquement dans l'historique. **Rechercher dans vos conversations** (Ctrl+K) cherche dans
  les titres et les messages.
- Le titre est donné par le modèle après la première réponse ; il se change avec **Renommer**.
- **Chat temporaire** (bouton **Temporaire** de la barre supérieure) : il n'est pas enregistré dans l'historique et
  n'utilise ni ne modifie la mémoire.
- Les erreurs du chat (p. ex. « Je ne peux pas me connecter au modèle ») proposent **Réessayer** et **Masquer cet
  avis**.
- Les exporter toutes en Markdown ou les supprimer : **Paramètres › Données et confidentialité**.
- Quand une conversation devient très longue, Jayth résume la partie ancienne pour que le modèle ne l'oublie pas.

## Jayth Code (projets)

- On y accède avec **Code** dans la barre latérale (Ctrl+2 ; Ctrl+1 revient à Chat). **Nouveau projet** ou **Ouvrir un
  dossier…**. Les projets apparaissent dans la section **Projets** de la barre latérale, chacun avec ses conversations
  (clic droit : **Modifier le projet…** pour le nom, le dossier et les **instructions du projet** ; **Retirer de la
  liste**).
- **Explorateur de fichiers** (Ctrl+B) : icônes par type ; les fichiers modifiés par l'agent portent un point vert. Clic
  droit : Ouvrir, Ouvrir avec son application, Nouveau fichier…, Nouveau dossier…, Renommer, Copier le chemin, Copier le
  chemin relatif, Mettre à la corbeille. **Aller à un fichier…** avec Ctrl+P.
- **Éditeur :** onglets (Ctrl+S enregistre, Ctrl+W ferme). Markdown, HTML, SVG et CSV s'ouvrent en **Aperçu** ; on passe
  à **Code** pour les modifier. Word, Excel, PowerPoint et PDF s'affichent en lecture seule ; les images, avec zoom.
  **Ouvrir avec son application** ouvre le fichier avec l'application du système. **Retour à la ligne** (Alt+Z) pour les
  lignes longues.
- **Enregistrement automatique (sauvegarde auto) :** par défaut, il enregistre après 1 seconde sans frappe. Se change
  dans **Paramètres › Général › Éditeur de Jayth Code** (aussi au changement d'onglet ou de fenêtre, ou désactivé :
  enregistrer avec Ctrl+S). Un onglet avec « ● » a des modifications non enregistrées ; avec « ⚠ », il n'a pas pu être
  enregistré (le motif s'affiche en le survolant avec la souris).
- **Terminal** (Ctrl+`) : celui du système (PowerShell sous Windows, zsh/bash sous macOS et Linux), dans le dossier du
  projet ; ↑ ↓ parcourt l'historique. Pour les commandes, pas pour les programmes interactifs.
- **Panneau de l'agent** (Ctrl+L) : le chat du projet ; l'agent travaille dans le dossier du projet et lit les règles de
  AGENTS.md, JAYTH.md ou CLAUDE.md s'ils existent.
- **Disposition des panneaux** (barre supérieure) : afficher ou masquer les panneaux, agent à gauche ou à droite,
  terminal en dessous ou à droite de l'éditeur et **Mode concentration (éditeur seul)** (Ctrl+Maj+M). Les séparateurs se
  déplacent en les faisant glisser ; un double clic sur l'un d'eux replie le panneau voisin. Tout est mémorisé.

## Navigateur de Jayth

Le bouton du globe dans la barre supérieure. L'utilisateur peut y naviguer ou demander à l'agent d'utiliser un site web
(chercher dans un site, remplir des formulaires, pages avec JavaScript). L'agent le pilote sous vos yeux, avec son
propre pointeur et une lueur sur les bords tant qu'il a le contrôle ; l'utilisateur peut intervenir quand il le
souhaite. Les mots de passe sont toujours saisis par l'utilisateur, et l'agent demande confirmation avant d'acheter, de
payer, de publier ou d'envoyer des données personnelles.

## Canevas

Pour les pages web, les documents longs, les diagrammes SVG ou les programmes que l'utilisateur veut voir : l'agent les
affiche dans un panneau à côté du chat (« Voir sur le canevas »), avec aperçu et code, versions (v1 sur n) et la
possibilité de les enregistrer.

## Images

L'agent peut créer de nouvelles images (photos, illustrations, logos, icônes, fonds, couvertures) sur l'ordinateur
même : quand vous le lui demandez ou quand une tâche en a besoin (illustrer un site web, une présentation ou un
document). Il modifie aussi une image que vous avez déjà (avec FLUX.2 [klein]). Pendant la création, on voit l'étape en
cours, le temps restant et un aperçu ; à la fin, l'image apparaît en grand dans le chat avec **Ouvrir** et **Afficher
dans le dossier**. Elle est enregistrée dans le dossier « images » du dossier de travail (ou du projet), ou dans celui
choisi dans les Paramètres.

- Fonctionne sans internet ni services externes, avec stable-diffusion.cpp (MIT) et un modèle d'image sous licence libre
  (Apache-2.0 ou MIT) : **FLUX.2 [klein] 4B** (polyvalent et capable d'écrire du texte dans l'image, le modèle
  recommandé avec une carte graphique), **Z-Image Turbo** (plus réaliste, mieux avec une carte graphique) ou **Segmind
  Vega RT** (le plus rapide sans carte graphique, en 4 étapes, avec moins de détails). En « Automatique », Jayth choisit
  selon l'ordinateur. Sans carte graphique, FLUX.2 met environ 11 minutes par image (mesuré sur un portable avec un i5 à
  4 cœurs).
- La première fois, il faut l'installer (environ 5 Go, une seule fois) : avec **Installer** sur la carte qui apparaît
  dans le chat quand l'agent en a besoin (ensuite, **Continuer**), ou dans **Paramètres › Images**. On voit la
  progression, on peut annuler et l'installation reprend si elle est interrompue. **Retirer** supprime ses fichiers.
- Durée : avec une carte graphique, moins d'une minute par image ; sans carte graphique, plusieurs minutes (c'est
  pourquoi, sans carte graphique, les images sont créées en 512 px). Se change dans Paramètres › Images › « Taille des
  images ».
- Il ne sert que si le modèle de texte actif ne crée pas d'images lui-même (aujourd'hui, aucun de ceux qui fonctionnent
  avec llama.cpp ne le fait). Se désactive avec « Autoriser l'agent à créer des images ».
- Chaque image est une action d'écriture : selon le mode d'autorisation, elle doit être approuvée avant d'être créée, et
  elle peut être annulée.
- Pour les graphiques de données, l'agent utilise Python, et pour les diagrammes, du SVG sur le canevas.

## Connaissances

Dans **Paramètres › Connaissances**, on choisit des dossiers (notes, documents, projets) et l'agent y cherche par le
sens, pas seulement par mots exacts (« combien a coûté la réparation de la bagnole ? » trouve la note de la facture de
la voiture), sans avoir à les lire en entier : idéal avec les modèles locaux, qui ont peu de mémoire de conversation. Il
le fait avec un petit moteur de recherche qui fonctionne sur l'ordinateur (Qwen3-Embedding 0.6B, 640 Mo, un seul
téléchargement) et comprend le français, l'espagnol, l'anglais, le portugais et bien d'autres langues. Il prend en
charge le texte, le code, Markdown, Word, PDF, PowerPoint et Excel.

- **Recherche par le sens :** **Installer** (une fois).
- **Dossiers de connaissances :** **Ajouter un dossier…** et **Retirer**.
- **Index :** combien de fichiers et de fragments il contient et quand il a été mis à jour ; **Mettre à jour l'index**
  (ne relit que ce qui est nouveau ou modifié) et « Mettre à jour l'index à l'ouverture de Jayth ».
- L'agent ne l'utilise que lorsque c'est nécessaire (p. ex. « d'après mes notes… ») et cite le fichier d'où vient chaque
  information.

## Contrôle de l'ordinateur et autres programmes

L'agent peut ouvrir des programmes et des fichiers, lire les boutons et les champs de n'importe quelle fenêtre
(accessibilité du système), cliquer, faire glisser, écrire, appuyer sur des raccourcis, gérer les fenêtres, utiliser le
presse-papiers et faire des captures de l'écran ou d'une fenêtre. Pendant qu'il a le contrôle, on voit une lueur sur les
bords de l'écran et son pointeur. Cela s'active ou se désactive dans **Paramètres › Outils › Autoriser le contrôle de
l'ordinateur**. Sous macOS, il faut accorder à Jayth les autorisations **Enregistrement de l'écran** et
**Accessibilité** (Réglages Système › Confidentialité et sécurité). Sous Linux, cela fonctionne dans les sessions X11
(sous Wayland, le contrôle global est limité) ; pour lister les fenêtres, il faut `wmctrl`.

## Modèles

- **Modèles** (menu du profil, ou Paramètres › Modèles › Gérer les modèles…) : liste des modèles installés avec leur
  type, leur variante et leur taille. **Utiliser celui-ci**, **Ajouter un modèle…**, **Localiser…** (si vous avez
  déplacé le fichier), **Rechercher dans un dossier…**, **Ouvrir le dossier**, **Retirer de la liste** et **Supprimer
  des fichiers…**.
- **Ajouter un modèle** (assistant) : catalogue de modèles ouverts de Hugging Face, marqués selon qu'ils tiennent ou non
  sur l'ordinateur (Agent = utilise des outils ; Vision = comprend les images ; Raisonnement = réfléchit avant de
  répondre), un dépôt saisi à la main (utilisateur/Modèle-GGUF), votre propre fichier .gguf ou un dossier avec le modèle
  original (config.json + .safetensors), que Jayth convertit en GGUF sur l'ordinateur. On choisit la quantification
  (celle recommandée est marquée) et, si elle existe, la **vision** pour que le modèle voie les images et les captures.
- **Modèles par API…** : OpenAI, Claude, Gemini, Ollama, LM Studio ou un autre serveur compatible avec OpenAI. Aussi
  dans **Paramètres › Modèles › Fournisseur** (URL, nom du modèle et clé).
- **Démarrer ou arrêter le modèle :** pastille du modèle › **Moteur**, ou le bouton **Démarrer le modèle** de l'avis.
  Démarré, il occupe de la mémoire et répond immédiatement ; arrêté, il la libère.
- Les téléchargements affichent le pourcentage, la vitesse et le temps restant, reprennent s'ils sont interrompus et
  sont vérifiés avec SHA-256.
- Si une nouvelle version de l'un de vos modèles est publiée, Jayth vous prévient (se désactive dans Paramètres › À
  propos › Nouveautés).

## Moteur et performances

Jayth télécharge la version officielle de llama.cpp adaptée à l'ordinateur : Metal sur Mac avec Apple Silicon, CUDA pour
NVIDIA, Vulkan pour AMD ou Intel Arc, ou CPU. Dans **Paramètres › Performances** : **Changer ou mettre à jour le
moteur…**, **Préchauffer au démarrage du modèle**, **Mémoire de la conversation (contexte)** (par défaut
**Automatique** : tout le contexte que le modèle accepte d'origine, réduit si sa mémoire ne tient pas sur l'ordinateur ;
avec **Contexte compressé**, il en tient deux fois plus, voire davantage), **Arrêter le modèle s'il est inutilisé
pendant**, et dans **Paramètres du moteur** : Threads CPU, Couches sur le GPU (l'automatique répartit le modèle entre le
GPU et la RAM), Taille de lot, Contexte compressé, Flash attention, Accélération de l'écriture, mmap, verrouillage en
RAM et le port local. Les changements du moteur s'appliquent au redémarrage du modèle (**Redémarrer le modèle**). Le
journal du moteur se trouve dans **Paramètres › Journal du modèle**.

- **Optimiser pour cet ordinateur** (Paramètres › Performances) : au lieu d'estimer, mesure réellement avec le modèle
  actif (quelques minutes, le modèle étant arrêté pendant ce temps) : teste les threads et flash attention avec
  llama-bench ainsi que l'« Accélération de l'écriture » (décodage spéculatif : **MTP**, pour les modèles qui intègrent
  ces couches comme Qwen 3.5 et 3.8, et **n-grammes**, qui accélère la réécriture de code ou de texte), et conserve le
  réglage le plus rapide. Le résultat s'affiche en dessous (« lit … tok/s · écrit … tok/s »). L'« Accélération de
  l'écriture » se choisit aussi à la main dans Paramètres du moteur.
- **Mémoire :** au démarrage du modèle, Jayth prévient s'il ne tient pas sur l'ordinateur (il sera très lent et mieux
  vaut une variante plus petite) ou si, à ce moment-là, d'autres programmes occupent la mémoire. La mémoire que
  llama.cpp garde des conversations précédentes s'ajuste d'elle-même à ce qui reste, pour ne pas en priver le modèle.

## Paramètres

Ils s'ouvrent depuis le menu du profil (**Paramètres**). Les changements s'enregistrent automatiquement. Pages et
options (avec leur nom exact) :
- **Général :** « Langue de l'interface », « Thème », « Taille du texte », « Animations (apparition des messages, barre
  latérale, notifications) », « Barre de titre intégrée à la fenêtre » (Windows uniquement).
  - **Éditeur de Jayth Code :** « Enregistrement automatique des fichiers ».
  - **Démarrage et fenêtre :** ouvrir Jayth au démarrage du système (réduit dans la zone de notification), « Démarrer le
    modèle à l'ouverture de Jayth », « À la fermeture de la fenêtre, continuer à fonctionner dans la zone de
    notification », « M'avertir quand l'agent a besoin de mon approbation », « Raccourci de la fenêtre rapide ».
- **Personnalisation :** « Comment voulez-vous qu'il vous appelle ? », « Que doit savoir Jayth sur vous ? », « Comment
  voulez-vous qu'il réponde ? », « Langue des réponses », « Instructions supplémentaires pour l'agent ».
  - **Voix :** « Précision de la dictée », « Langue de la dictée ».
  - **Mémoire :** « Utiliser la mémoire (retenir des choses entre les conversations) », la liste des souvenirs (ajouter,
    modifier ou supprimer) et **Effacer toute la mémoire**.
- **Modèles :** le modèle actif, **Gérer les modèles…**, **Ajouter un modèle…**, **Assistant de configuration…** et
  « Dossier où sont téléchargés les modèles ».
  - **Fournisseur :** « Quel moteur l'agent utilise-t-il ? » (local ou serveur externe), « URL du serveur externe (se
    termine par /v1) », « Nom du modèle sur ce serveur », « Clé API (si le serveur l'exige) » et **Tester la
    connexion**.
- **Génération :** « Réfléchir en profondeur par défaut (meilleures réponses, plus lent) », « Paramètres
  d'échantillonnage » (recommandés pour le modèle actif ou personnalisés), « Température », « Longueur maximale de
  chaque réponse (tokens) ».
  - **Échantillonnage avancé :** « Top-p », « Top-k », « Min-p », « Pénalité de répétition », « Graine » et **Rétablir
    les valeurs recommandées**.
- **Performances :** **Changer ou mettre à jour le moteur…**, « Préchauffer au démarrage du modèle », « Mémoire de la
  conversation (contexte) », « Arrêter le modèle s'il est inutilisé pendant ».
  - **Paramètres du moteur :** « Threads CPU », « Couches sur le GPU », « Taille de lot », « Contexte compressé »,
    « Flash attention », « Charger le modèle avec mmap (démarrage plus rapide) », « Verrouiller le modèle en RAM
    (empêche le système de le déplacer sur le disque) », « Port local du moteur ».
  - **Téléchargements :** « Connexions simultanées lors du téléchargement des modèles ».
- **Agent et autorisations :** « Autorisations par défaut », « Dossier de travail du mode Chat », « Commandes autorisées
  sans demander ».
  - **Limites :** « Nombre maximal d'étapes par tâche », « Durée maximale de chaque commande », « Texte maximal que le
    modèle reçoit de chaque action », « Envoyer les captures et images au modèle (s'il a la vision) », « Images récentes
    mémorisées ».
- **Outils :** « Autoriser l'accès à internet (rechercher, lire des pages et télécharger) », « Autoriser le contrôle de
  l'ordinateur (souris, clavier, captures) », « Outils chargés » (par défaut, uniquement ceux dont chaque tâche a
  besoin : l'agent a sous la main les outils de base et active les autres groupes — web, navigateur, contrôle du PC,
  documents, Python, images, agenda et chaque connecteur — quand il en a besoin ; ainsi, le modèle local a plus de
  mémoire et répond plus vite).
  - **Outils disponibles :** chaque outil de l'agent peut être désactivé séparément.
  - **Recherche web :** « Moteur de recherche » (automatique avec DuckDuckGo et Wikipédia, Brave Search ou SearXNG),
    « Clé Brave Search », « URL de SearXNG ».
  - **Services avec votre compte :** des fiches pour connecter des services en ligne (**Connecter**, **Déconnecter**,
    **Configurer Google…**).
  - **Connecteurs MCP :** modèles prédéfinis, ajouter (**Ajouter et tester**), tester et retirer des connecteurs.
- **Connaissances :** recherche par le sens (**Installer**), dossiers (**Ajouter un dossier…**, **Retirer**), index
  (**Mettre à jour l'index**) et « Mettre à jour l'index à l'ouverture de Jayth ».
- **Images :** « Autoriser l'agent à créer des images ».
  - **Modèle d'image :** « Modèle choisi » (Automatique, FLUX.2 [klein] 4B, Z-Image Turbo ou Segmind Vega RT), son état
    et **Installer**, **Annuler** ou **Retirer**.
  - **Images créées :** « Taille des images » (Automatique, 512, 768 ou 1024 px) et « Dossier où elles sont enregistrées ».
- **Données et confidentialité :** le dossier de données (**Ouvrir le dossier**).
  - **Conversations :** **Exporter les conversations (Markdown)…**, libérer l'espace occupé par les images inutilisées
    et supprimer toutes les conversations.
- **Journal du modèle :** le journal du moteur llama.cpp (pour diagnostiquer) et **Mettre à jour**.
- **Raccourcis clavier :** la liste des raccourcis.
- **À propos :** version, auteur et licence (**Voir la licence**, **Politique de marque**), **Rechercher des mises à
  jour**, **Ouvrir sur GitHub**.
  - **Nouveautés :** « M'avertir quand une nouvelle version de Jayth est disponible », « Télécharger les mises à jour en
    arrière-plan et les installer à la fermeture de Jayth », « M'avertir quand une nouvelle version de mes modèles est
    publiée ».
  - **Commentaires :** **Signaler un bug…** et **Suggérer une amélioration…**.

## Personnalisation et mémoire

Dans **Personnalisation**, on indique à l'agent comment vous appeler, ce qu'il doit savoir de vous, comment répondre
(style), dans quelle langue répondre (Automatique = la langue de votre message) et des instructions supplémentaires. La
**mémoire** conserve des préférences durables d'une conversation à l'autre (l'agent les enregistre quand vous les lui
dites, p. ex. « j'utilise pnpm ») ; elle se consulte, se modifie ou s'efface dans Personnalisation › Mémoire et peut
être désactivée. Le chat temporaire ne l'utilise pas.

## Assistants et compétences

Menu du profil › **Assistants et compétences**. Un **assistant** est un agent avec ses propres instructions et fichiers
de référence (p. ex. « Correcteur de style ») ; il se choisit avec **+ › Utiliser un assistant** dans la zone de texte.
Une **compétence** est une procédure que l'agent utilise quand elle correspond à la tâche (p. ex. « Rédiger des rapports
de synthèse et les livrer en Word ») ; les compétences se créent, s'importent, s'activent ou se désactivent dans
l'onglet Compétences (**Ajouter des exemples** en ajoute quelques-unes à titre d'exemple).

## Tâches planifiées

Menu du profil › **Tâches planifiées**. Une tâche est une mission que l'agent accomplit seul à l'heure prévue (Une fois,
Chaque jour, Du lundi au vendredi, Chaque semaine les jours choisis ou À intervalles) et il vous prévient quand il a
terminé : **Nouvelle tâche**, nom, ce qu'il doit faire, quand, comment il agit (autorisations), **Exécuter maintenant**
et **Voir le dernier résultat**. Les tâches s'exécutent tant que Jayth est ouvert (y compris dans la zone de
notification). L'agent peut aussi les planifier si on le lui demande.

## Fenêtre rapide

Une petite barre pour poser une question à Jayth depuis n'importe quel programme : raccourci **Ctrl+Alt+J** (se change
ou se désactive dans Paramètres › Général › Raccourci de la fenêtre rapide) ou **Question rapide** dans la zone de
notification. **Avec capture** joint une image de ce qui était à l'écran (Ctrl+S). Entrée envoie, Échap ferme.

## Connecteurs MCP et recherche web

- **Connecteurs MCP** (Paramètres › Outils) : ils étendent les outils de l'agent avec le standard Model Context Protocol
  (fichiers, mémoire, navigateur Playwright, Git, Fetch, GitHub…). Des modèles prédéfinis remplissent le formulaire ; il
  peut s'agir d'un programme de l'ordinateur (commande et arguments ; beaucoup ont besoin de Node.js ou de uv) ou d'un
  service distant (adresse et clé). **Ajouter et tester** les connecte ; si le service demande de se connecter, sa page
  s'ouvre (ensuite, **Se connecter** ou **Se déconnecter** sur sa ligne).
- **Services avec votre compte** (Paramètres › Outils) : tout est facultatif ; Jayth fonctionne en local et sans
  internet. Il existe des fiches pour Higgsfield (images et vidéos IA dans le cloud, avec vos crédits), Notion, Canva,
  Gmail, Google Drive, Google Calendar, Linear, Jira et Confluence, et Hugging Face (sans compte). **Connecter** ouvre
  la page du service dans le navigateur : l'utilisateur s'y connecte et donne son autorisation ; Jayth ne voit jamais le
  mot de passe et conserve l'autorisation chiffrée sur l'ordinateur (elle se renouvelle toute seule). **Déconnecter**
  l'oublie. Gmail, Drive et Calendar demandent d'abord **Configurer Google…** : créer une fois un « ID client OAuth » de
  type « Application de bureau » dans Google Cloud (avec les API MCP activées et l'adresse e-mail comme utilisateur
  test) et coller son ID et son secret ; il sert pour les trois.
- Si une tâche le nécessite, l'agent peut proposer de connecter un service : sa fiche apparaît dans le chat avec
  **Connecter** et, une fois la connexion faite, **Continuer**. Tout ce qui modifie quelque chose dans le compte
  (envoyer, publier, dépenser des crédits) demande toujours une approbation, même en mode Automatique ; la lecture, non.
- **Recherche web :** DuckDuckGo par défaut ; s'il demande un captcha, Jayth ne le contourne pas et utilise Wikipédia.
  Pour des recherches complètes, on peut indiquer une clé Brave Search ou sa propre instance de SearXNG.

## Langue de l'interface

Jayth est disponible en espagnol, anglais, portugais (Brésil), français, allemand et italien. La première fois, il
utilise la langue du système (à défaut, l'anglais) ; elle se change dans **Paramètres › Général › Langue de l'interface** et Jayth propose de
redémarrer pour l'appliquer. La langue dans laquelle répond l'agent est indépendante : par défaut, celle du message de
l'utilisateur (Paramètres › Personnalisation › Langue des réponses).

## Mises à jour

Quand une nouvelle version est disponible, Jayth la télécharge en arrière-plan (le bouton de la barre latérale affiche
« Téléchargement de la mise à jour… % ») sans rien interrompre. Une fois le téléchargement terminé, le bouton devient
**Redémarrer pour mettre à jour** : en cliquant dessus, Jayth se ferme, la nouvelle version s'installe (avec une petite
fenêtre « Mise à jour de Jayth vers la version… ») et il se rouvre. Si on ne clique pas, elle s'installe toute seule à
la fermeture de Jayth. À l'ouverture de la nouvelle version, un avis apparaît avec un lien vers les **Nouveautés**. On
peut vérifier manuellement depuis le menu du profil › **Rechercher des mises à jour** et désactiver le téléchargement
automatique dans Paramètres › À propos › Nouveautés. Les conversations, les paramètres et les modèles sont conservés
lors de la mise à jour.

## Où tout est enregistré

- **Paramètres, conversations, moteur et modèles :** Windows `%LOCALAPPDATA%\Jayth`, macOS `~/Library/Application
  Support/Jayth`, Linux `~/.local/share/jayth` (le chemin réel de cet ordinateur figure dans les données de cette
  version).
- **Dossier de travail du mode Chat :** par défaut `Documents/Jayth` ; se change dans Paramètres › Agent et
  autorisations.
- **Dossier des modèles :** se change dans Paramètres › Modèles. Les modèles d'image vont dans son sous-dossier
  `imagen`, et le moteur d'images, à côté de celui de llama.cpp (`runtime/imagen`).
- **Mode portable :** un fichier `portable.txt` à côté du programme enregistre tout dans `userdata/`, juste à côté (pour
  une clé USB).
- **Confidentialité :** tout reste sur l'ordinateur ; Jayth n'envoie ni conversations ni fichiers à aucun serveur. Il
  n'utilise internet que pour télécharger des modèles et des moteurs, rechercher des mises à jour et pour les outils web
  que l'utilisateur autorise (ou lorsqu'on utilise un modèle par API, qui reçoit les messages de cette conversation).
- **Désinstaller :** Windows, Paramètres › Applications › Jayth › Désinstaller ; macOS, faire glisser Jayth dans la
  Corbeille ; Linux, supprimer l'AppImage. Les données et les modèles ne sont pas supprimés lors de la désinstallation.

## Commentaires et aide

Menu du profil › **Envoyer des commentaires…** ou **Signaler un bug…** (aussi dans Paramètres › À propos) :
l'utilisateur relit le texte avant de l'envoyer. Sous chaque réponse, **Signaler un problème avec cette réponse**. Le
projet se trouve sur https://github.com/Json-Tuiran/jayth.ai (téléchargements dans Releases).

## Problèmes fréquents

- **« Le modèle est arrêté » ou il ne répond pas :** cliquer sur **Démarrer le modèle** (ou écrire : Jayth le démarre
  tout seul). S'il ne démarre pas, le motif apparaît dans l'avis et dans Paramètres › Journal du modèle ; c'est souvent
  un manque de mémoire : choisir une quantification plus petite, réduire la **Mémoire de la conversation (contexte)** ou
  utiliser le **Contexte compressé**.
- **C'est lent :** sur les ordinateurs sans GPU, les grands modèles prennent du temps ; essayer un modèle plus petit,
  baisser l'effort à Faible ou, avec un GPU NVIDIA, vérifier que le moteur est CUDA (Paramètres › Performances › Changer
  ou mettre à jour le moteur…).
- **Il ne trouve pas le modèle (« Je ne trouve pas le fichier… ») :** cliquer sur **Le chercher** ou, dans Modèles, sur
  **Localiser…** ou **Rechercher dans un dossier…**.
- **Il ne voit pas les images :** le modèle a besoin de la vision (projecteur) ; en l'ajoutant, cocher **Inclure la
  vision**. Vérifier Paramètres › Agent et autorisations › Envoyer les captures et images au modèle.
- **Il ne crée pas d'images ou échoue en les créant :** installer le générateur dans Paramètres › Images et vérifier que
  « Autoriser l'agent à créer des images » est coché. S'il manque de mémoire, choisir une taille plus petite ou FLUX.2
  [klein] et fermer d'autres programmes ; le détail de la dernière tentative se trouve dans le journal `imagen.log` du
  dossier de données.
- **Il ne peut pas utiliser internet ou la souris :** vérifier Paramètres › Outils (accès à internet, contrôle de
  l'ordinateur et liste des outils).
- **Windows affiche « Windows a protégé votre ordinateur » :** le programme d'installation n'est pas encore signé :
  Informations complémentaires › Exécuter quand même. **macOS :** la première fois, clic droit sur Jayth › Ouvrir.
- **L'agent ne permet pas de revenir à un message :** attendre qu'il termine ou l'arrêter ; les messages déjà résumés ne
  peuvent pas être rembobinés (utiliser Nouvelle conversation).
- **Un onglet de l'éditeur affiche ⚠ :** il n'a pas pu être enregistré (fichier en lecture seule ou dossier protégé) ;
  le motif s'affiche en survolant l'onglet avec la souris.
