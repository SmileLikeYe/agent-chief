"""Implements SPEC §4.4 stage 1 + Principle 3: POLICY.md parsing.

Grammar (kept deliberately tiny; anything else is ignored with a warning):
- under ``## Muted topics``: ``- <topic>``
- under ``## Rules``: ``- <topic-glob> -> <route>`` (also accepts ``→``)
- ``## Learned`` lines are human-readable prose, never parsed as rules.
"""

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from core.schema import Route, Scene

logger = logging.getLogger(__name__)

_RULE_RE = re.compile(r"^-\s*(?P<pattern>\S+)\s*(?:->|→)\s*(?P<route>\w+)\s*$")
_ITEM_RE = re.compile(r"^-\s*(?P<topic>\S+)\s*$")
_THRESHOLD_RE = re.compile(r"^-\s*(?P<scene>\w+)\s*=\s*(?P<value>[\d.]+)\s*$")
_ROUTES = set(get_args(Route))
_SCENES = set(get_args(Scene))


@dataclass
class PolicyRule:
    pattern: str
    route: str

    def matches(self, topic: str) -> bool:
        return fnmatch.fnmatch(topic, self.pattern)


@dataclass
class Policy:
    muted_topics: set[str] = field(default_factory=set)
    rules: list[PolicyRule] = field(default_factory=list)
    scene_thresholds: dict[str, float] = field(default_factory=dict)

    def is_muted(self, topic: str) -> bool:
        return any(fnmatch.fnmatch(topic, m) for m in self.muted_topics)

    def route_for(self, topic: str) -> PolicyRule | None:
        for rule in self.rules:
            if rule.matches(topic):
                return rule
        return None


def parse_policy(text: str) -> Policy:
    """Parse POLICY.md. Bad lines are ignored with a warning, never crash (SPEC §4.6)."""
    policy = Policy()
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            section = stripped.lstrip("#").strip().lower()
            continue
        if not stripped.startswith("-"):
            continue
        if section.startswith("muted"):
            m = _ITEM_RE.match(stripped)
            if m:
                policy.muted_topics.add(m.group("topic"))
            else:
                logger.warning("POLICY.md: ignoring unparseable muted line: %r", stripped)
        elif section.startswith("rules"):
            m = _RULE_RE.match(stripped)
            if m and m.group("route") in _ROUTES:
                policy.rules.append(PolicyRule(m.group("pattern"), m.group("route")))
            else:
                logger.warning("POLICY.md: ignoring unparseable rule line: %r", stripped)
        elif section.startswith("scene"):
            m = _THRESHOLD_RE.match(stripped)
            if m and m.group("scene") in _SCENES:
                policy.scene_thresholds[m.group("scene")] = float(m.group("value"))
            else:
                logger.warning("POLICY.md: ignoring unparseable threshold line: %r", stripped)
        # "learned" section is prose for humans; never parsed.
    return policy


def load_policy(path: str | Path) -> Policy:
    path = Path(path).expanduser()
    if not path.exists():
        return Policy()
    return parse_policy(path.read_text(encoding="utf-8"))


def add_muted_topic(path: str | Path, topic: str) -> None:
    """Append a topic under '## Muted topics', creating file/section as needed.

    Manual-edit friendly and idempotent; effective immediately (Principle 3).
    """
    path = Path(path).expanduser()
    if load_policy(path).is_muted(topic):
        return
    text = path.read_text(encoding="utf-8") if path.exists() else "# POLICY\n"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower().lstrip("#").strip().startswith("muted") and line.startswith("#"):
            lines.insert(i + 1, f"- {topic}")
            break
    else:
        lines += ["", "## Muted topics", f"- {topic}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
