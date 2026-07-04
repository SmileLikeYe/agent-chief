"""Implements SPEC §4.4: all LLM prompts. No prompt strings live anywhere else (SPEC §7.4).

Three blocks, in prompt-caching-friendly order:
[system] stable; [context] semi-stable (cache per day); [user] per call.
"""

import json

from core.schema import Event
from judge.base import JudgeContext

SYSTEM_PROMPT = """You are the gatekeeper of the user's attention. Your sole duty is to protect it.
Your default answer is "do not disturb".
For each candidate event output JSON:
{"urgency":0-1,"relevance":0-1,"actionability":0-1,"novelty":0-1,"confidence":0-1,
 "dispatchable":true|false,"dispatch_goal":"one-line goal if dispatchable else null",
 "memorize":"one-line fact/intent worth remembering, else null",
 "reason":"one line"}
urgency = does value decay with time; relevance = match to user's goals;
actionability = what the user can do right now; novelty = new info vs recently delivered;
confidence = verifiability of evidence;
dispatchable = is there prep work an agent can complete without the user.
Output JSON only. Exaggeration and flattery are dereliction of duty. Temperature 0."""

RETRY_PROMPT = (
    "Your previous output was not the required JSON object. "
    "Answer again with ONLY the JSON object described in the instructions."
)

VERIFY_PROMPT = (
    "Does this result satisfy the acceptance criteria? Answer pass/fail + one reason.\n"
    'Output JSON only: {{"verdict":"pass"|"fail","reason":"one line"}}\n'
    "Acceptance criteria: {acceptance}\nResult: {result}"
)

DISTILL_PROMPT = (
    "Translate today's preference-weight changes into ONE short human-readable policy line "
    "a user would recognize, format exactly:\n"
    "- {{rule}} (learned {date}, source: {stats})\n"
    "Weight changes: {changes}\nOutput the single line only."
)

TOPIC_INFER_PROMPT = (
    "Assign a short hierarchical topic (like dev.ci or travel.flight_change) to this event. "
    "Output the topic string only, no punctuation around it.\nEvent: {summary}"
)


def context_block(ctx: JudgeContext) -> str:
    recent = "; ".join(ctx.recent_deliveries) or "none"
    memory = "; ".join(ctx.associated_memory) or "none"
    return (
        f"User profile: {ctx.user_profile or 'unknown'}\n"
        f"Recently delivered: {recent}\n"
        f"Associated memory: {memory}"
    )


def user_block(event: Event, ctx: JudgeContext) -> str:
    return (
        f"Current scene: {ctx.scene} (confidence {ctx.scene_confidence})\n"
        f"Candidate event: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}"
    )
