import asyncio
import collections.abc
import dataclasses
import enum
import inspect
import logging
import types
import typing

from fishmael.events import base as events_base
from fishmael.internal import async_utils, class_utils

__all__: collections.abc.Sequence[str] = ("EventManager",)

_LOGGER: typing.Final[logging.Logger] = logging.getLogger(__name__)

# Listeners
ListenerMap = dict[
    type[events_base.Event],
    list[events_base.EventCallbackT[events_base.Event]],
]

# Waiters
DispatchPredicateT = typing.Callable[[events_base.EventT], bool]
WaiterPairT = tuple[
    DispatchPredicateT[events_base.EventT] | None,
    asyncio.Future[events_base.EventT],
]
WaiterMap = dict[type[events_base.Event], set[WaiterPairT[events_base.Event]]]

# Streams
_T = typing.TypeVar("_T")
DoneCallback = collections.abc.Callable[[_T], None]
StreamPairT: typing.TypeAlias = tuple[
    DispatchPredicateT[events_base.EventT] | None,
    "EventStream[events_base.EventT]",
]
StreamMap = dict[type[events_base.Event], set[StreamPairT[events_base.Event]]]
StreamQueue = asyncio.Queue[events_base.EventT | None | Exception]


@dataclasses.dataclass(slots=True)
class EventManager:
    _listeners: ListenerMap = dataclasses.field(default_factory=dict, init=False)
    _waiters: WaiterMap = dataclasses.field(default_factory=dict, init=False)
    _streams: StreamMap = dataclasses.field(default_factory=dict, init=False)

    async def _handle_callback(
        self,
        callback: events_base.EventCallbackT[events_base.Event],
        event: events_base.Event,
    ) -> None:
        try:
            await callback(event)

        except Exception as exc:
            if isinstance(event, events_base.ExceptionEvent):
                exc_info = type(exc), exc, exc.__traceback__.tb_next if exc.__traceback__ else None

                _LOGGER.exception(
                    "An exception occurred while handling event %r in '%s.%s', and was ignored.",
                    type(event).__name__,
                    callback.__module__,
                    callback.__qualname__,
                    exc_info=exc_info,
                )
                return

            _LOGGER.exception(
                "An exception occurred while handling event %r in '%s.%s'.",
                type(event).__name__,
                callback.__module__,
                callback.__qualname__,
            )
            await self.dispatch(events_base.ExceptionEvent(exc, event, callback))

    def dispatch(self, event: events_base.Event) -> asyncio.Future[typing.Any]:  # noqa: C901
        tasks: list[collections.abc.Coroutine[None, None, None]] = []

        for event_type in event.dispatches:
            for callback in self._listeners.get(event_type, ()):
                tasks.append(self._handle_callback(callback, event))  # noqa: PERF401

            for predicate, future in self._waiters.get(event_type, ()):
                if future.done():
                    continue

                try:
                    if predicate and predicate(event):
                        future.set_result(event)

                except Exception as exc:  # noqa: BLE001
                    future.set_exception(exc)

            for predicate, stream in self._streams.get(event_type, ()):
                if stream.is_closed():
                    continue

                try:
                    if predicate and predicate(event):
                        stream.send(event)

                except Exception as exc:  # noqa: BLE001
                    stream.send(exc)
                    del stream

        return asyncio.gather(*tasks) if tasks else async_utils.create_completed_future()

    def subscribe(
        self,
        event_type: type[events_base.EventT],
        callback: events_base.EventCallbackT[events_base.EventT],
    ) -> None:
        try:
            self._listeners[event_type].append(callback)  # pyright: ignore[reportArgumentType]
        except KeyError:
            self._listeners[event_type] = [callback]  # pyright: ignore[reportArgumentType]

    def unsubscribe(
        self,
        event_type: type[events_base.EventT],
        callback: events_base.EventCallbackT[events_base.EventT],
    ) -> None:
        listeners = self._listeners.get(event_type)
        if not listeners:
            return

        listeners.remove(callback)  # pyright: ignore[reportArgumentType]
        if not listeners:
            del self._listeners[event_type]

    def listen(
        self,
        *event_types: type[events_base.EventT],
    ) -> collections.abc.Callable[
        [events_base.EventCallbackT[events_base.EventT]],
        events_base.EventCallbackT[events_base.EventT],
    ]:
        def wrapper(
            callback: events_base.EventCallbackT[events_base.EventT],
        ) -> events_base.EventCallbackT[events_base.EventT]:
            signature = inspect.signature(callback)
            parameters = signature.parameters.values()
            event_param = next(iter(parameters))
            annotation = event_param.annotation

            if annotation is inspect.Parameter.empty:
                if not event_types:
                    msg = (
                        "Please provide the event type either as an argument to"
                        " the decorator or as a type hint."
                    )
                    raise TypeError(msg)

                resolved_types = event_types

            elif typing.get_origin(annotation) in (typing.Union, types.UnionType):
                resolved_types = {
                    class_utils.strip_generic(ann)
                    for ann in typing.get_args(annotation)
                }

            else:
                resolved_types = {class_utils.strip_generic(annotation)}

            for event_type in resolved_types:
                if events_base.Event not in event_type.mro():
                    msg = f"Expected event class, got {event_type.__name__!r}"
                    raise TypeError(msg)

                self.subscribe(event_type, callback)

            return callback

        return wrapper

    async def wait_for(
        self,
        event_type: type[events_base.EventT],
        /,
        *,
        timeout: float | None = None,
        predicate: DispatchPredicateT[events_base.EventT] | None = None,
    ) -> events_base.EventT:
        waiter_set: set[WaiterPairT[events_base.Event]]
        future: asyncio.Future[events_base.EventT] = asyncio.get_running_loop().create_future()

        try:
            waiter_set = self._waiters[event_type]
        except KeyError:
            waiter_set = self._waiters[event_type] = set()

        pair = typing.cast(WaiterPairT[events_base.Event], (predicate, future))
        waiter_set.add(pair)

        try:
            return await asyncio.wait_for(future, timeout)

        finally:
            waiter_set.remove(pair)
            if not waiter_set:
                del self._waiters[event_type]

    def stream(
        self,
        event_type: type[events_base.EventT],
        /,
        *,
        timeout: float | None = None,
        predicate: DispatchPredicateT[events_base.EventT] | None = None,
    ) -> "EventStream[events_base.EventT]":
        stream_set: set[StreamPairT[events_base.Event]]
        stream: EventStream[events_base.EventT] = EventStream()

        try:
            stream_set = self._streams[event_type]
        except KeyError:
            stream_set = self._streams[event_type] = set()

        pair = typing.cast(StreamPairT[events_base.Event], (predicate, stream))
        stream_set.add(pair)
        stream.add_done_callback(lambda _: stream_set.discard(pair))

        if timeout:
            loop = asyncio.get_running_loop()
            timeout_handle = loop.call_later(timeout, stream.stop)
            stream.add_done_callback(lambda _: timeout_handle.cancel())

        return stream


class EventStreamState(enum.Enum):
    CLOSED = enum.auto()
    STARTING = enum.auto()
    STREAMING = enum.auto()


@dataclasses.dataclass(slots=True)
class EventStreamIterator(typing.Generic[events_base.EventT]):
    exception: Exception | None = dataclasses.field(default=None, init=False)
    state: EventStreamState = dataclasses.field(default=EventStreamState.STARTING)
    queue: StreamQueue[events_base.EventT] = dataclasses.field(default_factory=asyncio.Queue)

    def __aiter__(self) -> collections.abc.AsyncIterator[events_base.EventT]:
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
            msg = "Cannot send to a closed stream."
            raise RuntimeError(msg)

        self._iterator.queue.put_nowait(event)

    def stop(self) -> None:
        if self._iterator.state is not EventStreamState.CLOSED:
            self._iterator.queue.put_nowait(None)

    def __enter__(self) -> EventStreamIterator[events_base.EventT]:
        self._iterator = EventStreamIterator()
        return self._iterator

    def __exit__(self, *_exc_info: object) -> None:
        for callback in self._callbacks:
            callback(self)

        self._callbacks.clear()

        if self._iterator.exception:
            raise self._iterator.exception
