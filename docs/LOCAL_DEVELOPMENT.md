# Run Newsroom on this Windows computer

The local installation runs at `http://127.0.0.1:8001`. It uses the existing React frontend, FastAPI API and a real MongoDB database stored inside this project. No cloud database, Docker, API keys or WordPress credentials are needed to open it.

## Everyday use

1. Double-click **Start Local.cmd** in the project folder (or the Newsroom desktop shortcut).
2. Keep its console window open. Your browser opens automatically once the server is ready.
3. On first use, choose a username and password of at least 12 characters in **Create your administrator**. This account belongs to your local installation. No default password was created.
4. Use Setup Wizard to edit the two sites independently, Prompt Studio to edit prompts, and the other screens to inspect your local data.
5. Double-click **Stop Local.cmd**, or press **Ctrl+C** in the running console, to stop cleanly. Your database is retained.

The app is bound to loopback only. It is not reachable from another computer. Review mode, dry-run ON, scheduler OFF and auto-publish OFF are enforced by the desktop launcher. Manual public news discovery is available without AI keys. Published-post import, paid AI, WordPress publishing and media uploads stay disabled. Empty article/topic lists are expected on a clean installation. Saving credentials does not verify a connection or enable publishing.

To collect topics, select **Resume** at the top if the app is paused, then **Command Center → Run Discovery — Both Sites**. The app reads the public RSS feeds and news searches configured in `backend/lib/editorial_briefs.py`, then opens **Topic Intelligence** when the requests finish. You can also select one site there and choose **Discover Trends**. Pause, Stop All and individual site pauses still block discovery. Feed failures appear as errors; no sample news is substituted. Results are preliminary editorial leads, not researched articles. Duplicate checks use only records already indexed locally; published-post import remains unavailable. Kannada discovery currently uses one publisher because Google News's unsupported Kannada edition redirected to Hindi during verification.

Full automation is not ready in this local build. Research/writing require your Gemini API key, and images require your OpenAI API key in the private server configuration. Those keys alone do not release the repair lock or enable the scheduler. Review every stage with your own accounts before enabling live automation.

To check WordPress, save the base URL, username and Application Password for the selected site, then choose **Test Connection** and confirm the read-only request. This is allowed while dry-run stays ON. The server authenticates and reads REST endpoints using a client that rejects every non-GET request. Each site's result is independent. Reported write/upload capabilities are declarations, not live write tests. A successful connection does not unlock publishing. Unsaved connection edits must be saved before testing; changing credentials during a test invalidates its result.

## Installed locations

| Location | Contents |
|---|---|
| `.venv/` | Isolated Python 3.14 environment and backend dependencies |
| `.tools/yarn/` | Project-local Yarn 1.22.22; no global installation |
| `.tools/mongodb/` | Portable MongoDB 8.0.28; downloaded from the vendor and SHA-256 checked; no Windows service |
| `.local/mongodb/` | Persistent local database; never delete this to fix an installation problem |
| `.local/logs/mongodb.log` | MongoDB startup/shutdown diagnostics |
| `backend/.env` | Private configuration, session secret and credential encryption key; ignored by Git |
| `frontend/dist/` | Built frontend served by FastAPI |
| `frontend/yarn.lock`, `backend/requirements.lock.txt` | Dependency versions resolved for this installation |

Local MongoDB listens on `127.0.0.1:27018`; the database is `editorial_desktop`. This development database relies on the desktop's OS account security and loopback isolation, not MongoDB authentication. Do not expose that port or reuse this configuration for production. The launcher refuses to attach to a different database directory on that port.

The API uses Argon2id password hashes, eight-hour server-side sessions, HttpOnly/SameSite=Strict cookies, CSRF tokens and origin validation. `Secure` cookies are enabled for an HTTPS `APP_URL`; the desktop's loopback HTTP origin uses a non-Secure cookie so local login works. Login attempts are limited to ten per fifteen-minute bucket per client address.

## Setup or repair dependencies

Double-click **Setup Local.cmd**. It requires Python 3.14 and Node.js 24 and downloads dependencies on the first run. The portable MongoDB archive is large (approximately 805 MB). Setup preserves an existing environment file and database, fills only missing local configuration values, installs from lockfiles when available and rebuilds the frontend.

PowerShell equivalents from the repository root:

```powershell
python scripts/setup_local.py
.\.venv\Scripts\python.exe scripts/start_local.py
```

For a launch without opening the browser:

```powershell
.\.venv\Scripts\python.exe scripts/start_local.py --no-browser
```

If port 8001 is occupied by this app, a second start opens the existing instance. If another program owns the port, startup stops with an explanation. Do not change global PATH or install a database service to work around this.

## Editing the frontend

The desktop launcher serves the built frontend, so rebuild after source changes:

```powershell
Set-Location frontend
node ..\.tools\yarn\node_modules\yarn\bin\yarn.js build
```

Alternatively keep the local launcher running, run the following from `frontend`, and browse `http://127.0.0.1:3000` for hot reload:

```powershell
node ..\.tools\yarn\node_modules\yarn\bin\yarn.js dev
```

The development proxy uses `/api` on the same origin and forwards to port 8001. Use `127.0.0.1:3000`, which is in the configured origin allowlist.

## Verification commands and results

From repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s audit_tests -p test_safety.py -v
$env:RUN_LOCAL_INTEGRATION = 'true'
.\.venv\Scripts\python.exe -m unittest discover -s audit_tests -p test_local_app.py -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q backend scripts
git diff --check
```

Keep the desktop launcher running for the integration tests. They create a separate UUID-named `editorial_test_…` database and remove only that test database afterward. They never touch your administrator account or desktop data; external HTTP calls are forbidden in the test harness.


## Back up your local work

Stop the app cleanly, then copy `.local/mongodb` and `backend/.env` to a private encrypted backup location. This is a stopped-database backup, not a live directory copy. Restore the database together with the matching environment encryption key. Never share or commit either location. An online production backup strategy is still part of the broader self-hosting work.

## Scope and remaining work

This enables the local desktop application and user-initiated read-only WordPress connection tests. Paid providers, WordPress writes, complete research/language/publication invariants, a production scheduler, containers and production deployment remain under repair. The local launcher cannot enable publishing. No production deployment, real WordPress request or paid provider test was performed during verification.

MongoDB installation follows the vendor's [Windows ZIP installation method](https://www.mongodb.com/docs/v8.0/tutorial/install-mongodb-on-windows-zip/).
