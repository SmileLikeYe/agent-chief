"""Implements SPEC §4.4 + v3.1 Step 27: versioned prompt templates.

All prompts live in `judge/templates/<version>/*.j2` (provider-agnostic
variables); no prompt strings live anywhere else (SPEC §7.4). The active
version is stamped into every judged Decision's trace/audit record, and
`chief eval --compare vA vB` diffs two versions on the golden set. Rule
(CONTRIBUTING.md): no prompt change merges without an eval diff report.

Three blocks, in prompt-caching-friendly order:
[system] stable; [context] semi-stable (cache per day); [user] per call.
"""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from core.schema import Event
from judge.base import JudgeContext

TEMPLATES_ROOT = Path(__file__).parent / "templates"
PROMPT_VERSION = "v1"  # the active version, stamped into traces (Step 26)

_envs: dict[Path, Environment] = {}


def _env(root: Path) -> Environment:
    if root not in _envs:
        _envs[root] = Environment(
            loader=FileSystemLoader(root), undefined=StrictUndefined, autoescape=False
        )
    return _envs[root]


def render(name: str, version: str | None = None, root: Path | None = None, **vars) -> str:
    version = version or PROMPT_VERSION
    return _env(Path(root or TEMPLATES_ROOT)).get_template(f"{version}/{name}.j2").render(**vars)


def template_exists(name: str, version: str | None = None, root: Path | None = None) -> bool:
    try:
        _env(Path(root or TEMPLATES_ROOT)).get_template(f"{version or PROMPT_VERSION}/{name}.j2")
        return True
    except TemplateNotFound:
        return False


def available_versions(root: Path | None = None) -> list[str]:
    root = Path(root or TEMPLATES_ROOT)
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def verify_prompt(*, acceptance: str, result: str, version: str | None = None) -> str:
    return render("verify", version=version, acceptance=acceptance, result=result)


def distill_prompt(*, date: str, changes: str, version: str | None = None) -> str:
    return render("distill", version=version, date=date, changes=changes)


def topic_infer_prompt(*, summary: str, version: str | None = None) -> str:
    return render("topic_infer", version=version, summary=summary)


def context_block(ctx: JudgeContext, version: str | None = None) -> str:
    return render(
        "context",
        version=version,
        user_profile=ctx.user_profile,
        recent="; ".join(ctx.recent_deliveries),
        memory="; ".join(ctx.associated_memory),
    )


def user_block(event: Event, ctx: JudgeContext, version: str | None = None) -> str:
    return render(
        "user",
        version=version,
        scene=ctx.scene,
        scene_confidence=ctx.scene_confidence,
        event_json=json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
    )


# Rendered from the active version at import: the stable prompt-cache prefix.
SYSTEM_PROMPT = render("system")
RETRY_PROMPT = render("retry")
