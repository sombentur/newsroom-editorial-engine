# Newsroom Editorial Engine

A desktop newsroom assistant for two WordPress news sites — one in **Kannada**, one in
**English**. It runs on your own Windows computer and, step by step, finds story leads,
researches them, writes a draft, checks the Kannada, makes a thumbnail and, only when you
allow it, publishes to WordPress.

Every stage can be run by hand from the **Editorial Workbench**, and nothing is published
until you turn publishing on. Out of the box the app starts in *review mode* with
dry-run ON, the scheduler OFF and auto-publish OFF.

## Who it is for

Small bilingual newsrooms and solo publishers who already have WordPress sites, their own
AI accounts (Google Gemini and/or OpenAI) and want one place to run the whole editorial
pipeline with a human in the loop.

## What it does

| Stage | What happens |
|---|---|
| Topic discovery | Reads public RSS feeds and news searches you configure, drops stories the site never covers, and lets an AI editor score the rest against each site's editorial brief. |
| Deep research | Builds a source-grounded dossier (Gemini Deep Research through the API, or through your own Gemini tab with the optional Chrome extension). |
| Writing | Writes the article from the dossier in the site's language and tone; Kannada drafts pass a script and spelling check. |
| Thumbnail | Generates a 1536×864 image and typesets short headlines on it with a real Kannada font. |
| SEO and publishing | Prepares title, description, categories and tags, then schedules or publishes to WordPress through the REST API with an Application Password. |

## Requirements

- Windows 10/11 (the launcher and portable MongoDB are Windows-only).
- [Python 3.14](https://www.python.org/downloads/) and [Node.js 24 LTS](https://nodejs.org/) on the PATH.
- About 2 GB of free disk space (the setup downloads a portable MongoDB, roughly 800 MB).
- Your own accounts, entered by you in the app (none are built in):
  - Google Gemini API key (research and writing) — <https://aistudio.google.com/>
  - OpenAI API key (thumbnail images) — <https://platform.openai.com/>
  - For each WordPress site: the site address, a dedicated editor user and an
    *Application Password* (WordPress → Users → Profile → Application Passwords).
- A font with Kannada glyphs for thumbnails. Windows ships *Nirmala UI*; on other systems
  install [Noto Sans Kannada](https://fonts.google.com/noto/specimen/Noto+Sans+Kannada)
  and point `THUMBNAIL_FONT_PATH` at it.
- Optional: Google Chrome, for the "Browser Bridge" extension that drives your own Gemini
  and ChatGPT tabs instead of the paid APIs.

## Install (no command line needed)

1. Download this repository as a zip (green **Code** button → **Download ZIP**) and unzip
   it to a folder of your choice, for example `C:\Newsroom`.
2. Double-click **Setup Local.cmd**. It creates a private Python environment, installs the
   web app, downloads portable MongoDB and writes `backend\.env` with freshly generated
   secrets. This takes several minutes the first time. When it says *Local configuration
   ready*, press any key.
3. Double-click **Start Local.cmd**. Keep its window open; your browser opens
   `http://127.0.0.1:8001`.
4. **Create your administrator**: choose a username and a password of at least 12
   characters. This account exists only on your computer.
5. Open **Setup Wizard** and fill in, for each site: its name, domain, timezone,
   publishing times, categories, WordPress address, editor username and Application
   Password. Use **Test Connection** (read-only) to confirm it works.
6. Open **Settings → AI providers** and paste your Gemini and OpenAI keys. They are written
   to `backend\.env` on your computer and never shown again.
7. Edit the sample editorial configuration to match your sites:
   - `backend/lib/editorial_briefs.py` — feeds, searches, exclusions and the brief for each site;
   - `backend/lib/menu_categories.py` — the category IDs of your WordPress sites.
   Then restart with **Stop Local.cmd** / **Start Local.cmd**.
8. Stop with **Stop Local.cmd** (or Ctrl+C in the window). Your database stays in `.local\`.

More detail: [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) and
[docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

## Everyday use

1. Press **Resume** at the top if the app is paused, then **Run Discovery — Both Sites**.
2. In **Topic Intelligence**, pick a lead and **Add to Workbench**.
3. In the **Editorial Workbench** run **Start Deep Research → Generate → Image**, reading
   the dossier, article and headlines at each step. Deep Research can take several
   minutes and continues in the background.
4. Review the SEO fields and categories, then **Schedule** or **Publish now** — these only
   work after you have turned off dry-run and released the repair lock in **Settings**.

Automatic scheduling (a fixed number of posts a day per site, alternating between the
two sites) exists but is off until you enable the scheduler, auto-publish and each site's
opt-in.

## Chrome extension (optional)

`chrome-extension/` is the *Newsroom Browser Bridge*. Load it in Chrome with
**Extensions → Developer mode → Load unpacked**, then pair it from **Setup Wizard →
Browser Extension**. It only acts in the dedicated Gemini and ChatGPT tabs it opens itself
and never reads your other tabs, cookies or passwords. See
[chrome-extension/README.md](chrome-extension/README.md).

## Known limits

- Windows only; the launcher binds to `127.0.0.1:8001` and MongoDB to `127.0.0.1:27018`.
- Built for exactly two sites, one Kannada (`kannadiga`) and one English (`human`); the
  names, domains and everything else are yours to set, but the pair is fixed.
- The Kannada quality checks are rule-based (script, spelling patterns) plus an optional
  AI audit; a human must still read every Kannada article before it goes live.
- The AI providers, their model names and the WordPress REST API change over time; model
  names are configured in `backend\.env` (see docs/ENVIRONMENT_VARIABLES.md).
- The Chrome extension depends on the current layout of gemini.google.com and chatgpt.com
  and may need updates when those sites change.
- There is no multi-user login: one administrator per installation.

## Disclaimer

This software produces AI-assisted drafts. **You are the editor and publisher**: check
facts, sources, names, numbers and language before anything is published under your
name, and follow the terms of service of the AI providers and of WordPress. The authors
accept no responsibility for what is published with it. It is not legal, medical or
financial advice software.

## Third-party components

All runtime dependencies are open source (MIT, BSD, Apache-2.0, ISC, MPL-2.0 or OFL):
FastAPI, Uvicorn, Motor/PyMongo, Pydantic, Pillow, python-docx, pypdf, google-genai,
openai, argon2-cffi, bleach, uharfbuzz, freetype-py (bundles FreeType, FTL/GPLv2
dual-licensed), openpyxl; React, Vite, TanStack Query, Tailwind CSS, Base UI, Recharts,
lucide-react, Simple Icons (CC0 icon data; brand marks remain their owners' trademarks),
DOMPurify (MPL-2.0/Apache-2.0), Fontsource fonts Geist, JetBrains Mono and Noto Sans
Kannada (SIL OFL 1.1). MongoDB Community Server is **downloaded by the setup script from
MongoDB's own servers** under the SSPL; it is not redistributed in this repository.

## Credits

Author: [sombentur](https://github.com/sombentur)

Built with AI-assisted development (Claude).

## License

MIT — see [LICENSE](LICENSE).
