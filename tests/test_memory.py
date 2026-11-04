"""Tests of session memory against a fake connection: owner scoping, idempotent turns, ordering, what is replayed.

No Postgres: the connection records the SQL it is given and answers from an in-memory table. The
live path (schema creation, inserts, read-back through a second helper, isolation of a second
session and another owner) is exercised by notebooks/agent_experiments.py.
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from psycopg import sql

from evidence_curator.memory import LakebaseMemory, replayable, trim_history


class FakeConnection:
    """Enough of psycopg's connection for the memory module: execute() with parameters, transaction()."""

    def __init__(self, store: "FakeStore") -> None:
        self.store = store

    def execute(self, statement: sql.Composed | str, params: tuple[Any, ...] | None = None) -> "FakeCursor":
        """Record the statement and answer it from the fake table."""
        text = statement.as_string(None) if isinstance(statement, sql.Composed) else str(statement)
        self.store.statements.append((text, params))
        return FakeCursor(self.store.run(text, params or ()))

    @contextmanager
    def transaction(self):  # noqa: ANN201 - mirrors psycopg
        """Yield a no-op transaction block."""
        yield


class FakeCursor:
    """A list of rows."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        """All rows."""
        return self.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        """First row or None."""
        return self.rows[0] if self.rows else None


@dataclass
class FakeStore:
    """An in-memory session_messages table and the statements executed against it."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    statements: list[tuple[str, tuple[Any, ...] | None]] = field(default_factory=list)
    next_id: int = 1

    def run(self, text: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        """Interpret the four statements the module issues."""
        if text.startswith("INSERT"):
            session_id, owner, turn_id, message = params
            self.rows.append(
                {
                    "id": self.next_id,
                    "session_id": session_id,
                    "owner": owner,
                    "turn_id": turn_id,
                    "message": json.loads(message),
                }
            )
            self.next_id += 1
            return []
        if text.startswith("SELECT 1"):
            session_id, owner, turn_id = params
            return (
                [(1,)]
                if any(
                    r["session_id"] == session_id and r["owner"] == owner and r["turn_id"] == turn_id for r in self.rows
                )
                else []
            )
        if text.startswith("SELECT message"):
            session_id, owner = params
            rows = sorted(
                (r for r in self.rows if r["session_id"] == session_id and r["owner"] == owner), key=lambda r: r["id"]
            )
            return [(r["message"],) for r in rows]
        if text.startswith("SELECT session_id"):
            (owner, limit) = params
            counts: dict[str, int] = {}
            for r in self.rows:
                if r["owner"] == owner:
                    counts[r["session_id"]] = counts.get(r["session_id"], 0) + 1
            return list(counts.items())[:limit]
        return []  # DDL

    @contextmanager
    def connect(self):  # noqa: ANN201 - a connection context manager
        """Open a fake connection on this table."""
        yield FakeConnection(self)


def _memory(store: FakeStore, owner: str = "brad@example.com") -> LakebaseMemory:
    return LakebaseMemory(schema="llmops_dev_memory", owner=owner, connect=store.connect)


TURN = [
    {"role": "user", "content": "What did SURMOUNT-OSA report?"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search_papers", "arguments": "{}"}}],
    },
    {"role": "tool", "tool_call_id": "c1", "content": "{...8 KB of passages...}"},
    {
        "role": "assistant",
        "content": "AHI fell by 25 events/h (PMC11111111, NCT05412004).",
        "tools": [{"name": "search_papers", "arguments": {}}],
    },
]


def test_replayable_keeps_questions_and_final_answers_only() -> None:
    """Tool calls, tool results and empty assistant messages are not persisted."""
    kept = replayable(TURN)
    assert [m["role"] for m in kept] == ["user", "assistant"]
    assert kept[1]["tools"] == [{"name": "search_papers", "arguments": {}}]
    assert replayable([{"role": "assistant", "content": "   "}]) == []


def test_trim_history_starts_at_a_user_message() -> None:
    """The replayed window never opens on an answer without its question."""
    messages = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    assert trim_history(messages, 3) == messages[2:]
    assert trim_history(messages, 4) == messages
    assert trim_history(messages, 1) == []
    assert trim_history(messages, 0) == []


def test_schema_name_is_validated() -> None:
    """A schema name is interpolated as an identifier, so it must be a plain one."""
    with pytest.raises(ValueError, match="identifier"):
        LakebaseMemory(schema="dev; DROP TABLE x", owner="x", connect=FakeStore().connect)
    with pytest.raises(ValueError, match="LakebaseConnector"):
        LakebaseMemory(schema="ok", owner="x")


def test_ensure_schema_creates_schema_table_and_index() -> None:
    """The one-time setup issues three qualified DDL statements."""
    store = FakeStore()
    _memory(store).ensure_schema()
    texts = [t for t, _ in store.statements]
    assert texts[0].startswith('CREATE SCHEMA IF NOT EXISTS "llmops_dev_memory"')
    assert 'CREATE TABLE IF NOT EXISTS "llmops_dev_memory"."session_messages"' in texts[1]
    assert "owner       TEXT NOT NULL" in texts[1] and "turn_id     TEXT NOT NULL" in texts[1]
    assert "(session_id, owner, id)" in texts[2]


def test_save_turn_scopes_rows_to_the_owner_and_tags_the_turn() -> None:
    """Every inserted row carries the owner and the turn id; the stored message keeps the turn id too."""
    store = FakeStore()
    written = _memory(store).save_turn("s1", "turn-1", TURN)
    assert written == 2
    inserts = [p for t, p in store.statements if t.startswith("INSERT")]
    assert all(p[0] == "s1" and p[1] == "brad@example.com" and p[2] == "turn-1" for p in inserts)
    assert json.loads(inserts[1][3])["turn_id"] == "turn-1"


def test_save_turn_is_idempotent_per_turn() -> None:
    """A retried save of the same turn inserts nothing; a new turn appends."""
    store = FakeStore()
    memory = _memory(store)
    assert memory.save_turn("s1", "turn-1", TURN) == 2
    assert memory.save_turn("s1", "turn-1", TURN) == 0
    assert memory.save_turn("s1", "turn-2", TURN) == 2
    assert len(store.rows) == 4


def test_load_messages_is_ordered_scoped_and_trimmed() -> None:
    """Messages come back in insertion order for this owner only; max_messages trims to whole turns."""
    store = FakeStore()
    memory = _memory(store)
    memory.save_turn("s1", "t1", [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}])
    memory.save_turn("s1", "t2", [{"role": "user", "content": "q2"}, {"role": "assistant", "content": "a2"}])
    _memory(store, owner="someone.else@example.com").save_turn(
        "s1", "t9", [{"role": "user", "content": "theirs"}, {"role": "assistant", "content": "x"}]
    )
    loaded = memory.load_messages("s1")
    assert [m["content"] for m in loaded] == ["q1", "a1", "q2", "a2"]
    assert all(m["turn_id"] in ("t1", "t2") for m in loaded)
    assert [m["content"] for m in memory.load_messages("s1", max_messages=3)] == ["q2", "a2"]
    assert memory.load_messages("s2") == []
    assert [m["content"] for m in _memory(store, owner="someone.else@example.com").load_messages("s1")] == [
        "theirs",
        "x",
    ]
    selects = [p for t, p in store.statements if t.startswith("SELECT message")]
    assert selects[0] == ("s1", "brad@example.com")


def test_sessions_lists_this_owners_sessions() -> None:
    """The inspection helper counts messages per session for the owner."""
    store = FakeStore()
    memory = _memory(store)
    memory.save_turn("s1", "t1", [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
    memory.save_turn("s2", "t1", [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
    assert sorted(memory.sessions()) == [("s1", 2), ("s2", 2)]
