"""The launcher keeps Chrome's installed extension folder up to date; it never touches other extensions."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extension_sync  # noqa: E402


def _extension(folder: Path, name: str, version: str) -> Path:
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    (folder / "worker.js").write_text("// old", encoding="utf-8")
    return folder


def test_sync_updates_only_installed_newsroom_bridge(tmp_path, monkeypatch):
    bridge = _extension(tmp_path / "newsroom-browser-bridge", "Newsroom Browser Bridge", "0.3.1")
    other = _extension(tmp_path / "some-other-extension", "Other", "1.0")
    profile = tmp_path / "chrome" / "Profile 8"
    profile.mkdir(parents=True)
    (profile / "Secure Preferences").write_text(json.dumps({"extensions": {"settings": {
        "a": {"location": 4, "path": str(bridge)},
        "b": {"location": 4, "path": str(other)},
        "c": {"location": 1, "path": "store-extension"},
        "d": {"location": 4, "path": str(extension_sync.SOURCE)},
    }}}), encoding="utf-8")
    monkeypatch.delenv("BROWSER_EXTENSION_DIR", raising=False)

    assert extension_sync.installed_folders(tmp_path / "chrome") == [bridge.resolve()]
    notes = extension_sync.sync(tmp_path / "chrome")
    assert len(notes) == 1 and "reloads itself" in notes[0]
    source_manifest = (extension_sync.SOURCE / "manifest.json").read_text(encoding="utf-8")
    assert (bridge / "manifest.json").read_text(encoding="utf-8") == source_manifest
    assert (bridge / "worker.js").read_bytes() == (extension_sync.SOURCE / "worker.js").read_bytes()
    assert (other / "worker.js").read_text(encoding="utf-8") == "// old", "unrelated extension untouched"
    assert extension_sync.sync(tmp_path / "chrome") == [], "nothing to do once in sync"


def test_missing_chrome_profile_is_harmless(tmp_path, monkeypatch):
    monkeypatch.delenv("BROWSER_EXTENSION_DIR", raising=False)
    assert extension_sync.sync(tmp_path / "no-chrome") == []
