# Jayth guide

This guide describes the installed version of Jayth: what each part does, where it is and how to use it. The names of
buttons and menus are the ones shown in the interface (in this language). This computer's data (version, active model,
folders, shortcuts…) is added separately, taken from the app itself at the time of the lookup.

## What Jayth is

Jayth is a desktop application for Windows, macOS and Linux that turns a local AI model (GGUF format, with llama.cpp)
into an agent that works on the user's computer: it programs, creates and edits files, runs commands, uses other apps,
browses the web with its own browser, and reads and creates Word, Excel, PowerPoint and PDF documents. Everything
happens on the computer and works offline once the model is downloaded. The user approves each action (or gives it free
rein in automatic mode). It can also use models through an API (OpenAI, Claude, Gemini, Ollama…).
Created by Ing. Jeison Tuiran. Free software licensed under GPL-3.0. Web: https://github.com/Json-Tuiran/jayth.ai

## The main window

- **Sidebar (left):** at the top, the ≡ button to hide it (Ctrl+Shift+S) and the **Chat / Code** selector.
  Below, **New conversation** (Ctrl+N), **Search your conversations** (Ctrl+K) and the history grouped by date
  (Today, Yesterday, Last 7 days…; click a group to collapse it). Right-click a conversation: **Rename** or
  **Delete**. At the very bottom, your profile button (**Your profile and settings**) and, when there's a new version,
  the update button. With the sidebar hidden, it peeks out when you hover over the left edge.
