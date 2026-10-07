"""Read-only credential-pattern scan; reports only filenames, lines and types.

Scans source/environment files in the worktree and textual blobs reachable from
local Git refs. A clean result is not proof of absence: review deployment secrets
and external databases separately. No credential values are emitted.
"""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".cache", ".tools", ".local"}
PATTERNS = {
    "OpenAI-style API key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b"),
    "Google-style API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "credential-bearing database URI": re.compile(r"mongodb(?:\+srv)?://[^\s/:]+:[^\s@]+@"),
    "private key material": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "JWT-like token": re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
}


def findings(data: bytes, name: str, scope: str):
    if b"\x00" in data:
        return
    text = data.decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                yield {"scope": scope, "file": name, "line": number, "type": kind}


def main():
    results = []
    file_count = 0
    for directory, dirs, names in os.walk(ROOT, followlinks=False):
        dirs[:] = [name for name in dirs if name not in EXCLUDED and not (Path(directory) / name).is_symlink()]
        for name in names:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            file_count += 1
            results.extend(findings(path.read_bytes(), path.relative_to(ROOT).as_posix(), "worktree"))
    objects = subprocess.check_output(["git", "rev-list", "--objects", "--all"], cwd=ROOT).decode().splitlines()
    blob_count = 0
    for row in objects:
        oid, _, name = row.partition(" ")
        kind = subprocess.check_output(["git", "cat-file", "-t", oid], cwd=ROOT).strip()
        if kind != b"blob":
            continue
        blob_count += 1
        data = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=ROOT)
        results.extend(findings(data, name or "(unnamed blob)", "git-history"))
    print(json.dumps({"worktree_files_scanned": file_count, "history_blobs_scanned": blob_count,
                      "findings": results, "limitations": "Pattern scan only; excludes dependencies, binary data and large worktree files. Database contents and external deployment configuration were not accessed."}, indent=2))
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main())
