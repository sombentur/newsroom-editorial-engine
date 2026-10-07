# News Room Editorial Engine

A local, AI-assisted newsroom for running **two WordPress news sites** — one in **Kannada**, one in **English** — from a single desk on your own Windows computer.

It finds trending topics from news feeds, researches them with Google Gemini Deep Research, writes and checks the article, prepares SEO fields and a 16:9 thumbnail, and schedules or publishes the finished post to WordPress — with human review gates at every step. Everything runs on your machine; nothing is sent anywhere except to the services you connect yourself (your WordPress sites and, optionally, your own AI accounts).

> **Built with AI-assisted development (Claude).**

---

## Who it is for

Small publishers or solo editors who run one Kannada-language and one English-language WordPress site and want a structured, reviewable pipeline from *topic → research → article → SEO → thumbnail → schedule*. You do not need to be a programmer to install or use it, but you do need your own WordPress sites and (for the AI steps) your own AI accounts or API keys.

## What you get

| Screen | What it does |
|---|---|
| **Command Center** | Health of both sites, today's output, the current article in production, pause / stop controls |
| **Topic Intelligence** | Topics discovered from your feeds and searches, scored 0–100 against each site's editorial brief; bulk select, grid view, filters, CSV export |
| **Editorial Workbench** | One place per article: research, article preview, SEO checklist, quality gates, thumbnail headlines, approve, schedule, publish |
| **Manual Workbench** | Do the research yourself (download an Excel of topics and prompts, paste report links, or paste/upload Word/PDF reports) |
| **Broadcast Schedule** | Publishing slots per site and the ready/scheduled queue |
| **Prompt Studio** | Edit the research, article and thumbnail prompts, with version history |
| **Setup Wizard** | Your websites, WordPress connections, AI providers and the optional Chrome extension |
| **Integration Health / Audit Log** | Connection status and a full trail of every automated and human action |

---

## Requirements

- **Windows 10 or 11** (the launcher scripts are Windows-only)
- **Python 3.14** — https://www.python.org/downloads/ (tick **"Add python.exe to PATH"** during installation)
- **Node.js 24 LTS** — https://nodejs.org/
- About **1.5 GB of free disk space** (a portable MongoDB database engine, ~0.8 GB, is downloaded once during setup; it is not installed as a Windows service)
- An internet connection during setup and while discovering topics
- One or two **WordPress** sites where you can create an *Application Password* (WordPress → Users → Profile → Application Passwords)
- *Optional:* a **Google Gemini API key** and an **OpenAI API key** (for research, writing and image generation through the API route), and/or **Google Chrome** signed in to Gemini and ChatGPT (for the Chrome Bridge route — see the warning below)

Nothing is pre-configured. Every key, login and site is entered by you, in the app.

---

## Installation (step by step)

1. **Download** this project (on GitHub: green **Code** button → **Download ZIP**) and **extract** it to a folder you control, for example `C:\NewsRoom`. Avoid folders that need administrator rights (such as `C:\Program Files`).
2. **Install Python 3.14** from python.org. On the first installer screen tick **Add python.exe to PATH**, then choose *Install Now*.
3. **Install Node.js 24 LTS** from nodejs.org with the default options.
4. Open the extracted folder and double-click **`Setup Local.cmd`**. A black window shows progress. It installs the Python and JavaScript dependencies into the project folder, builds the interface, downloads portable MongoDB and writes a private configuration file (`backend\.env`) with freshly generated secrets. This takes **5–15 minutes** the first time. When it says *Setup complete*, press any key to close it.
   - If it stops with an error about `python` or `npm` not being found, close the window, log out and back in to Windows (so the new PATH takes effect), and run `Setup Local.cmd` again.
