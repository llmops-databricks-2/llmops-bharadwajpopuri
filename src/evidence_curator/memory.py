"""Session memory in Lakebase: the agent's conversation history, outside the process that answers.

A serving request carries no previous turn, so the application stores each turn's messages under a
session ID and loads them before the next model call; the agent process stays stateless and any
replica can continue any conversation. The store is one Postgres table in the same Lakebase
project as the chunk copy, in a schema per catalog (`llmops_dev_memory`, `llmops_acc_memory`, …)
because dev, acc and prd share the project while their Unity Catalog data stays apart.

Three decisions, from docs/agent_orchestration.md:

- **Only `user` and final `assistant` messages are persisted and replayed.** Tool-call and
  tool-result messages are run-time scaffolding whose `tool_call_id` pairs must survive intact
  to be replayed at all, and they would carry kilobytes of chunk text into every later prompt. The
  assistant message keeps a small `tools` list (names and arguments) so a conversation can be
  inspected, but that list is metadata, not a replayed message.
- **`owner` is part of every read and write.** A session ID is a correlation key, not an
  authorization check: rows are read and appended as `(session_id, owner)`, so a guessed session
  ID under another identity returns nothing. `owner` defaults to the connecting identity.
- **Appends are idempotent per turn.** Every message carries the `turn_id` of the request that
  produced it; saving a turn whose `turn_id` is already stored inserts nothing, so a retried
  request cannot duplicate history. Rows replay in insertion order (`id`), never by timestamp:
  the messages of one turn share a timestamp.

The teaching helper of the course (`arxiv_curator.memory.LakebaseMemory`) stores raw messages
ordered by `created_at` with a connection pool; this module keeps its table shape close enough to
compare and departs where the lecture notes say the teaching version falls short.
"""

import json
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any

import psycopg
from psycopg import sql

from evidence_curator.lakebase import LakebaseConnector

TABLE = "session_messages"
REPLAYED_ROLES = ("user", "assistant")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

Connect = Callable[[], AbstractContextManager[psycopg.Connection]]


def replayable(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the messages worth persisting: user questions and assistant answers without tool calls."""
    kept = []
    for message in messages:
        if message.get("role") not in REPLAYED_ROLES or message.get("tool_calls"):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        kept.append(message)
    return kept


def trim_history(messages: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    """Keep the last `max_messages`, cut so that the history starts at a user message."""
    if max_messages <= 0 or not messages:
        return []
    recent = messages[-max_messages:]
    for index, message in enumerate(recent):
        if message.get("role") == "user":
            return recent[index:]
    return []


class LakebaseMemory:
    """Owner-scoped, append-only session history in a Lakebase table."""

    def __init__(
        self,
        connector: LakebaseConnector | None = None,
        schema: str = "llmops_dev_memory",
        owner: str | None = None,
        connect: Connect | None = None,
    ) -> None:
        """Create the store.

        Args:
            connector: Opens connections for the current identity; `connect` may be given instead (tests).
            schema: Postgres schema holding the table, one per catalog.
            owner: Identity that owns the sessions read and written; defaults to the connecting role.
            connect: Connection factory used instead of the connector (tests, or an app's own pool).

        """
        if not _IDENT.match(schema):
            raise ValueError(f"Not a plain SQL identifier: {schema!r}")
        if connector is None and connect is None:
            raise ValueError("a LakebaseConnector or a connect() factory is required")
        self.connector = connector
        self._connect = connect or connector.connect  # type: ignore[union-attr]
        self.schema = schema
        self._owner = owner
        self.table = sql.Identifier(schema, TABLE)

    @property
    def owner(self) -> str:
        """The identity whose sessions this store reads and writes."""
        if self._owner is None:
            if self.connector is None:
                raise ValueError("owner is required when no connector identifies the caller")
            self._owner = self.connector.username()
        return self._owner

    def connect(self) -> AbstractContextManager[psycopg.Connection]:
        """One connection with a fresh credential."""
        return self._connect()

    def ensure_schema(self) -> None:
        """Create the schema, the table and its index if they do not exist (a one-time, privileged step)."""
        with self.connect() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            conn.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {table} (
                        id          BIGSERIAL PRIMARY KEY,
                        session_id  TEXT NOT NULL,
                        owner       TEXT NOT NULL,
                        turn_id     TEXT NOT NULL,
                        message     JSONB NOT NULL,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                ).format(table=self.table)
            )
            conn.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {index} ON {table} (session_id, owner, id)").format(
                    index=sql.Identifier(f"{TABLE}_session_owner_idx"), table=self.table
                )
            )

    def load_messages(self, session_id: str, max_messages: int | None = None) -> list[dict[str, Any]]:
        """Load a session's messages for this owner, oldest first, optionally trimmed to the last turns."""
        with self.connect() as conn:
            rows = conn.execute(
                sql.SQL("SELECT message FROM {table} WHERE session_id = %s AND owner = %s ORDER BY id").format(
                    table=self.table
                ),
                (session_id, self.owner),
            ).fetchall()
        messages = [row[0] for row in rows]
        return trim_history(messages, max_messages) if max_messages else messages

    def turn_saved(self, session_id: str, turn_id: str) -> bool:
        """Whether a turn is already stored (the idempotency check of `save_turn`)."""
        with self.connect() as conn:
            row = conn.execute(
                sql.SQL("SELECT 1 FROM {table} WHERE session_id = %s AND owner = %s AND turn_id = %s LIMIT 1").format(
                    table=self.table
                ),
                (session_id, self.owner, turn_id),
            ).fetchone()
        return row is not None

    def save_turn(self, session_id: str, turn_id: str, messages: list[dict[str, Any]]) -> int:
        """Append a turn's replayable messages in one transaction; returns rows written (0 when already saved)."""
        kept = replayable(messages)
        if not kept or self.turn_saved(session_id, turn_id):
            return 0
        with self.connect() as conn, conn.transaction():
            for message in kept:
                record = {**message, "turn_id": turn_id}
                conn.execute(
                    sql.SQL("INSERT INTO {table} (session_id, owner, turn_id, message) VALUES (%s, %s, %s, %s)").format(
                        table=self.table
                    ),
                    (session_id, self.owner, turn_id, json.dumps(record, ensure_ascii=False)),
                )
        return len(kept)

    def sessions(self, limit: int = 20) -> Iterator[tuple[str, int]]:
        """List this owner's sessions with their message counts, most recent first (for inspection)."""
        with self.connect() as conn:
            rows = conn.execute(
                sql.SQL(
                    "SELECT session_id, COUNT(*) FROM {table} WHERE owner = %s "
                    "GROUP BY session_id ORDER BY MAX(id) DESC LIMIT %s"
                ).format(table=self.table),
                (self.owner, limit),
            ).fetchall()
        return iter((row[0], int(row[1])) for row in rows)
