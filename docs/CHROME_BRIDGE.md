# Chrome Bridge (optional)

The Chrome Bridge lets the app use **Gemini Deep Research and ChatGPT through your own signed-in Google Chrome** instead of API keys. It is optional; the API route is the supported default.

> **Read first.** This automates the consumer web apps of Google Gemini and OpenAI ChatGPT. Automated or scripted use of those web apps may be prohibited by their terms of service and could lead to your account being limited or suspended. The page layouts of those sites change without notice, which can break the extension until it is updated. Use it only if you have checked that it is allowed for your accounts, and at your own risk.

## What it does

- Opens **two dedicated work tabs** in Chrome (one for Gemini, one for ChatGPT) and never touches your personal chat tabs.
- Runs one job at a time per tab: Deep Research, SEO assets, or a thumbnail image.
- Never overwrites text it did not type: if a message box already contains a draft, the job waits and then asks you.
- Sends each prompt exactly once; uncertain sends are reported, never repeated automatically.
- Connects to the app on `http://127.0.0.1:8001` only (change `BASE` in `chrome-extension/worker.js` if you run the app on another port).

## Install

1. Open Chrome and go to `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose the `chrome-extension` folder of this project.
4. Sign in to Gemini and ChatGPT in that Chrome profile.
5. Start the app. Within a minute **Setup Wizard → Browser Extension** shows *Connected*. Pairing is automatic on the local machine; a manual pairing code exists as a fallback.
6. On the Command Center choose **Chrome Bridge** as the route for research and/or images.

The app copies updated extension files into the folder Chrome loaded them from on every start (`scripts/extension_sync.py`, or set `BROWSER_EXTENSION_DIR`), and the extension reloads itself once when the app reports a newer version.

## Operating notes

- The page planner (a small Gemini/OpenAI call per uncertain page state) is used only when the built-in rules do not recognise the page; set `BROWSER_CONTROLLER_PROVIDER` / `BROWSER_CONTROLLER_MODEL` in `backend/.env`.
- Each image job chooses ChatGPT's *Create image* tool and sets the thinking level before sending the prompt; a failed image is retried in a fresh chat up to two times, then the article waits for you.
- A Deep Research run that does not finish in time is released and retried once automatically; **Copy report again** fetches a finished report from an open Gemini tab without new research.
- Use a different Google account for research by pasting its Gemini address (`https://gemini.google.com/u/N/app`) in Setup Wizard → Browser Extension.
- Stop a stuck browser job from Setup Wizard → Browser Extension → *Stop this browser job*.
