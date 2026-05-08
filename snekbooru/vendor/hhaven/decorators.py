from collections.abc import Callable, Awaitable
from typing import Any, TypeVar
from . import exceptions

__all__ = ["requires_build", "requires_token", "cached"]

R = TypeVar("R")

def requires_build(func: Callable[..., R]) -> Callable[..., R]:
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> R:
        if not getattr(self, "_built", False):
            raise exceptions.HHavenException(
                "Hentai Haven client was not fully initialized. "
                "Remember to use client.build() to complete client initialization.",
                0,
            )
        return func(self, *args, **kwargs)
    return wrapper

def requires_token(func: Callable[..., R]) -> Callable[..., R]:
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> R:
        if not getattr(self, "token", None):
            raise exceptions.TokenException(
                "Hentai Haven token is missing. "
                "Use client.get_new_token() to obtain it.",
                0,
            )
        return func(self, *args, **kwargs)
    return wrapper

def cached(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> R:
        cache = getattr(self, "cache", None)
        ttl = getattr(self, "cache_ttl", None)
        key = f"{func.__name__}_{args}_{kwargs}"
        if cache:
            cached = await cache.get(key)
            if cached is not None:
                return cached
        result = await func(self, *args, **kwargs)
        if cache:
            await cache.set(key, result, ttl=ttl)
        return result
    return wrapper