- **Top bar:** on the left, the model status (e.g. “● Ready · local”). On the right: **Temporary**
  (temporary chat), the globe (**Jayth browser**), **Panel layout**, the folder (opens the working
  folder) and **⋯ More options** (Rename conversation, Open working folder, Delete conversation). In Jayth Code
  the **File explorer** (Ctrl+B), **Terminal** (Ctrl+`) and **Agent panel** (Ctrl+L) buttons also
  appear.
- **Your profile menu** (at the bottom of the sidebar): Settings, Personalization, Memory, Assistants and skills,
  Scheduled tasks, Models, API models…, Keyboard shortcuts, Send feedback…, Report a bug…,
  Check for updates, About Jayth and Quit.
- **System tray:** Show, Quick question, Stop agent and Quit.

## The message box

- **Enter** sends; **Shift+Enter** inserts a line break. Ctrl+V pastes an image.
- **+** button: Attach files or documents…, Attach image…, Attach screenshot and **Use an assistant**.
- **Microphone:** dictate by voice (transcribed on the computer; the dictation model is downloaded the first time).
- **Permissions chip** (e.g. “Ask” or “Automatic”): changes the permission mode for this conversation.
- **Model chip** (e.g. “Qwen3.8 27B · Low”): switches models, sets the **Effort** (how much it reasons before
  answering: Low, Medium, High), downloads or adds models (Download or add a model…), Manage models…, API models…
  and **Engine** (start or stop the model).
- If the model is off, a notice with **Start model** appears above the box (it can be closed with the ×; it comes
  back if the situation changes). If you type while the model is off, Jayth starts it and sends the message when it's
  ready.
- While the agent works, the send button turns into **Stop**.

## Permission modes

They're changed in the permissions chip of the message box (for that conversation) or in **Settings › Agent and
permissions › Default permissions**. There are five: Read only, Plan, Ask, Edit files and Automatic (the exact list
with descriptions is in this version's data). In the modes that ask, each action shows **Allow** and
**Deny**. Sensitive actions (deleting, installing, `sudo`, touching the system or protected paths) always ask for
permission, even in Automatic. In **Plan** the agent researches and proposes a plan; **Run the plan** carries it out
(or **Keep refining**). To instantly stop mouse control: move the pointer to the top-left corner of the
screen.

## What you see while it works

- Before each action the agent says in one sentence what it's going to do. Each action is a line with its icon and an
  animation while it runs; clicking it expands the details (the exact command, the change, the result).
- **Thinking:** the “Thought for…” line expands to show its reasoning.
- **Screenshots:** when it checks something by looking at the screen or a window, the screenshot appears in the chat
  (click to see it full size).
- **Plan:** in long tasks, a task list pinned above the message box (Plan · n of m).
- **Questions:** if it needs some information, it asks with options; you answer with a click or with **Another
  answer…**.
- Files the agent creates or changes can be opened from the chat (paths as links), and commands the user needs to
  run appear with **Copy** and **Run** buttons.

## Actions on responses

Below each response: **Copy response**, **Read aloud**, **Regenerate response** and **Report a problem with this response**; on the right, the tokens it wrote and their
speed. If the response changed files, the **Changed 2 files** card appears below it with each file, its added and removed
lines and a note (“new”, “to the Recycle Bin”, “moved to …”): a click opens it and its button restores it to how it was before that
response; with two or more, **Undo all**. Each action that changes files also has its own button to undo just that
change. When the agent used tools, the “Worked for 3 min 12 s” line separates what it did from its response.

## While it works: writing to it, permissions and notifications

- **Writing to it without stopping it:** while it works you can type and send (Enter or the send button that appears
  next to **Stop**). The message waits in a queue above the text box (with × to remove it) and the agent sees it on its
  next step; in the chat it shows the note “You wrote this while it was working; it saw it here”. If it is stopped first, the text goes back to the box.
- **Grouped steps:** what it thinks between actions (“Thought for a moment”) goes inside the group of actions; when it finishes, the
  group folds into one line that expands with a click. At the top, the status shows how long it has been working
  (“Working · local · 1:12”).
- **Permissions:** besides **Allow** and **Deny**, the field “Or tell it what to do instead and press Enter…” denies the action and passes the instruction
  to the agent; below the action it shows “You asked: “…””. “Always “…” here” is not offered for sensitive actions or for actions on
  connected accounts: those are confirmed every time.
- **Plan:** when you press **Run the plan**, the chat shows the marker “You approved the plan: running it step by step”.
- **Computer control:** while it uses the mouse and keyboard, a notice at the top of the screen has **Pause** (the agent
  waits and the user can use the mouse; then **Resume**) and **Stop**. If the agent is about to click where the
  notice is, the notice moves out of the way. Moving the pointer to the top-left corner also stops it.
- **Notifications outside the window:** if it is waiting for a permission or an answer while Jayth is in the background,
  the taskbar icon flashes and a notification appears; if a task longer than 15 seconds finishes while the user is
  looking at something else, it also notifies (clicking the notification opens that conversation).

## Conversation memory (context)

Next to the microphone in the message box, a ring shows how much of the model's memory the conversation uses: accent
color while there is room, amber from 70 % (with the percentage) and red from 85 %. At 70 % Jayth trims old tool outputs
(it keeps their beginning; the last three stay whole). If that's not enough, at 85 % the model summarizes the older part:
everything before the user's last message or, in a single very long task, its first steps (the latest ones stay as they
are). The size of the summary adapts to the model's memory. Clicking the ring shows how much is used, what Jayth will do,
**Summarize now** and **Start a new conversation**. The notice left by the summary has **Show the summary**. On computers without a graphics card,
summarizing can take a few minutes.

## Actions on your messages

When you hover over one of your messages: **Copy message**, **Edit and resend** (edited right in the message;
Ctrl+Enter sends, Esc cancels), **Retry from here** and **⋯ More actions**: **Go back to this point** (removes that
message and everything after it and leaves its text in the box) and **New conversation from here** (copies the
conversation up to that point; the original doesn't change). If the agent changed files after that message, Jayth
asks whether to **Undo those changes** or **Keep the files**. You can't go back to a message that is already inside
the summary of a very long conversation. You have to wait for the agent to finish (or stop it).

## Conversations

- They're saved automatically in the history. **Search your conversations** (Ctrl+K) searches titles and messages.
- The model sets the title after the first response; change it with **Rename**.
- **Temporary chat** (**Temporary** button in the top bar): isn't saved to history and doesn't use or change memory.
- Chat errors (e.g. “Can't connect to the model”) come with **Retry** and **Remove this notice**.
- Export all of them to Markdown or delete them: **Settings › Data and privacy**.
- When a conversation gets very long, Jayth summarizes the older part so the model doesn't forget it.

## Jayth Code (projects)

- Enter it with **Code** in the sidebar (Ctrl+2; Ctrl+1 goes back to Chat). **New project** or **Open folder…**.
  Projects appear in the **Projects** section of the sidebar, each with its conversations (right-click:
  **Edit project…** for the name, the folder and the **project instructions**; **Remove from list**).
- **File explorer** (Ctrl+B): icons by type; files the agent changed have a green dot. Right-click: Open, Open with
  its app, New file…, New folder…, Rename, Copy path, Copy relative path, Move to Trash. **Go to a file…** with
  Ctrl+P.
- **Editor:** tabs (Ctrl+S saves, Ctrl+W closes). Markdown, HTML, SVG and CSV open in **Preview**; switch to **Code**
  to edit. Word, Excel, PowerPoint and PDF are shown read-only; images, with zoom. **Open with its app** opens the file
  with the system app. **Wrap lines** (Alt+Z) for long lines.
- **Save files automatically (autosave):** by default it saves after 1 second without typing. Change it in
  **Settings › General › Jayth Code editor** (also when switching tabs or windows, or off: save with Ctrl+S). A tab
  with “●” has unsaved changes; with “⚠”, it couldn't be saved (the reason shows on hover).
- **Terminal** (Ctrl+`): the system one (PowerShell on Windows, zsh/bash on macOS and Linux), inside the project
  folder; ↑ ↓ goes through the history. For commands, not for interactive programs.