5. Double-click **`Start Local.cmd`**. Keep this window open while you use the app (minimising it is fine; closing it stops the app). Your browser opens **http://127.0.0.1:8001** automatically.
6. On the first visit, the app asks you to **create your administrator** account: choose a username and a password of at least 12 characters. This account exists only in your local database; there is no default login.
7. Open **Setup Wizard** (left menu):
   - **Websites** — for each of the two sites enter its name, domain, WordPress base URL (`https://your-site.example`), the WordPress user name and its *Application Password*, time zone, publishing times and word counts. Click **Save Settings**, then **Test Connection** (read-only).
   - **AI Providers** — paste your Gemini and/or OpenAI API keys and pick the models. Keys are stored only in `backend\.env` on your computer and are never shown again in the browser.
   - **Browser Extension** — only if you want the Chrome Bridge route (see *Chrome Bridge* below).
   - For Rank Math / Yoast SEO fields, install the companion plugin from **Integration Health → Download newsroom-seo-bridge.php** on each WordPress site.
8. To stop: double-click **`Stop Local.cmd`** (or press Ctrl+C in the launcher window). Your database and settings are kept.

To start again later, just double-click `Start Local.cmd`.

### Optional: desktop shortcuts

Right-click `scripts\create_desktop_shortcuts.ps1` → **Run with PowerShell** to add *Newsroom Engine* and *Stop Newsroom* shortcuts to your desktop.

---

## First run: from an empty queue to a published post

1. The app starts **paused** and in **Review** mode with publishing locked (safe defaults). Click **Resume** in the top bar.
2. **Command Center → Run Discovery — Both Sites** reads the news feeds and searches configured for each site. Topics appear in **Topic Intelligence**. (With a Gemini key the AI editor scores them 0–100; without one they get a heuristic score and nothing is queued automatically.)
3. Open a topic → **Add to Workbench**.
4. In the **Editorial Workbench** either press **Start Workflow** (research → article → SEO → thumbnail, using the generation route chosen on the Command Center) or do the research yourself via the **Manual Workbench** and paste the report link / document.
5. Review the research, article, SEO checklist and gates. Edit the thumbnail headlines if you like (they also become the post title). **Approve locally**.
6. **Schedule** it into one of the site's publishing slots or press **Publish Now**.
7. To let the app run on its own, switch the operating mode to **Auto**, turn the **Scheduler** on (Command Center) and, in `backend\.env`, set `DRY_RUN=false`, `REPAIR_LOCK=false`, `SCHEDULER_ENABLED=true` and `AUTO_PUBLISH_ENABLED=true` (then restart). The app then publishes one article at a time, alternating between the two sites, one per hour inside each site's publishing window, up to the daily quota. High-risk subjects always wait for your approval.

---

## The two websites

The app is built around exactly two sites with fixed internal keys:

| Key | Language | Where it is configured |
|---|---|---|
| `kannadiga` | Kannada (`kn`) | Setup Wizard → first website tab |
| `human` | English (`en`) | Setup Wizard → second website tab |

The names, domains and WordPress details are yours to set in the Setup Wizard (the shipped values are samples: *Kannada News (sample)* / *English News (sample)*). Two text files hold the editorial setup you should also adapt:

- `backend/lib/editorial_briefs.py` — each site's **news feeds, search queries, excluded story types, categories and editorial brief** used to score topics. The shipped briefs are generic samples; write your own.
- `backend/lib/menu_categories.py` — each site's **WordPress menu categories** (IDs, names, descriptions and keyword hints). Replace the sample IDs with the real category IDs from your WordPress admin (Posts → Categories; the ID is in the link).

Prompts (research, article, thumbnail) are edited in **Prompt Studio** inside the app.

---

## Configuration file and ports

`Setup Local.cmd` creates `backend\.env` from `backend\.env.example` and fills in the secrets. Every setting is explained in **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)**. The important safety switches:

| Setting | Default | Meaning |
|---|---|---|
| `DRY_RUN` | `true` | No WordPress writes at all |
| `REPAIR_LOCK` | `true` | Automatic publishing cannot be switched on |
| `SCHEDULER_ENABLED` | `false` | The background scheduler does not run |
| `AUTO_PUBLISH_ENABLED` | `false` | Finished articles are never published without you |
| `OPERATING_MODE` | `review` | `review`, `research_only` or `auto` |
| `MANUAL_AI_ENABLED` | `false` | Allow AI calls you trigger by hand while publishing stays locked |

The app listens on `127.0.0.1:8001` and its database on `127.0.0.1:27018` — loopback only, never reachable from other computers. If those ports are taken, start it with different ones, e.g. in PowerShell:

