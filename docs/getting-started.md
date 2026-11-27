# Getting started with Jayth

A short guide for non-technical people. *Español: [primeros-pasos.md](primeros-pasos.md).*

## 1. What it is

Jayth is an AI assistant that **works on your computer**: it doesn't just answer, it does things. For example:

- "Sort the photos in my Downloads folder by date."
- "Make a Word report from the sales in this Excel file."
- "Find the best price for this laptop online."
- "Build a web page for my business and show it to me."

It can use a **local** AI (on your computer, free and offline) or an **online** AI (Claude, Gemini, ChatGPT…), faster and
smarter but paid, and the conversation is sent to that service.

## 2. Install

1. Download the installer for your system from the [downloads page](https://github.com/Json-Tuiran/jayth.ai/releases/latest).
2. **Windows:** open it. If "Windows protected your PC" appears, click **More info → Run anyway** (it shows up because
   the installer isn't signed yet; common for new programs).
   **Mac:** open the `.dmg`, drag Jayth to Applications and, the first time, right-click Jayth → **Open**.
3. The first time you open Jayth, a **wizard** checks your computer and suggests an AI that fits. Accept and wait for
   the download (a few minutes, only once).

## 3. Choosing the AI

- **Little memory (8 GB) or no graphics card:** use a small model (the wizard picks it). It will answer slowly — that's
  normal. For speed, add an online AI in **Your profile → API models…** (you need a paid key from that service).
- **16 GB or more, or a graphics card:** you can use bigger, smarter models (**Your profile → Models**).

You can switch AI any time with the **model chip** next to the message box.

## 4. Asking for things

Write what you want as you'd tell a person and press **Enter**. You'll see every step: which file it reads, which command
it runs, what it creates. If something looks wrong, press **Stop**.

Tips:

- **Be specific:** "make a shopping list for 4 people in an Excel file" works better than "help me with shopping".
- **Drag files** into the chat (or use **+**) so it can work with them.
- What it creates (pages, documents, Word, Excel, PDF…) can be **viewed on the canvas**, on the right, with **View**,
  and you can save a copy with **Download a copy…**.

## 5. Permissions: who decides

Next to the message box is the **permissions chip**:

- **Ask** (recommended at first): Jayth asks before changing anything. You click **Allow** or **Deny**.
- **Automatic:** works without asking, except for sensitive things (deleting, installing software, touching the
  system…), which always ask.

If the agent reads a web page that tries to give it hidden orders, Jayth warns you and asks permission for everything
else in that reply.

## 6. If something goes wrong

- **Very slow:** normal with a local AI on a laptop. Try a smaller model or an online AI.
- **It made a mistake:** below each answer there is **Regenerate response**, and the changes card's **Undo all**
  restores your files.
- **A Jayth bug:** **Your profile → Report a bug…** (you see exactly what is sent before sending it).
- **How do I…?** Ask Jayth itself ("how do I change the language?"): it checks its own guide.

## 7. Your data

With a local AI, your files and conversations stay on your computer. With an online AI, the conversation is sent to
that service. Keys are stored protected on your computer. More in [SECURITY.md](../SECURITY.md).
