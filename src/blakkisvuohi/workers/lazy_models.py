"""
Importing aiogram without building all of its pydantic models at once.

aiogram declares its Telegram types with `defer_build=True`, but then calls `model_rebuild()` on
every one of them when it is imported, which builds the validators and serialisers of several
hundred models. In a Worker that is about 75 MiB of the 128 MB an isolate may use: the Worker does
not even pass Cloudflare's startup check. The bot uses a few dozen of the models.

import_aiogram() imports aiogram with model_rebuild() only remembering the namespace aiogram gives
it (the names its forward references need), and hands that namespace to every type and method, so
that each model builds itself, completely, the first time it is used. Call it before anything
imports aiogram. The long running bot does not need it.
"""

from __future__ import annotations

import sys
from typing import Any


def import_aiogram() -> None:
    if "aiogram" in sys.modules:
        raise RuntimeError("aiogram was already imported: its models are built already")
    from pydantic import BaseModel

    original = BaseModel.__dict__["model_rebuild"].__func__
    namespace: dict[str, Any] = {}

    def remember_namespace(
        cls: type[BaseModel],
        *,
        force: bool = False,
        raise_errors: bool = True,
        _parent_namespace_depth: int = 2,
        _types_namespace: dict[str, Any] | None = None,
    ) -> bool | None:
        if _types_namespace is not None and not force:
            namespace.update(_types_namespace)
            return None  # built when first used
        return original(
            cls,
            force=force,
            raise_errors=raise_errors,
            _parent_namespace_depth=_parent_namespace_depth,
            _types_namespace=_types_namespace,
        )

    BaseModel.model_rebuild = classmethod(remember_namespace)  # type: ignore[assignment]
    try:
        import aiogram.methods
        import aiogram.types
    finally:
        BaseModel.model_rebuild = classmethod(original)  # type: ignore[assignment]

    for module in (aiogram.types, aiogram.methods):
        for name in module.__all__:
            model = getattr(module, name)
            if isinstance(model, type) and issubclass(model, BaseModel):
                own = model.__pydantic_parent_namespace__ or {}
                model.__pydantic_parent_namespace__ = {**namespace, **own}
