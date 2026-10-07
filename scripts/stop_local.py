"""Ask only this launcher's instance to shut down; never kill arbitrary processes."""
import json
from pathlib import Path

local = Path(__file__).resolve().parents[1] / ".local"
runtime = local / "runtime.json"
if runtime.exists():
    instance = json.loads(runtime.read_text(encoding="utf-8"))["instance"]
    (local / "stop.request").write_text(instance, encoding="utf-8")
    print("Requested graceful shutdown of this local Newsroom instance.")
else:
    print("No local Newsroom launch is recorded.")
