"""D1 for the tests: the same two operations as the binding (workers/d1.py), on a SQLite file."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any


def _d1_params(params: Sequence[Any]) -> tuple[Any, ...]:
    """D1 binds every number as a JavaScript number: a REAL, never an INTEGER."""
    return tuple(float(p) if isinstance(p, int) and not isinstance(p, bool) else p for p in params)


class SqliteD1:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.execute("PRAGMA foreign_keys = ON")  # as in D1, where it is always on

    async def query(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[list[Any]]]:
        cursor = self.conn.execute(sql, _d1_params(params))
        columns = [d[0] for d in cursor.description or []]
        return columns, [list(row) for row in cursor.fetchall()]

    async def batch(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> list[int]:
        """All or nothing, like a D1 batch."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            changes = []
            for sql, params in statements:
                cursor = self.conn.execute(sql, _d1_params(params))
                changes.append(max(cursor.rowcount, 0))
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")
        return changes

    def close(self) -> None:
        self.conn.close()