- **Agent panel** (Ctrl+L): the project chat; the agent works inside the project folder and reads the rules in
  AGENTS.md, JAYTH.md or CLAUDE.md if they exist.
- **Panel layout** (top bar): show or hide panels, agent on the left or on the right, terminal below or to the right
  of the editor, and **Focus mode (editor only)** (Ctrl+Shift+M). Dividers can be dragged; double-click one to
  collapse the panel next to it. Everything is remembered.

## Jayth browser

The globe button in the top bar. The user can browse in it or ask the agent to use a website (search within a site,
fill in forms, pages with JavaScript). The agent drives it in plain view, with its own pointer and a glow around the
edges while it has control; the user can step in at any time. Passwords are always typed by the user, and the agent
asks for confirmation before buying, paying, publishing or sending personal data.

## Canvas

For web pages, long documents, SVG diagrams or programs the user wants to see: the agent shows them in a panel next
to the chat (“View on canvas”), with preview and code, versions (v1 of n) and the option to save them.

## Images

The agent can create new images (photos, illustrations, logos, icons, backgrounds, covers) on the computer itself:
when you ask for one or when a task needs it (illustrating a website, a presentation or a document). It can also
modify an image you already have (with FLUX.2 [klein]). While it works you see the current step, the time left and a
preview; when it's done the image appears large in the chat with **Open** and **Show in folder**. It's saved in the
“images” folder of the working folder (or of the project), or in the one chosen in Settings.

- It works without internet or external services, with stable-diffusion.cpp (MIT) and an image model with a free
  license (Apache-2.0 or MIT): **FLUX.2 [klein] 4B** (versatile and with text inside the image, the recommended one
  with a graphics card), **Z-Image Turbo** (more realistic, better with a graphics card) or **Segmind Vega RT** (the
  fastest without a graphics card, in 4 steps, with less detail). In “Automatic”, Jayth chooses based on
  the computer. Without a graphics card, FLUX.2 takes about 11 minutes per image (measured on a laptop with a 4-core i5).
- The first time it has to be installed (about 5 GB, only once): with **Install** on the card that appears in the chat
  when the agent needs it (then **Continue**), or in **Settings › Images**. You see the progress, you can cancel, and
  it resumes if interrupted. **Remove** deletes its files.
- Time: with a graphics card, under a minute per image; without one, several minutes (that's why, without a graphics
  card, images are made at 512 px). Change it in Settings › Images › “Image size”.
