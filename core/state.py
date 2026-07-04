"""Implements SPEC §3: sqlite state layer (8 tables) and audit JSONL writer."""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from core.schema import Decision, Event, MemoryItem, SceneState, Task

TABLES = [
    "events",
    "decisions",
    "tasks",
    "memory",
    "memory_archive",
    "feedback",
    "topic_weights",
    "scene_log",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, topic TEXT, dedup_key TEXT, received_at TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
    event_id TEXT PRIMARY KEY, route TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, status TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory (
    id TEXT PRIMARY KEY, topic TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_archive (
    id TEXT PRIMARY KEY, topic TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (
    rowid_ INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, signal TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS topic_weights (
    topic TEXT PRIMARY KEY, weights TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scene_log (
    rowid_ INTEGER PRIMARY KEY AUTOINCREMENT, scene TEXT, at TEXT, data TEXT NOT NULL);
"""


class State:
    """Async persistence over a single SQLite file (`~/.chief/state.db` by default)."""

    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @classmethod
    @asynccontextmanager
    async def open(cls, path: str | Path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
            yield cls(db)

    async def table_names(self) -> list[str]:
        rows = await self._db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table'")
        return [r[0] for r in rows]

    async def _put(self, sql: str, params: tuple) -> None:
        await self._db.execute(sql, params)
        await self._db.commit()

    async def _get_data(self, sql: str, params: tuple) -> str | None:
        rows = await self._db.execute_fetchall(sql, params)
        return rows[0][0] if rows else None

    # events
    async def save_event(self, ev: Event) -> None:
        await self._put(
            "INSERT OR REPLACE INTO events (id, topic, dedup_key, received_at, data)"
            " VALUES (?,?,?,?,?)",
            (ev.id, ev.topic, ev.dedup_key, ev.received_at.isoformat(), ev.model_dump_json()),
        )

    async def load_event(self, event_id: str) -> Event | None:
        data = await self._get_data("SELECT data FROM events WHERE id=?", (event_id,))
        return Event.model_validate_json(data) if data else None

    # decisions
    async def save_decision(self, d: Decision) -> None:
        await self._put(
            "INSERT OR REPLACE INTO decisions (event_id, route, data) VALUES (?,?,?)",
            (d.event_id, d.route, d.model_dump_json()),
        )

    async def load_decision(self, event_id: str) -> Decision | None:
        data = await self._get_data("SELECT data FROM decisions WHERE event_id=?", (event_id,))
        return Decision.model_validate_json(data) if data else None

    # tasks
    async def save_task(self, t: Task) -> None:
        await self._put(
            "INSERT OR REPLACE INTO tasks (id, status, data) VALUES (?,?,?)",
            (t.id, t.status, t.model_dump_json()),
        )

    async def load_task(self, task_id: str) -> Task | None:
        data = await self._get_data("SELECT data FROM tasks WHERE id=?", (task_id,))
        return Task.model_validate_json(data) if data else None

    # memory
    async def save_memory(self, m: MemoryItem, archive: bool = False) -> None:
        table = "memory_archive" if archive else "memory"
        await self._put(
            f"INSERT OR REPLACE INTO {table} (id, topic, data) VALUES (?,?,?)",
            (m.id, m.topic, m.model_dump_json()),
        )

    async def load_memory(self, memory_id: str) -> MemoryItem | None:
        data = await self._get_data("SELECT data FROM memory WHERE id=?", (memory_id,))
        return MemoryItem.model_validate_json(data) if data else None

    # feedback
    async def save_feedback(self, event_id: str, signal: str, at) -> None:
        await self._put(
            "INSERT INTO feedback (event_id, signal, at) VALUES (?,?,?)",
            (event_id, signal, at.isoformat()),
        )

    async def feedback_rows(self) -> list[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT event_id, signal, at FROM feedback ORDER BY rowid_"
        )
        return [{"event_id": r[0], "signal": r[1], "at": r[2]} for r in rows]

    # scene log
    async def log_scene(self, s: SceneState) -> None:
        await self._put(
            "INSERT INTO scene_log (scene, at, data) VALUES (?,?,?)",
            (s.scene, s.at.isoformat(), s.model_dump_json()),
        )

    async def recent_scenes(self, n: int) -> list[SceneState]:
        rows = await self._db.execute_fetchall(
            "SELECT data FROM scene_log ORDER BY rowid_ DESC LIMIT ?", (n,)
        )
        return [SceneState.model_validate_json(r[0]) for r in rows]


class AuditLog:
    """Append-only JSONL audit trail at `~/.chief/logs/audit.jsonl` (SPEC §4.2)."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
