"""Owner-managed AI provider settings stored only in the server environment file."""

import asyncio
import os
from pathlib import Path

from lib.runtime import ConfigurationError

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
_WRITE_LOCK = asyncio.Lock()
_KEY_ENV = {"gemini_api_key": "GEMINI_API_KEY", "openai_api_key": "OPENAI_API_KEY", "rankmath_api_key": "RANKMATH_API_KEY"}
_PROVIDER_ENV = {"research_provider": "RESEARCH_AI_PROVIDER", "writing_provider": "WRITING_AI_PROVIDER", "image_provider": "IMAGE_AI_PROVIDER"}
_MODEL_ENV = {"model_research": "GEMINI_RESEARCH_MODEL", "model_writing": "GEMINI_WRITING_MODEL", "model_image": "OPENAI_IMAGE_MODEL"}
_GET_MODEL_ENV = {"research": "GEMINI_RESEARCH_MODEL", "writing": "GEMINI_WRITING_MODEL", "image": "OPENAI_IMAGE_MODEL"}
_ALLOWED_MODELS = {
    "model_research": {"deep-research-preview-04-2026", "deep-research-max-preview-04-2026", "o4-mini-deep-research", "o3-deep-research"},
    "model_writing": {"gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gpt-5.1", "gpt-4.1"},
    "model_image": {"gpt-image-2.5-sunburst", "gpt-image-2.5-flare", "gpt-image-2", "imagen-4.0-generate-001", "imagen-4.0-ultra-generate-001"},
}
_ALLOWED_PROVIDERS = {"research_provider": {"gemini", "openai"}, "writing_provider": {"gemini", "openai"}, "image_provider": {"openai", "gemini"}}

def get_secret(name: str) -> str:
    return os.environ.get(_KEY_ENV.get(name, ""), "")


def get_model(kind: str) -> str:
    return os.environ.get(_GET_MODEL_ENV[kind], "")


def get_provider(kind: str) -> str:
    default = "gemini" if kind in {"research", "writing"} else "openai"
    if kind == "writing":
        return os.environ.get("WRITING_AI_PROVIDER") or os.environ.get("RESEARCH_AI_PROVIDER", default)
    env_name = "RESEARCH_AI_PROVIDER" if kind == "research" else "IMAGE_AI_PROVIDER"
    return os.environ.get(env_name, default)


def _mask(value: str) -> str:
    return "Configured" if value else "Not configured"


def _validated(patch: dict) -> dict[str, str]:
    updates: dict[str, str] = {}
    for field, value in patch.items():
        if field not in _KEY_ENV and field not in _MODEL_ENV and field not in _PROVIDER_ENV:
            continue
        value = str(value).strip()
        if not value:  # Blank API key means keep the currently saved key.
            continue
        if len(value) > 4096 or any(ch in value for ch in "\r\n\0"):
            raise ConfigurationError("The AI provider setting has an invalid format.")
        if field in _ALLOWED_MODELS and value not in _ALLOWED_MODELS[field]:
            raise ConfigurationError("The selected AI model is not supported by this app.")
        if field in _ALLOWED_PROVIDERS and value not in _ALLOWED_PROVIDERS[field]:
            raise ConfigurationError("The selected AI provider is not supported by this app.")
        updates[(_KEY_ENV | _MODEL_ENV | _PROVIDER_ENV)[field]] = value
    return updates


def _write_env(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if name in remaining:
            output.append(f"{name}={remaining.pop(name)}")
        else:
            output.append(line)
    if remaining and output and output[-1] != "":
        output.append("")
    output.extend(f"{name}={value}" for name, value in remaining.items())
    temporary = ENV_PATH.with_name(ENV_PATH.name + ".tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temporary, ENV_PATH)


async def load_secrets() -> None:
    """Compatibility entry point; settings are loaded by the application bootstrap."""


async def save_secrets(patch: dict) -> None:
    updates = _validated(patch)
    if not updates:
        return
    async with _WRITE_LOCK:
        try:
            _write_env(updates)
        except OSError as exc:
            raise ConfigurationError("The AI provider settings could not be saved.") from exc
        os.environ.update(updates)


async def status() -> dict:
    research_provider = os.environ.get("RESEARCH_AI_PROVIDER", "gemini")
    image_provider = os.environ.get("IMAGE_AI_PROVIDER", "openai")
    writing_provider = get_provider("writing")
    return {
        "gemini_configured": bool(get_secret("gemini_api_key")),
        "gemini_key_masked": _mask(get_secret("gemini_api_key")),
        "openai_configured": bool(get_secret("openai_api_key")),
        "openai_key_masked": _mask(get_secret("openai_api_key")),
        "rankmath_configured": bool(get_secret("rankmath_api_key")),
        "rankmath_key_masked": _mask(get_secret("rankmath_api_key")),
        "research_model": get_model("research"),
        "writing_model": get_model("writing"),
        "image_model": get_model("image"),
        "research_provider": research_provider,
        "writing_provider": writing_provider,
        "image_provider": image_provider,
        "research_key_configured": bool(get_secret(f"{research_provider}_api_key")),
        "writing_key_configured": bool(get_secret(f"{writing_provider}_api_key")),
        "image_key_configured": bool(get_secret(f"{image_provider}_api_key")),
        "provider": "own-keys",
        "emergent_used": False,
    }
