# Environment configuration

Use `backend/.env.example` as the single configuration template. Enter secrets locally in an ignored `backend/.env` or the eventual host's secret manager; never paste them into chat, frontend code, browser storage or a committed Compose file. The desktop setup now creates an ignored backend/.env and generates private session/encryption values locally without displaying them.

The restored server validates required configuration at startup. The desktop launcher forces an isolated local database and safe operating controls; see LOCAL_DEVELOPMENT.md. The table distinguishes implemented controls from planned placeholders: adding a placeholder does not implement the feature.

| Variable | Purpose and current state |
|---|---|
| `MONGO_URL` | Owner-controlled Mongo URI. Existing required name retained; no competing `DATABASE_URL` introduced. Validated at startup; the desktop launcher uses mongodb://127.0.0.1:27018 |
| `DB_NAME` | Owner-controlled database name; existing required name retained |
| `APP_URL` | Intended public origin; existing name retained. Validated origin used for sessions, trusted hosts and CSRF checks |
| `CORS_ORIGINS` | Explicit allowed origins. Explicit allowlist only; desktop setup supplies loopback origins, with no wildcard |
| `GEMINI_API_KEY` | Server-only direct Google API credential; never read from legacy Mongo now |
| `GEMINI_RESEARCH_MODEL` | Explicit configured research model; no fallback model name |
| `GEMINI_WRITING_MODEL` | Explicit configured writing model; no fallback model name |
| `OPENAI_API_KEY` | Server-only direct OpenAI credential |
| `OPENAI_IMAGE_MODEL` | Explicit configured image model; no fallback model name |
| `WP_CREDENTIAL_ENCRYPTION_KEY` | Existing canonical encryption setting retained instead of adding `APP_ENCRYPTION_KEY`. Required by Fernet; setup generates it directly in the ignored server environment if absent. Existing keys are preserved |
| `DRY_RUN` | Implemented strict boolean; default `true`. Blocks discovery, provider boundaries and WordPress-write preflight |
| `SCHEDULER_ENABLED` | Implemented environment scheduler gate; default `false`; persisted administrator flag and repair lock must also allow execution |
| `AUTO_PUBLISH_ENABLED` | Default `false`; workflow publication/scheduling requires this plus environment Auto mode, persisted Auto mode and site opt-in. The desktop UI disables automatic publishing |
| `OPERATING_MODE` | `review`, `research_only`, `auto`; default `review`. Workflow also enforces persisted mode. The local dashboard reports effective Review mode |
| `SOURCE_GROUNDED_RESEARCH_ENABLED` | Default `false`; existing grounded research adapter cannot act as a silent Deep Research fallback |
| `SESSION_SECRET` | Required server secret (at least 32 characters), used to hash opaque session and CSRF tokens; generated locally by setup |
| `NODE_ENV`, `PORT`, `LOG_LEVEL` | Blank placeholders for restored startup/container scripts; not yet wired |

`WP_CREDENTIAL_KEY_FILE` was removed: encryption keys must live in server environment/secret management. If a previous runtime created a key file, retain it securely and provision that same key locally; do not generate a replacement for existing ciphertext.

Safety values are explicit rather than blank in the example because they are operating defaults, not secrets. Empty/invalid booleans fail closed with variable names only in error messages. Keep AI credentials/models blank during offline repair. WordPress username/Application Password are managed by the authenticated Setup Wizard, not by frontend environment variables.

`LOCAL_SETUP_ENABLED` defaults to false in the example. The desktop launcher sets it true for loopback-only first-owner setup; a unique owner record prevents subsequent replacement. Full local details are in [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md).


## Manual AI in local review

`MANUAL_AI_ENABLED` defaults to `false`. The owner can enable manual paid research, writing and image requests while retaining `DRY_RUN=true`. Only authenticated article actions receive this exception; scheduler and WordPress guards remain independent. Global/site pause and Stop still apply.

`GEMINI_RESEARCH_MODEL` must name a Deep Research agent (configured here as `deep-research-preview-04-2026`), not a generate-content model. `GEMINI_WRITING_MODEL` formats the cited report and writes the article. `OPENAI_IMAGE_MODEL` is configured here as `gpt-image-2.5-sunburst`, which supports `1536x864` output. `THUMBNAIL_FONT_PATH` defaults to `C:/Windows/Fonts/NirmalaB.ttf`; other systems need a locally installed Kannada-capable font. The font is not redistributed.

References: [Gemini Deep Research](https://ai.google.dev/gemini-api/docs/deep-research), [OpenAI image generation](https://developers.openai.com/api/docs/guides/image-generation).

- `KANNADA_AI_AUDIT` (default `false`): when `true`, Kannada articles get the extra AI language/fact audit and one rewrite pass after writing. Off by default; the free Kannada script checks in the quality gate always run.

- `GEMINI_FAST_MODEL` (default `gemini-flash-latest`, Google's alias for the current stable Flash; `BROWSER_CONTROLLER_FALLBACKS` defaults to `gemini-3.6-flash,gemini-3.8-flash` for the page planner when a model is overloaded): fast Gemini model used to rank discovered topics for engagement and to drive the Chrome extension page planner.
- `BROWSER_CONTROLLER_PROVIDER` (default `gemini`) / `BROWSER_CONTROLLER_MODEL`: which API decides each Chrome extension step. Previously this used the OpenAI writing model, so OpenAI rate limits also stopped Chrome jobs. Set the provider to `openai` to restore the old behaviour.
- Report-as-article workflow (2026-09-27): when the Chrome research route is on, Gemini Deep Research writes the article itself (`backend/lib/report_article.py`), its copied report becomes the post body, and a ChatGPT `seo` browser job returns SEO assets and the thumbnail prompt. Override the research prompt by saving a `deep_research_article` prompt.