- It's only used if the active text model can't create images by itself (today none of the ones that run on llama.cpp
  can). Turn it off with “Allow the agent to create images”.
- Each image is a writing action: depending on the permission mode it's approved before it's created, and it can be
  undone.
- For data charts the agent uses Python, and for diagrams, SVG on the canvas.

## Knowledge

In **Settings › Knowledge** you choose folders (notes, documents, projects) and the agent searches them by meaning,
not just exact words (“how much did fixing the car cost?” finds the note about the car's invoice), without having to
read them whole: ideal with local models, which have little conversation memory. It does this with a small search
model that runs on the computer (Qwen3-Embedding 0.6B, 640 MB, downloaded once) and understands Spanish, English,
Portuguese and many more languages. It supports text, code, Markdown, Word, PDF, PowerPoint and Excel.

- **Search by meaning:** **Install** (once).
- **Knowledge folders:** **Add folder…** and **Remove**.
- **Index:** how many files and fragments it has and when it was updated; **Update the index** (only rereads what's new
  or changed) and “Update the index when Jayth opens”.
- The agent uses it only when needed (e.g. “according to my notes…”) and cites which file each fact comes from.

## Computer control and other apps

The agent can open programs and files, read the buttons and fields of any window (system accessibility), click,
drag, type, press shortcuts, manage windows, use the clipboard and take screenshots of the screen or of a window.
While it's in control, you see a glow around the edges of the screen and its pointer. Turn it on or off in
**Settings › Tools › Allow computer control**. On macOS, Jayth needs the **Screen Recording** and **Accessibility**
permissions (System Settings › Privacy & Security). On Linux it works in X11 sessions (on Wayland global control is
limited); listing windows requires `wmctrl`.

## Models

- **Models** (profile menu, or Settings › Models › Manage models…): list of installed models with their type,
  variant and size. **Use this one**, **Add model…**, **Locate…** (if you moved the file), **Search in a folder…**,
  **Open folder**, **Remove from list** and **Delete files…**.
- **Add a model** (wizard): catalog of open models from Hugging Face marked according to whether they fit on the
  computer (Agent = uses tools; Vision = understands images; Reasoning = thinks before answering), a repository typed
  by hand (user/Model-GGUF), your own .gguf file, or a folder with the original model (config.json + .safetensors),
  which Jayth converts to GGUF on the computer. You pick the quantization (the recommended one is marked) and, if
  available, **vision** so the model can see images and screenshots.
- **API models…**: OpenAI, Claude, Gemini, Ollama, LM Studio or another OpenAI-compatible server. Also in
  **Settings › Models › Provider** (URL, model name and key).
- **Start or stop the model:** model chip › **Engine**, or the **Start model** button in the notice. When it's on,
  it takes up memory and responds instantly; turning it off frees that memory.
- Downloads show percentage, speed and time remaining, resume if interrupted, and are verified with SHA-256.
- If a new version of one of your models is released, Jayth lets you know (turn it off in Settings › About › Updates).

## Engine and performance

Jayth downloads the official llama.cpp build suited to the computer: Metal on Macs with Apple Silicon, CUDA for
NVIDIA, Vulkan for AMD or Intel Arc, or CPU. In **Settings › Performance**: **Change or update the engine…**, **Warm
up when starting the model**, **Conversation memory (context)** (by default **Automatic**: all the context the model
supports out of the box, reduced if its memory doesn't fit on the computer; with **Compressed context** twice as much
or more fits), **Stop the model if unused for**, and in
**Engine settings**: CPU threads, Threads for reading (automatic: without a graphics card it reads with all the processor's threads), GPU layers (automatic splits the model between GPU and RAM), Batch size,
Compressed context, Flash attention, Writing speed-up, mmap, lock in RAM and the local port. Engine changes apply when the model
restarts (**Restart model**). The engine log is in **Settings › Model log**.

- **Optimize for this computer** (Settings › Performance): instead of estimating, it actually measures with the active
  model (a few minutes, with the model stopped meanwhile): it tests threads and flash attention with llama-bench and
  the “Writing speed-up” (speculative decoding: **MTP**, for models that include those layers such as Qwen 3.5 and 3.8,
  and **n-grams**, which speeds up rewriting code or text), and keeps the fastest. The result is shown below it
  (“reads … tok/s · writes … tok/s”). “Writing speed-up” can also be chosen by hand in Engine settings.
- **Memory:** when the model starts, Jayth warns if it doesn't fit on the computer (it will be very slow and a smaller
  variant is better) or if other programs are using the memory at that moment. The memory llama.cpp keeps from earlier
  conversations adjusts itself to what's left over, so it doesn't take it from the model.

## Settings

Open them from the profile menu (**Settings**). Changes are saved automatically. Pages and options (with their exact
names):
- **General:** “Interface language”, “Theme”, “Text size”, “Animations (message appearance, sidebar, notices)”,
  “Title bar built into the window” (Windows only).
  - **Jayth Code editor:** “Save files automatically”.
  - **Startup and window:** open Jayth when the system starts (minimized to the tray), “Start the model when Jayth
    opens”, “When closing the window, keep running in the system tray”, “Notify me when the agent needs my
    approval”, “Quick window shortcut”.
- **Personalization:** “What should it call you?”, “What should Jayth know about you?”, “How do you want it to
  respond?”, “Response language”, “Additional instructions for the agent”.
  - **Voice:** “Dictation accuracy”, “Dictation language”.
  - **Memory:** “Use memory (remember things across conversations)”, the list of memories (add, edit or delete) and
    **Clear all memory**.
- **Models:** the active model, **Manage models…**, **Add model…**, **Setup wizard…** and “Folder where models are
  downloaded”.
  - **Provider:** “Which engine does the agent use?” (local or external server), “External server URL (ends in
    /v1)”, “Model name on that server”, “API key (if the server requires it)” and **Test connection**.
- **Generation:** “Think deeply by default (better answers, slower)”, “Sampling parameters” (recommended for the
  active model or custom), “Temperature”, “Maximum length of each response (tokens)”.
  - **Advanced sampling:** “Top-p”, “Top-k”, “Min-p”, “Repetition penalty”, “Seed” and **Reset to recommended
    values**.
- **Performance:** **Change or update the engine…**, “Warm up when starting the model”, “Conversation memory
  (context)”, “Stop the model if unused for”.
  - **Engine settings:** “CPU threads”, “Threads for reading”, “GPU layers”, “Batch size”, “Compressed context”, “Flash attention”, “Load
    the model with mmap (faster startup)”, “Lock the model in RAM (keeps the system from moving it to disk)”,
    “Engine local port”.
  - **Downloads:** “Simultaneous connections when downloading models”.
- **Agent and permissions:** “Default permissions”, “Chat mode working folder”, “Commands allowed without asking”.
  - **Limits:** “Maximum steps per task”, “Maximum time per command”, “Maximum text the model receives from each
    action”, “Send screenshots and images to the model (if it has vision)”, “Recent images it remembers”.
- **Tools:** “Allow internet access (search, read pages and download)”, “Allow computer control (mouse, keyboard,
  screenshots)”, “Tools that are loaded” (by default, only the ones each task needs: the agent has the basic ones at hand
  and turns on the other groups —web, browser, computer control, documents, Python, images, schedule and each
  connector— when it needs them; this leaves a local model more memory and makes it answer sooner).
  - **Available tools:** each of the agent's tools can be turned off separately.
  - **Web search:** “Search engine” (automatic with DuckDuckGo and Bing, no key needed; Brave Search or SearXNG), “Brave
    Search key”, “SearXNG URL”.
  - **Services with your account:** cards to connect online services (**Connect**, **Disconnect**, **Set up
    Google…**).
  - **MCP connectors:** templates, add (**Add and test**), test and remove connectors.
- **Knowledge:** search by meaning (**Install**), folders (**Add folder…**, **Remove**), index (**Update the index**)
  and “Update the index when Jayth opens”.
- **Images:** “Allow the agent to create images”.
  - **Image model:** “Chosen model” (Automatic, FLUX.2 [klein] 4B, Z-Image Turbo or Segmind Vega RT), its status and **Install**, **Cancel** or
    **Remove**.
  - **Created images:** “Image size” (Automatic, 512, 768 or 1024 px) and “Folder where they're saved”.
- **Data and privacy:** the data folder (**Open folder**).
  - **Conversations:** **Export conversations (Markdown)…**, free up space from unused images and delete all
    conversations.
- **Model log:** the llama.cpp engine log (for diagnostics) and **Update**.
- **Keyboard shortcuts:** the list of shortcuts.
- **About:** version, author and license (**View license**, **Trademark policy**), **Check for updates**,
  **Open on GitHub**.
  - **Updates:** “Notify me when there's a new version of Jayth”, “Download updates in the background and install
    them when Jayth closes”, “Notify me when a new version of my models is released”.
  - **Feedback:** **Report a bug…** and **Suggest an improvement…**.

## Personalization and memory

In **Personalization** you tell the agent what to call you, what to know about you, how to respond (style), which
language to respond in (Automatic = the language of your message) and additional instructions. **Memory** keeps
lasting preferences across conversations (the agent saves them when you tell it, e.g. “I use pnpm”); review, edit or
delete them in Personalization › Memory, and it can be turned off. The temporary chat doesn't use it.

## Assistants and skills

Profile menu › **Assistants and skills**. An **assistant** is an agent with its own instructions and reference files
(e.g. “Style editor”); pick it with **+ › Use an assistant** in the message box. A **skill** is a procedure the agent
uses when it fits the task (e.g. “Write executive reports and deliver them in Word”); create, import, enable or
disable them in the Skills tab (**Add examples** brings in a few samples).

## Scheduled tasks

Profile menu › **Scheduled tasks**. A task is a job the agent does on its own at the set time (Once, Every day,
Monday to Friday, Every week on the chosen days, or At intervals) and lets you know when it's done: **New task**,
name, what it should do, when, how it acts (permissions), **Run now** and **View last result**. Tasks run while Jayth
is open (also in the tray). The agent can also schedule them if asked.

## Quick window

A small bar to ask Jayth from any app: shortcut **Ctrl+Alt+J** (change or disable it in Settings › General › Quick
window shortcut) or **Quick question** in the tray. **With screenshot** attaches an image of what was on the screen
(Ctrl+S). Enter sends, Esc closes.

## MCP connectors and web search

- **MCP connectors** (Settings › Tools): extend the agent's tools with the Model Context Protocol standard (files,
  memory, Playwright browser, Git, Fetch, GitHub…). There are templates that fill in the form; they can be a program
  on the computer (command and arguments; many need Node.js or uv) or a remote service (address and key). **Add and
  test** connects them; if the service asks you to sign in, its page opens (afterwards, **Sign in** or **Sign out** on
  its row).
