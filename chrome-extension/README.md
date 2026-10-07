# Newsroom Adaptive Browser Controller — 0.3.1

Update: download from Setup Wizard > Browser Extension, extract and replace files in the SAME installed folder, open chrome://extensions and Reload. Do not remove/reinstall if you want to retain pairing. The app shows the connected version. This update is independently implemented; it does not contain Claude's code or use Claude's hosted service.

New installations: Load unpacked in Chrome Developer mode, select this folder, then pair using a one-use code from the app. Chrome and Newsroom must run on the same PC. A separate Chromebook cannot reach this Windows service at 127.0.0.1.

## How it works
The extension creates two separate work tabs, Gemini and ChatGPT, groups them together and connects to both before starting a new job. It reuses only tabs it created in this browser session. Personal tabs are never adopted. The app and popup show readiness for each tab. Connect both work tabs reconnects released control; Release control stops browser jobs and detaches both tabs. Jobs run sequentially. It observes current page controls and a screenshot. Your configured Writing AI chooses one bounded action using an observed element ID. The extension checks the target again, then uses Chrome debugger input to click or type. It observes again before the next action. Gemini Pro and Deep Research selection, the research plan, report completion and ChatGPT images are interpreted from current page state rather than fixed English button names.

Controller calls use your Writing AI API credits. Job-tab text and screenshots are sent to that configured provider. Screenshots are not persisted by the Newsroom server. The extension requests no cookies or passwords. Code limits browser actions to the dedicated job's Gemini or ChatGPT host, even though Chrome describes debugger permission broadly. Browser activity is shown in the setup screen. A screenshot helps interpret icon-only controls; this version targets main-frame elements, not controls inside cross-origin frames.

Login, CAPTCHA, unavailable plans, quota limits, account changes, ambiguous results and repeated failed actions stop with an attention message. Resolve the issue yourself, inspect the job tab, and use Check connection / Continue in the popup. Prompts are marked submitted before the Send action to avoid duplicate submissions after a crash. An uncertain Send is never automatically retried; cancel and explicitly start another job if necessary. Maximum 60 active control actions per run; passive waiting does not count. Image generation waiting is capped at 120 seconds after submission. Research waits for completion without a browser generation deadline. Manual recovery remains available in the popup.

Generated image bytes are collected only from the observed image's matching browser network response or its displayed URL. Landscape backgrounds are normalized to 1536x864 before the app typesets validated Kannada/English headlines. The extension never reports a screenshot as the original image. Completed research includes source links and still passes through the app's existing research, writing and Kannada validation pipeline.

Stop in the popup or app prevents further actions and closes the dedicated cancelled tab when the worker checks in. Remote generation may still finish on the provider. Disconnect revokes the local connection. No automatic WordPress publication occurs from the connection-test button; ordinary workflows retain their existing publication gates.

## Validation
Run the built-in Test Gemini + ChatGPT button after updating. Check both returned results and the activity log before relying on unattended operation. Offline policy and backend tests do not prove compatibility with your signed-in websites. Site UI changes can still require adjustments. Existing API generation remains available by disabling browser providers.

0.2.1: supports checkbox/radio menu items such as Gemini Deep Research; re-observes transient page changes twice; recovers a re-rendered composer only via its previously observed DOM id and still refuses to overwrite existing text.

0.2.2: verifies the complete prompt after a bounded editor-settling wait, allowing only whitespace differences. No automatic re-insertion. After updating, refresh the dedicated job tab and use Continue in the popup.

0.3.1: Completed Gemini reports use Share & Export → Copy content. Clipboard read permission is required; reads occur only after the observed Copy content button is clicked and Gemini displays a copied confirmation. Research plans and missing Kannada output are rejected. Recovery captures the existing work-tab report without starting another research request.
