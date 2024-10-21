import asyncio
import collections.abc
import dataclasses
import inspect
import logging
import types
import typing

from fishmael.events import base as events_base
from fishmael.events import stream as event_stream
from fishmael.internal import async_utils, class_utils

__all__: collections.abc.Sequence[str] = ("EventManager",)

_LOGGER: typing.Final[logging.Logger] = logging.getLogger(__name__)

DispatchPredicateT = typing.Callable[[events_base.EventT], bool]

# Listeners
ListenerPairT = tuple[
    DispatchPredicateT[events_base.EventT] | None,
    events_base.EventCallbackT[events_base.Event],
]
ListenerMap = dict[type[events_base.Event], set[ListenerPairT[events_base.Event]]]

# Waiters
WaiterPairT = tuple[
    DispatchPredicateT[events_base.EventT] | None,
    asyncio.Future[events_base.EventT],
]
WaiterMap = dict[type[events_base.Event], set[WaiterPairT[events_base.Event]]]

# Streams
StreamPairT: typing.TypeAlias = tuple[
    DispatchPredicateT[events_base.EventT] | None,
    event_stream.EventStream[events_base.EventT],
]
StreamMap = dict[type[events_base.Event], set[StreamPairT[events_base.Event]]]


@dataclasses.dataclass(slots=True)
class EventManager:
    _listeners: ListenerMap = dataclasses.field(default_factory=dict, init=False)
    _waiters: WaiterMap = dataclasses.field(default_factory=dict, init=False)
    _streams: StreamMap = dataclasses.field(default_factory=dict, init=False)

    async def _handle_callback(
        self,
        callback: events_base.EventCallbackT[events_base.Event],
        predicate: DispatchPredicateT[events_base.Event] | None,
        event: events_base.Event,
    ) -> None:
        try:
            if not predicate or predicate(event):
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
            for predicate, callback in self._listeners.get(event_type, ()):
                tasks.append(self._handle_callback(callback, predicate, event))

            for predicate, future in self._waiters.get(event_type, ()):
                if future.done():
                    continue

                try:
                    if not predicate or predicate(event):
                        future.set_result(event)

                except Exception as exc:  # noqa: BLE001
                    future.set_exception(exc)

            for predicate, stream in self._streams.get(event_type, ()):
                if stream.is_closed():
                    continue

                try:
                    if not predicate or predicate(event):
                        stream.send(event)

                except Exception as exc:  # noqa: BLE001
                    stream.send(exc)
                    del stream

        return asyncio.gather(*tasks) if tasks else async_utils.create_completed_future()

    def subscribe(
        self,
        event_type: type[events_base.EventT],
        callback: events_base.EventCallbackT[events_base.EventT],
        *,
        predicate: DispatchPredicateT[events_base.EventT] | None = None,
    ) -> None:
        pair = typing.cast(ListenerPairT[events_base.Event], (predicate, callback))
        try:
            self._listeners[event_type].add(pair)
        except KeyError:
            self._listeners[event_type] = {pair}

    def unsubscribe(
        self,
        event_type: type[events_base.EventT],
        callback: events_base.EventCallbackT[events_base.EventT],
        *,
        predicate: DispatchPredicateT[events_base.EventT] | None = None,
        allow_search: bool = True,
    ) -> None:
        listeners = self._listeners.get(event_type)
        if not listeners:
            return

        if predicate:
            pair = typing.cast(ListenerPairT[events_base.Event], (predicate, callback))
            listeners.discard(pair)  # pyright: ignore[reportArgumentType]

        else:
            pair = typing.cast(ListenerPairT[events_base.Event], (None, callback))
            if pair in listeners:
                listeners.remove(pair)

            elif allow_search:
                for pair in listeners.copy():
                    if pair[1] == callback:
                        listeners.remove(pair)

        if not listeners:
            del self._listeners[event_type]

    def get_listeners(
        self,
        event_type: type[events_base.EventT],
        /,
        *,
        polymorphic: bool = True,
    ) -> typing.Collection[events_base.EventCallbackT[events_base.EventT]]:
        if polymorphic:
            listeners: list[events_base.EventCallbackT[events_base.EventT]] = []
            for event in event_type.dispatches:
                listeners.extend(self.get_listeners(event, polymorphic=False))

            return listeners

        if event_type not in self._listeners:
            return ()

        _, listeners = zip(*self._listeners[event_type], strict=True)
        return listeners

    def listen(
        self,
        *event_types: type[events_base.EventT],
        predicate: DispatchPredicateT[events_base.EventT] | None = None,
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

                self.subscribe(event_type, callback, predicate=predicate)

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
    ) -> event_stream.EventStream[events_base.EventT]:
        stream_set: set[StreamPairT[events_base.Event]]
        stream: event_stream.EventStream[events_base.EventT] = event_stream.EventStream()

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
