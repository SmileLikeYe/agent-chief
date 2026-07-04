"""Implements SPEC §10: chief home layout (`~/.chief`, overridable via CHIEF_HOME)."""

import os
import tomllib
from pathlib import Path


def chief_home() -> Path:
    return Path(os.environ.get("CHIEF_HOME", "~/.chief")).expanduser()


def db_path() -> Path:
    return chief_home() / "state.db"


def policy_path() -> Path:
    return chief_home() / "POLICY.md"


def user_md_path() -> Path:
    return chief_home() / "USER.md"


def config_path() -> Path:
    return chief_home() / "config.toml"


def audit_log_path() -> Path:
    return chief_home() / "logs" / "audit.jsonl"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))
