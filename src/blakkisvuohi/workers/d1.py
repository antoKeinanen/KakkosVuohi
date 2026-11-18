"""
The D1 binding of the Worker, as the D1Client that db/d1.py needs. Only works inside a Worker.

The Workers Python SDK wraps the binding (env.DB): it converts the arguments to JavaScript (None
to null) and the results to Python, so plain Python values go in and come out.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _changes(result: Any) -> int:
    meta = result["meta"] if isinstance(result, dict) else result.meta
    changes = meta["changes"] if isinstance(meta, dict) else meta.changes
    return int(changes or 0)


class JsD1Client:
    def __init__(self, binding: Any) -> None:
        self._d1 = binding

    def _statement(self, sql: str, params: Sequence[Any]) -> Any:
        statement = self._d1.prepare(sql)
        return statement.bind(*params) if params else statement

    async def query(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[list[Any]]]:
        result = await self._statement(sql, params).raw({"columnNames": True})
        if not result:
            return [], []
        return list(result[0]), [list(row) for row in result[1:]]

    async def batch(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> list[int]:
        results = await self._d1.batch([self._statement(sql, params) for sql, params in statements])
        return [_changes(result) for result in results]
