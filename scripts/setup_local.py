"""Install this Windows desktop runtime without global packages or services."""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MONGO_VERSION = "8.0.28"


def run(args, cwd=ROOT):
    subprocess.run([str(x) for x in args], cwd=cwd, check=True)


def configure_environment():
    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import dotenv_values, set_key
    path = ROOT / "backend" / ".env"
    if not path.exists():
        with path.open("x", encoding="utf-8") as handle:
            handle.write((ROOT / "backend" / ".env.example").read_text(encoding="utf-8"))
    existing = dotenv_values(path)
    defaults = {
        "MONGO_URL": "mongodb://127.0.0.1:27018", "DB_NAME": "editorial_desktop",
        "APP_URL": "http://127.0.0.1:8001", "CORS_ORIGINS": "http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:3000",
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "WP_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "LOCAL_SETUP_ENABLED": "true", "NODE_ENV": "development", "PORT": "8001", "LOG_LEVEL": "INFO",
    }
    for name, value in defaults.items():
        if not existing.get(name):
            set_key(str(path), name, value)
    print("Local configuration ready. Secret values were not displayed.")


def main():
    if os.name != "nt":
        raise SystemExit("This desktop installer is for Windows.")
    os.chdir(ROOT)
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    lock = ROOT / "backend" / "requirements.lock.txt"
    run([python, "-m", "pip", "install", "-r", lock if lock.exists() else ROOT / "backend/requirements.txt",
         "--cache-dir", ROOT / ".cache/pip", "--disable-pip-version-check"])
    yarn = ROOT / ".tools/yarn/node_modules/yarn/bin/yarn.js"
    npm = shutil.which("npm.cmd")
    node = shutil.which("node.exe")
    if not npm or not node:
        raise SystemExit("Install Node.js 24 LTS, then run Setup Local.cmd again.")
    if not yarn.exists():
        run([npm, "install", "--prefix", ROOT / ".tools/yarn", "yarn@1.22.22", "--ignore-scripts", "--offline=false", "--cache", ROOT / ".cache/npm"])
    args = [node, yarn, "install", "--non-interactive", "--cache-folder", ROOT / ".cache/yarn",
            "--registry", "https://registry.npmjs.org", "--network-concurrency", "2", "--network-timeout", "120000"]
    if (ROOT / "frontend/yarn.lock").exists():
        args.append("--frozen-lockfile")
    run(args, ROOT / "frontend")
    run([node, yarn, "build"], ROOT / "frontend")
    if not list((ROOT / ".tools/mongodb").glob("*/bin/mongod.exe")):
        target = ROOT / ".tools/mongodb.zip"
        target.parent.mkdir(exist_ok=True)
        url = f"https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{MONGO_VERSION}.zip"
        print("Downloading portable MongoDB (large download, only needed once)...")
        urllib.request.urlretrieve(url, target)
        with urllib.request.urlopen(url + ".sha256", timeout=60) as response:
            expected = response.read().decode().split()[0].lower()
        with target.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise SystemExit("MongoDB checksum mismatch; installation stopped.")
        with zipfile.ZipFile(target) as archive:
            destination = (ROOT / ".tools/mongodb").resolve()
            for entry in archive.infolist():
                if not (destination / entry.filename).resolve().is_relative_to(destination):
                    raise SystemExit("Unsafe archive path; installation stopped.")
            archive.extractall(destination)
    run([python, __file__, "--configure-only"])
    print("Setup complete. Double-click Start Local.cmd.")


if __name__ == "__main__":
    try:
        if "--configure-only" in sys.argv:
            configure_environment()
        else:
            main()
    except (subprocess.CalledProcessError, OSError):
        raise SystemExit("Local setup could not finish. Check the preceding package/tool error and run Setup Local.cmd again.") from None
