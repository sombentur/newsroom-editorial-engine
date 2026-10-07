# Third-party software and assets

Everything below is used under a permissive open-source licence that allows redistribution. Licence texts ship with the packages when they are installed by `Setup Local.cmd` (`frontend/node_modules/*/LICENSE`, `.venv/Lib/site-packages/*.dist-info/`).

## JavaScript / frontend (installed from npm)

| Package | Version | Licence |
|---|---|---|
| react, react-dom, react-is | 19.2.8 | MIT |
| react-router-dom | 7.18.1 | MIT |
| @tanstack/react-query | 5.101.4 | MIT |
| @base-ui/react | 1.6.0 | MIT |
| shadcn (component templates) | 4.16.0 | MIT |
| tailwindcss, @tailwindcss/vite | 4.3.3 | MIT |
| tw-animate-css | 1.4.0 | MIT |
| tailwind-merge | 3.6.0 | MIT |
| class-variance-authority | 0.7.1 | Apache-2.0 |
| clsx | 2.1.1 | MIT |
| motion | 12.42.2 | MIT |
| recharts | 3.10.1 | MIT |
| sonner | 2.0.7 | MIT |
| dompurify | 3.4.15 | MPL-2.0 OR Apache-2.0 |
| date-fns | 4.4.0 | MIT |
| react-day-picker | 10.0.1 | MIT |
| next-themes | 0.4.6 | MIT |
| lucide-react (icons) | 1.27.0 | ISC |
| @icons-pack/react-simple-icons | 13.15.1 | MIT (icons: CC0-1.0) |
| vite, @vitejs/plugin-react | 8.1.5 / 6.0.4 | MIT |
| typescript | 7.0.2 | Apache-2.0 |
| oxlint, vitest, @babel/* , @types/* | — | MIT |

## Fonts (bundled through @fontsource packages, SIL Open Font License 1.1)

| Font | Use |
|---|---|
| Geist Variable | Interface text and headings |
| Noto Sans Kannada Variable | Kannada text |
| JetBrains Mono Variable | Code and identifiers |
| Fraunces Variable, Lora Variable | Installed but not used by the interface |

The thumbnail renderer can use a Kannada-capable font from the user's own system (`THUMBNAIL_FONT_PATH`); no system font is redistributed.

## Python / backend (installed from PyPI)

| Package | Version | Licence |
|---|---|---|
| fastapi | 0.141.1 | MIT |
| uvicorn | 0.52.1 | BSD-3-Clause |
| motor | 3.7.1 | Apache-2.0 |
| pymongo | 4.17.0 | Apache-2.0 |
| pydantic | 2.13.5 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| tzdata | 2026.4 | Apache-2.0 |
| argon2-cffi | 25.1.0 | MIT |
| bleach | 6.4.0 | Apache-2.0 |
| google-genai | 2.25.0 | Apache-2.0 |
| openai | 2.54.0 | Apache-2.0 |
| pillow | 12.3.0 | MIT-CMU |
| python-docx | 1.2.0 | MIT |
| pypdf | 5.9.0 | BSD-3-Clause |
| openpyxl | 3.1.5 | MIT |
| uharfbuzz | 0.56.2 | Apache-2.0 |
| freetype-py | 2.5.1 | BSD |
| pytest, pytest-xdist, pytest-asyncio | — | MIT / Apache-2.0 |

## Downloaded during setup (not included in this repository)

| Component | Source | Licence |
|---|---|---|
| MongoDB Community Server 8.0 (portable ZIP) | downloaded from mongodb.com by `scripts/setup_local.py`, SHA-256 verified | Server Side Public License (SSPL) — used locally, not redistributed |
| Yarn 1.22 | installed into `.tools/yarn` from npm | BSD-2-Clause |

## Services this app talks to (your own accounts)

WordPress REST API (your sites), Google Gemini API / Gemini web app, OpenAI API / ChatGPT web app, Google News RSS and the news feeds you configure, and Rank Math (optional). Each is subject to its own terms of service.

## Original work in this repository

Application code, prompts, the companion WordPress plugin (`GPL-2.0-or-later`), the Chrome extension and the "News Room — Editorial Engine" logo and icons are original to this project and released under the terms in [LICENSE](LICENSE) (MIT), except where a file states otherwise.
