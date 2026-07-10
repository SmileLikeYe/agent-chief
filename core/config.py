"""Implements SPEC §10: chief home layout (`~/.chief`, overridable via CHIEF_HOME)."""

import json
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


class UnsupportedConfig(Exception):
    """The config contains TOML shapes the built-in serializer cannot preserve."""


def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list) and all(
        isinstance(item, str | int | float | bool) for item in value
    ):
        return "[" + ", ".join(json.dumps(item) for item in value) + "]"
    raise UnsupportedConfig(f"cannot serialize value {value!r}")


def serialize_config(config: dict) -> str:
    """Serialize Chief's flat sections plus one nested table level."""
    lines: list[str] = []
    for section, body in config.items():
        if not isinstance(body, dict):
            raise UnsupportedConfig(f"root-level key {section!r} is not a section")
        scalars = {key: value for key, value in body.items() if not isinstance(value, dict)}
        tables = {key: value for key, value in body.items() if isinstance(value, dict)}
        if scalars or not tables:
            lines.append(f"[{section}]")
            lines += [f"{key} = {_scalar(value)}" for key, value in scalars.items()]
            lines.append("")
        for subsection, subbody in tables.items():
            if any(isinstance(value, dict) for value in subbody.values()):
                raise UnsupportedConfig(f"[{section}.{subsection}] nests too deep")
            lines.append(f"[{section}.{subsection}]")
            lines += [f"{key} = {_scalar(value)}" for key, value in subbody.items()]
            lines.append("")
    return "\n".join(lines)


def ensure_private_home() -> Path:
    home = chief_home()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    return home


def write_private_text(path: Path, text: str) -> None:
    """Atomically write a file containing user data or credentials as mode 0600."""
    ensure_private_home()
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)
