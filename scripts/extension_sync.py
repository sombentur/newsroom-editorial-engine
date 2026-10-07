"""Keep the Chrome extension folder that Chrome actually loads in sync with this app's copy.

Chrome runs an unpacked extension from whatever folder was chosen in "Load unpacked" (often an
extracted download). The app updates chrome-extension/ in this project; on every start the launcher
copies changed files into each installed Newsroom Browser Bridge folder, and the extension reloads
itself when the app reports a newer version. No pairing code or manual reload is needed.
"""
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chrome-extension"
FILES = ("manifest.json", "worker.js", "content.js", "policy.mjs", "workspace.mjs", "research-export.mjs", "observer.mjs",
         "popup.html", "popup.css", "popup.js", "README.md")
NAME = "Newsroom Browser Bridge"
UNPACKED = 4  # Chrome's extension location code for "Load unpacked"


def _is_bridge(folder: Path) -> bool:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("name") == NAME
    except (OSError, ValueError):
        return False


def installed_folders(chrome_data: Path | None = None) -> list[Path]:
    """Unpacked Newsroom Browser Bridge folders Chrome loads, plus BROWSER_EXTENSION_DIR if set.

    Reads only the extension paths from Chrome's profile settings.
    """
    candidates = []
    if configured := os.environ.get("BROWSER_EXTENSION_DIR"):
        candidates.append(Path(configured))
    base = chrome_data or Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    for prefs in [*base.glob("*/Secure Preferences"), *base.glob("*/Preferences")]:
        try:
            settings = json.loads(prefs.read_text(encoding="utf-8")).get("extensions", {}).get("settings", {})
        except (OSError, ValueError):
            continue
        for entry in settings.values():
            if isinstance(entry, dict) and entry.get("location") == UNPACKED and entry.get("path"):
                candidates.append(Path(entry["path"]))
    folders = []
    for folder in candidates:
        folder = folder.resolve()
        if folder != SOURCE.resolve() and folder not in folders and _is_bridge(folder):
            folders.append(folder)
    return folders


def sync(chrome_data: Path | None = None) -> list[str]:
    """Copy changed extension files into every installed copy. Returns human-readable notes."""
    notes = []
    for folder in installed_folders(chrome_data):
        changed = [name for name in FILES if (SOURCE / name).exists() and (
            not (folder / name).exists() or (folder / name).read_bytes() != (SOURCE / name).read_bytes())]
        for name in changed:
            shutil.copy2(SOURCE / name, folder / name)
        if changed:
            notes.append(f"Updated the Chrome extension in {folder} ({len(changed)} files); it reloads itself within a minute.")
    return notes