- **Services with your account** (Settings › Tools): all optional; Jayth works locally and offline. There are cards for
  Higgsfield (AI images and video in the cloud, with your credits), Notion, Canva, Gmail, Google Drive, Google Calendar,
  Linear, Jira and Confluence, and Hugging Face (no account). **Connect** opens the service's page in the browser: the
  user signs in there and authorizes; Jayth never sees the password and keeps the permission encrypted on the computer
  (it renews itself). **Disconnect** forgets it. Gmail, Drive and Calendar first need **Set up Google…**: create once an
  “OAuth client ID” of type “Desktop app” in Google Cloud (with the MCP APIs enabled and the email as a test user) and
  paste its ID and secret; it works for all three.
- If a task needs it, the agent can suggest connecting a service: its card appears in the chat with **Connect** and,
  when done, **Continue**. Anything that changes something in the account (sending, publishing, spending credits)
  always asks for approval, even in Automatic mode; reading doesn't.
- **Web search:** works without any setup: DuckDuckGo and, if it asks for verification (Jayth doesn't bypass it), Bing through the built-in browser's engine, without showing it. Wikipedia is the last resort. A Brave Search key or your own SearXNG instance are optional.

## Interface language

Jayth is available in Spanish, English, Portuguese (Brazil), French, German, Italian,
Japanese and Simplified Chinese. The first time, it uses
the system language (English if it isn't one of these); change it
in **Settings › General › Interface language** and Jayth offers to restart to apply it. The language the agent
responds in is separate: by default, the language of the user's message (Settings › Personalization › Response
language).

## Updates

When there's a new version, Jayth downloads it in the background (the sidebar button shows “Downloading update… %”)
without interrupting anything. When it's done, the button changes to **Restart to update**: when you click it, Jayth
closes, the new version is installed (with a small “Updating…” window) and it opens again. If you don't click it, it
installs by itself when Jayth closes. When the new version opens, a notice appears with a link to **Updates** (what's
new). You can check manually from the profile menu › **Check for updates** and turn off automatic downloading in
Settings › About › Updates. Conversations, settings and models are kept when updating.

## Where everything is stored

- **Settings, conversations, engine and models:** Windows `%LOCALAPPDATA%\Jayth`, macOS `~/Library/Application
  Support/Jayth`, Linux `~/.local/share/jayth` (this computer's real path is in this version's data).
- **Chat mode working folder:** by default `Documents/Jayth`; change it in Settings › Agent and permissions.
- **Models folder:** change it in Settings › Models. Image models go in its `imagen` subfolder, and the image engine
  next to llama.cpp's (`runtime/imagen`).
- **Portable mode:** a `portable.txt` file next to the program stores everything in `userdata/` beside it (for a USB
  drive).
- **Privacy:** everything stays on the computer; Jayth doesn't send conversations or files to any server. It only
  uses the internet to download models and engines, check for updates, and for the web tools the user allows (or when
  using an API model, which receives that conversation's messages). Feedback and reports only leave the computer when the user presses **Send**.
- **Uninstall:** Windows, Settings › Apps › Jayth › Uninstall; macOS, drag Jayth to the Trash; Linux, delete the
  AppImage. Data and models aren't deleted when uninstalling.

## Feedback and help

Profile menu › **Send feedback…** or **Report a bug…** (also in Settings › About): the user reviews the text before
sending it. Below each response, **Report a problem with this response**. With **Send**, the feedback goes straight to the Jayth team, privately (it isn't published and no account is needed); **Post on GitHub** opens a public GitHub issue instead. If Jayth has an unexpected error, it saves it on the computer (without personal paths) and offers **Send report…**; it never sends it on its own. The project is at
https://github.com/Json-Tuiran/jayth.ai (downloads in Releases).

## Common problems

- **“The model is off” or it doesn't respond:** click **Start model** (or just type: Jayth starts it on its own). If
  it doesn't start, the reason shows in the notice and in Settings › Model log; it's usually not enough memory: choose
  a smaller quantization, lower the **Conversation memory (context)** or use **Compressed context**.
- **It's slow:** on computers without a GPU, large models take a while; try a smaller model, lower the effort to Low
  or, with an NVIDIA GPU, check that the engine is CUDA (Settings › Performance › Change or update the engine…).
- **It can't find the model (“I can't find the file…”):** click **Find it** or, in Models, **Locate…** or
  **Search in a folder…**.
- **It doesn't see images:** the model needs vision (projector); when adding it, check **Include vision**. Check
  Settings › Agent and permissions › Send screenshots and images to the model.
- **It doesn't create images or fails while creating them:** install the generator in Settings › Images and check that
  “Allow the agent to create images” is ticked. If it runs out of memory, choose a smaller size or FLUX.2 [klein] and
  close other programs; the details of the last attempt are in the `imagen.log` file in the data folder.
- **It can't use the internet or the mouse:** check Settings › Tools (internet access, computer control and the list
  of tools).
- **Windows shows “Windows protected your PC”:** the installer isn't signed yet: More info › Run anyway. **macOS:**
  the first time, right-click Jayth › Open.
- **The agent won't let you go back to a message:** wait for it to finish or stop it; messages that were already
  summarized can't be rewound (use New conversation).
- **An editor tab shows ⚠:** it couldn't be saved (read-only file or protected folder); the reason shows when you
  hover over the tab.
