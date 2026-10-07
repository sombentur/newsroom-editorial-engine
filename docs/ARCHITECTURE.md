# Architecture

A local FastAPI backend (Python), a React + TypeScript interface built with Vite and Tailwind, a project-local MongoDB database, and an optional Chrome extension. Everything binds to `127.0.0.1`.

## Workflow

Each article moves through persisted stages:

```
selected → researching → research_validated → writing_article → article_validated
         → generating_image → image_ready → WordPress draft / scheduled / published / verified
```

`held_review` is a stop for both editorial warnings and technical failures; read `held_reason` to tell them apart. **Retry** reconnects to saved work; **Go ahead** records your acceptance of research warnings; **Approve locally** needs an article, a passing quality gate and an image.

Production is strictly **one article at a time, alternating sites** (Kannada → English → Kannada …). The scheduler advances the current article, hands finished ones to WordPress at the next free publishing slot, and discovers new topics roughly every two hours per site. High-risk subjects wait for human sign-off without blocking the queue.

Two **generation routes** exist for research, SEO assets and thumbnails: API keys (Gemini / OpenAI) or the Chrome Bridge (Gemini and ChatGPT web apps in your own Chrome, see [CHROME_BRIDGE.md](CHROME_BRIDGE.md)). On the Chrome route Deep Research writes the article itself ("report-as-article"); on the API route a research dossier is validated first and the article is written from it.

## Backend (`backend/`)

| Module | Role |
|---|---|
| `server.py` | App entry: indexes, seed, safety state, scheduler task, static serving of `frontend/dist` |
| `seed.py` | Idempotent first-run configuration (sample sites, prompts, system settings) |
| `lib/auth.py` | Single-owner login (Argon2id), sliding sessions, CSRF and origin checks |
| `routers/pipeline.py` | Discovery, topic queue, per-article actions (research, generate, image, approve, publish, retry, stop, set-image) |
| `routers/config.py` | Sites, prompts, secrets status, health, audit, stats, plugin download |
| `routers/manual_research.py` | Manual Workbench: Excel export/import, report links, paste/upload of research documents |
| `lib/workflow.py` | Stage transitions, preflight checks, validation, WordPress hand-off |
| `lib/scheduler.py` | Automatic advancement, slot allocation, discovery cadence, auto-queue |
| `lib/turn.py` | The persisted "current article" turn |
| `lib/discovery.py`, `lib/editorial_briefs.py` | Feed/search reading and AI scoring against each site's brief |
| `lib/ai.py`, `lib/secrets.py`, `lib/deep_research.py` | Provider selection, safe errors, persisted research jobs |
| `lib/browser_bridge.py`, `browser_controller.py`, `browser_actions.py`, `browser_startup.py` | Chrome Bridge job queue, page rules and bounded planning |
| `lib/report_article.py`, `editorial_html.py`, `wp_blocks.py` | Report clean-up, article HTML, WordPress block output |
| `lib/thumbnail_prompts.py`, `thumbnails.py` | Thumbnail prompt template and headline validation |
| `lib/menu_categories.py` | WordPress menu-category rules |
| `lib/wordpress.py`, `wp_credentials.py` | WordPress REST client and encrypted credentials |
| `lib/manual_research.py`, `research_docx.py` | Manual research import and Word export |
| `wordpress_plugin/newsroom-seo-bridge.php` | Companion plugin exposing an allow-listed SEO meta route |

## Frontend (`frontend/src`)

| File | Screen / role |
|---|---|
| `components/Layout.tsx` | Shell: sidebar, header status, alerts, navigation drawer |
| `components/AuthGate.tsx` | Sign-in and first-run administrator creation |
| `pages/Dashboard.tsx` | Command Center |
| `pages/Topics.tsx` | Topic Intelligence |
| `pages/Articles.tsx` | Editorial Workbench |
| `pages/ManualWorkbench.tsx`, `components/ResearchLink.tsx` | Manual research flow (shared research box) |
| `pages/Schedule.tsx`, `Prompts.tsx`, `Wizard.tsx`, `Health.tsx`, `Audit.tsx`, `BrowserBridge.tsx` | Remaining screens |
| `lib/ui.tsx`, `index.css` | Shared badges, site switch, design tokens |

The launcher serves the **built** interface from `frontend/dist`; rebuild after changing frontend code (`Setup Local.cmd` does this, or run `yarn build` in `frontend`).

## Chrome extension (`chrome-extension/`)

`worker.js` (executor, one active job per work tab), `workspace.mjs` (owns two work tabs), `content.js` (page observer), `policy.mjs` (allowed actions), `research-export.mjs` (report export checks). The app copies updated files into the installed extension folder on every start (`scripts/extension_sync.py`) and the extension reloads itself.

## Safety model

Publishing is gated by environment switches (`DRY_RUN`, `REPAIR_LOCK`, `SCHEDULER_ENABLED`, `AUTO_PUBLISH_ENABLED`, `OPERATING_MODE`), the persisted in-app mode, per-site Auto/Pause switches, the global Pause and Stop All, quality gates and the high-risk sign-off. WordPress writes are verified by reading the saved post back. Secrets are never returned to the browser; the UI only sees whether a key is configured.