```powershell
$env:NEWSROOM_PORT = "8002"; $env:NEWSROOM_MONGO_PORT = "27019"; .\.venv\Scripts\python.exe scripts\start_local.py
```

## Where your data lives (and how to back it up)

| Location | Contents |
|---|---|
| `backend\.env` | Your private configuration: API keys, session secret, the key that encrypts WordPress passwords |
| `.local\mongodb\` | The database: sites, topics, articles, images, audit log |
| `.local\logs\` | MongoDB logs |
| `.venv\`, `frontend\node_modules\`, `.tools\`, `.cache\` | Installed dependencies and the portable database engine (recreated by Setup) |

Stop the app, then copy **`backend\.env` and `.local\mongodb` together** to a private, encrypted backup. Never share either; the database can only be read with the matching `.env` key. All of these folders are ignored by Git.

---

## Chrome Bridge (optional) — please read

Besides the API route, the app can drive **Gemini and ChatGPT in your own signed-in Google Chrome** through the included browser extension (`chrome-extension/`), so that Deep Research, SEO assets and thumbnails use your existing subscriptions instead of API credits. How to install it is described in **[docs/CHROME_BRIDGE.md](docs/CHROME_BRIDGE.md)**.

**Warning.** This route automates the consumer web apps of Google Gemini and OpenAI ChatGPT. Automated or scripted use of those web apps may be prohibited by their terms of service and could lead to your account being limited or suspended. It is also fragile: whenever those sites change their page layout, the extension may stop working until it is updated. Use it only if you have checked that it is allowed for your accounts, and at your own risk. The API route (your own API keys) is the supported way to run this app.

---

## Known limits

- Windows only (the launcher, portable MongoDB and the thumbnail font path assume Windows). The code itself is portable, but no Linux/macOS launcher is provided.
- Exactly two sites with fixed keys (`kannadiga`, `human`); adding a third site requires code changes.
- Single administrator account; no multi-user roles.
- Designed for Kannada and English. Other languages would need prompt and validation changes.
- Gemini's free API tier allows only a handful of requests per model per day; topic scoring and the Chrome page planner slow down or pause when that quota is used up.
- Published posts are *verified by reading them back* from WordPress, but the app does not monitor your sites afterwards.
- WordPress SEO fields need the companion plugin (`backend/wordpress_plugin/newsroom-seo-bridge.php`, GPL-2.0-or-later) installed on each site.
- The Chrome Bridge depends on the current Gemini/ChatGPT page layouts (see the warning above).

## Disclaimer

This software is provided **"as is", without warranty of any kind**. It generates text and images with third-party AI services that can be wrong, biased, out of date or defamatory, and it can publish to live websites. **You are the publisher**: review every article before it goes live, keep the review gates on until you trust your setup, and make sure your use complies with the terms of WordPress, Google, OpenAI and every news source you read. The authors accept no responsibility for anything published with it. It is not legal, financial, medical or professional advice, and it does not provide any.

## Third-party software

All libraries, fonts and icons used are under permissive open-source licences (MIT, BSD, Apache-2.0, ISC, MPL-2.0 and the SIL Open Font License for the fonts). The full list is in **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**. Portable MongoDB is downloaded by you from mongodb.com during setup under MongoDB's own licence (SSPL); it is not included in this repository.

## Project layout

```
backend/            FastAPI server, workflow, scheduler, AI and WordPress clients (Python)
frontend/           React + TypeScript + Tailwind interface (built into frontend/dist by Setup)
chrome-extension/   Optional Chrome Bridge extension
scripts/            Setup, start and stop scripts
docs/               Configuration, architecture and Chrome Bridge guides
Setup Local.cmd / Start Local.cmd / Stop Local.cmd
```

## Author and licence

Author: **[YOUR-GITHUB-USERNAME](https://github.com/YOUR-GITHUB-USERNAME)**

Built with AI-assisted development (Claude).

Released under the **MIT License** — see [LICENSE](LICENSE). The bundled WordPress companion plugin is GPL-2.0-or-later, as WordPress requires.
