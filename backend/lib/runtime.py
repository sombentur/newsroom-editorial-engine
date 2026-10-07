"""Fail-closed switches shared by every external-operation boundary.

No database or provider imports: audit tools and offline tests can use this module.
The repair lock is also persisted in Mongo; environment flags cannot release it.
"""
import os
from dataclasses import dataclass
from typing import Mapping


class ConfigurationError(ValueError):
    """A configuration error whose message never includes a setting's value."""


def boolean(name: str, default: bool, env: Mapping[str, str]) -> bool:
    value = env.get(name, "true" if default else "false").strip().lower()
    if value not in {"true", "false"}:
        raise ConfigurationError(f"{name} must be true or false.")
    return value == "true"


@dataclass(frozen=True)
class RuntimeSafety:
    dry_run: bool = True
    scheduler_enabled: bool = False
    auto_publish_enabled: bool = False
    operating_mode: str = "review"
    repair_lock_enabled: bool = True
    high_risk_review_required: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RuntimeSafety":
        env = os.environ if env is None else env
        mode = env.get("OPERATING_MODE", "review").strip().lower()
        if mode not in {"review", "research_only", "auto"}:
            raise ConfigurationError("OPERATING_MODE must be review, research_only or auto.")
        return cls(
            dry_run=boolean("DRY_RUN", True, env),
            scheduler_enabled=boolean("SCHEDULER_ENABLED", False, env),
            auto_publish_enabled=boolean("AUTO_PUBLISH_ENABLED", False, env),
            operating_mode=mode,
            repair_lock_enabled=boolean("REPAIR_LOCK", True, env),
            high_risk_review_required=boolean("HIGH_RISK_REVIEW_REQUIRED", True, env),
        )


def external_operation_block_reason() -> str | None:
    try:
        safety = RuntimeSafety.from_env()
    except ConfigurationError as exc:
        return f"CONFIGURATION_INVALID: {exc}"
    if safety.dry_run:
        return "DRY_RUN: paid providers and WordPress writes are disabled."
    return None
