"""Run the built UI and API on loopback, with a project-local MongoDB process."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8001"
LOCAL = ROOT / ".local"


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def open_existing():
    try:
        with urllib.request.urlopen(URL + "/api/ready", timeout=2) as response:
            return json.load(response).get("service") == "editorial-local"
    except Exception:
        return False


def sync_extension():
    """Copy the latest Chrome extension files into the folder Chrome loads (never blocks startup)."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from extension_sync import sync
        for note in sync():
            print(note, flush=True)
    except Exception as exc:  # noqa: BLE001 - an extension update must never stop the app
        print(f"Chrome extension files were not updated ({type(exc).__name__}).", flush=True)


def updated_since_start():
    """True when app code changed after the running instance started (so Start should restart it)."""
    try:
        started = (LOCAL / "runtime.json").stat().st_mtime
    except OSError:
        return False
    watched = [*(ROOT / "backend").rglob("*.py"), ROOT / "frontend/dist/index.html", ROOT / "backend/.env",
               *(ROOT / "chrome-extension").glob("*")]
    return any(path.exists() and path.stat().st_mtime > started for path in watched)


def stop_running_instance():
    """Ask the running launcher to shut down gracefully and wait until it has."""
    try:
        instance = json.loads((LOCAL / "runtime.json").read_text(encoding="utf-8"))["instance"]
    except (OSError, ValueError, KeyError):
        return False
    (LOCAL / "stop.request").write_text(instance, encoding="utf-8")
    for _ in range(120):
        if not port_open(8001):
            break
        time.sleep(0.5)
    else:
        return False
    for _ in range(60):  # let it release the database it owns
        if not port_open(27018):
            break
        time.sleep(0.5)
    return True


def main():
    sync_extension()
    if port_open(8001):
        if not open_existing():
            raise SystemExit("Port 8001 is occupied by another program. Close it and try again.")
        if not updated_since_start():
            print("Newsroom is already running at " + URL)
            if "--no-browser" not in sys.argv:
                webbrowser.open(URL)
            return
        print("Newsroom was updated since it started; restarting it to apply the update…", flush=True)
        if not stop_running_instance():
            raise SystemExit("The running Newsroom did not stop. Use Stop Local.cmd, then Start Local.cmd.")
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit("Run Setup Local.cmd first to install dependencies and build the UI.")
    binaries = list((ROOT / ".tools/mongodb").glob("*/bin/mongod.exe"))
    if not binaries:
        raise SystemExit("Portable MongoDB is missing. Run Setup Local.cmd.")
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.errors import AutoReconnect, ConnectionFailure
    import uvicorn
    load_dotenv(ROOT / "backend/.env")
    # Keep the isolated local database, while honoring the owner's explicit
    # workflow controls from backend/.env.
    os.environ.update(MONGO_URL="mongodb://127.0.0.1:27018", DB_NAME="editorial_desktop",
                      APP_URL=URL, CORS_ORIGINS=URL + ",http://localhost:8001,http://127.0.0.1:3000",
                      LOCAL_SETUP_ENABLED="true")
    mongo_dir = LOCAL / "mongodb"
    mongo_dir.mkdir(parents=True, exist_ok=True)
    logs = LOCAL / "logs"
    logs.mkdir(exist_ok=True)
    mongo = None
    instance = None
    control = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=1000)
    if port_open(27018):
        options = control.admin.command("getCmdLineOpts")
        configured = Path(options.get("parsed", {}).get("storage", {}).get("dbPath", "")).resolve()
        if configured != mongo_dir.resolve():
            raise SystemExit("Port 27018 belongs to a different database. Stop that instance or use separate development configuration.")
    else:
        mongo = subprocess.Popen([str(binaries[0]), "--bind_ip", "127.0.0.1", "--port", "27018",
                                  "--dbpath", str(mongo_dir), "--logpath", str(logs / "mongodb.log"), "--logappend"],
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    done = threading.Event()
    try:
        for _ in range(40):
            try:
                control.admin.command("ping")
                break
            except ConnectionFailure:
                if mongo and mongo.poll() is not None:
                    raise SystemExit("MongoDB could not start. See .local/logs/mongodb.log.")
                time.sleep(0.5)
        else:
            raise SystemExit("MongoDB did not become ready. See .local/logs/mongodb.log.")
        sys.path.insert(0, str(ROOT / "backend"))
        instance = str(uuid.uuid4())
        (LOCAL / "runtime.json").write_text(json.dumps({"instance": instance, "url": URL}), encoding="utf-8")
        server = uvicorn.Server(uvicorn.Config("server:app", host="127.0.0.1", port=8001, access_log=False))

        def monitor():
            opened = "--no-browser" in sys.argv
            while not done.wait(0.5):
                if not opened and server.started:
                    webbrowser.open(URL)
                    opened = True
                stop_file = LOCAL / "stop.request"
                if stop_file.exists() and stop_file.read_text(encoding="utf-8").strip() == instance:
                    server.should_exit = True
                    return

        threading.Thread(target=monitor, daemon=True).start()
        print("Newsroom: " + URL, flush=True)
        safety = os.environ
        print(f"Mode {safety.get('OPERATING_MODE', 'review')} | Dry-run {safety.get('DRY_RUN', 'true')} | "
              f"Scheduler {safety.get('SCHEDULER_ENABLED', 'false')} | "
              f"Auto-publish {safety.get('AUTO_PUBLISH_ENABLED', 'false')}", flush=True)
        print("Keep this window open. Use Ctrl+C or Stop Local.cmd to stop safely.", flush=True)
        server.run()
    finally:
        done.set()
        # A replacement launcher may already have adopted this local MongoDB.
        # Never shut down a database owned by a newer runtime instance.
        current_instance = None
        try:
            current_instance = json.loads((LOCAL / "runtime.json").read_text(encoding="utf-8")).get("instance")
        except (OSError, ValueError):
            pass
        if mongo and mongo.poll() is None and current_instance == instance:
            try:
                control.admin.command({"shutdown": 1})
            except (AutoReconnect, ConnectionFailure):
                pass
            mongo.wait(timeout=30)
        control.close()


if __name__ == "__main__":
    main()
