"""Cancelable operation registry isolated by client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from typing import Protocol, TypeVar

from pydoll_mcp_server.errors import ErrorCode, StructuredError
from pydoll_mcp_server.json_types import JsonObject

T = TypeVar('T')


class CancelableOperation(Protocol):
    def done(self) -> bool: ...

    def cancel(self, msg: object | None = None) -> bool: ...


class OperationManager:
    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], CancelableOperation] = {}

    async def run(self, client_id: str, operation_id: str, awaitable: Awaitable[T]) -> T:
        if not operation_id:
            return await awaitable
        key = (client_id, operation_id)
        if key in self._tasks:
            if isinstance(awaitable, Coroutine):
                awaitable.close()
            raise StructuredError(ErrorCode.RESOURCE_LOCKED, f'Operation already exists: {operation_id}')
        task = asyncio.ensure_future(awaitable)
        self._tasks[key] = task
        try:
            return await task
        finally:
            self._tasks.pop(key, None)

    def cancel(self, client_id: str, operation_id: str) -> bool:
        task = self._tasks.get((client_id, operation_id))
        if task is None or task.done():
            return False
        task.cancel()
        return True


_MANAGER = OperationManager()


def get_operation_manager() -> OperationManager:
    return _MANAGER


async def operation_cancel(client_id: str, operation_id: str) -> JsonObject:
    cancelled = _MANAGER.cancel(client_id, operation_id)
    if not cancelled:
        return StructuredError(ErrorCode.RESOURCE_NOT_FOUND, 'Operation not found or already completed').to_dict()
    return {'success': True, 'operation_id': operation_id, 'cancelled': True}
