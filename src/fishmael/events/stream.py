import asyncio
import collections.abc
import dataclasses
import enum
import typing

from fishmael.events import base as events_base

__all__: collections.abc.Sequence[str] = ("EventStream",)


_T = typing.TypeVar("_T")
DoneCallback = collections.abc.Callable[[_T], None]
StreamQueue = asyncio.Queue[events_base.EventT | None | Exception]


class EventStreamState(enum.Enum):
    CLOSED = enum.auto()
    STARTING = enum.auto()
    STREAMING = enum.auto()


@dataclasses.dataclass(slots=True)
class EventStreamIterator(typing.Generic[events_base.EventT]):
    exception: Exception | None = dataclasses.field(default=None, init=False)
    queue: StreamQueue[events_base.EventT] = dataclasses.field(default_factory=asyncio.Queue)
    state: EventStreamState = dataclasses.field(default=EventStreamState.STARTING)

    def __aiter__(self) -> collections.abc.AsyncIterator[events_base.EventT]:
        if self.state is EventStreamState.STREAMING:
            msg = (
                "Cannot iterate over the same event stream from multiple"
                " locations simultaneously."
            )
            raise RuntimeError(msg)

        if self.state is EventStreamState.CLOSED:
            self.exception = None
            self.queue = asyncio.Queue()

        self.state = EventStreamState.STREAMING
        return self

    async def __anext__(self) -> events_base.EventT:
        item = await self.queue.get()
        if item is None:
            self.state = EventStreamState.CLOSED
            raise StopAsyncIteration

        if isinstance(item, Exception):
            self.exception = item
            self.state = EventStreamState.CLOSED
            raise StopAsyncIteration

        return item

@dataclasses.dataclass(eq=False, init=False, slots=True, weakref_slot=True)
class EventStream(typing.Generic[events_base.EventT]):
    _iterator: EventStreamIterator[events_base.EventT]
    _callbacks: list[DoneCallback[typing.Self]]

    def __init__(self) -> None:
        self._iterator = EventStreamIterator()
        self._callbacks = []

    def is_closed(self) -> bool:
        return self._iterator.state is EventStreamState.CLOSED

    def add_done_callback(self, callback: DoneCallback[typing.Self]) -> None:
        if self.is_closed():
            asyncio.get_running_loop().call_soon(callback, self)

        else:
            self._callbacks.append(callback)

    def send(self, event: events_base.EventT | Exception) -> None:
        if self._iterator.state is EventStreamState.CLOSED:
            msg = "Cannot send to a closed event stream."
            raise RuntimeError(msg)

        self._iterator.queue.put_nowait(event)

    def stop(self) -> None:
        if self._iterator.state is not EventStreamState.CLOSED:
            self._iterator.queue.put_nowait(None)

    def __enter__(self) -> EventStreamIterator[events_base.EventT]:
        if self._iterator.state is EventStreamState.STREAMING:
            msg = "Cannot enter an already streaming event stream."
            raise RuntimeError(msg)

        return self._iterator

    def __exit__(self, *_exc_info: object) -> None:
        for callback in self._callbacks:
            callback(self)

        self._callbacks.clear()

        if self._iterator.exception:
            raise self._iterator.exception
