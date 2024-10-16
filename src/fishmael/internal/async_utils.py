import asyncio
import collections.abc
import typing

__all__: collections.abc.Sequence[str] = ("create_completed_future",)


_T = typing.TypeVar("_T")

def create_completed_future(result: _T = None, /) -> asyncio.Future[_T]:
    future = asyncio.get_running_loop().create_future()
    future.set_result(result)
    return future
