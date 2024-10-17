import asyncio
import collections.abc
import dataclasses
import inspect
import logging
import types
import typing

from fishmael.events import base as events_base
from fishmael.internal import async_utils, class_utils

__all__: collections.abc.Sequence[str] = ("EventManager",)

_LOGGER: typing.Final[logging.Logger] = logging.getLogger(__name__)

ListenerMap = dict[
    type[events_base.Event],
    list[events_base.EventCallbackT[events_base.Event]],
]
WaiterPredicateT = typing.Callable[[events_base.EventT], bool]
WaiterPairT = tuple[WaiterPredicateT[events_base.Event] | None, asyncio.Future[events_base.EventT]]
WaiterMap = dict[type[events_base.Event], set[WaiterPairT[events_base.Event]]]


@dataclasses.dataclass
class EventManager:
    _listeners: ListenerMap = dataclasses.field(default_factory=dict, init=False)
    _waiters: WaiterMap = dataclasses.field(default_factory=dict, init=False)

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

    def dispatch(self, event: events_base.Event) -> asyncio.Future[typing.Any]:
        tasks: list[collections.abc.Coroutine[None, None, None]] = []

        for event_type in event.dispatches:
            for callback in self._listeners.get(event_type, ()):
                tasks.append(self._handle_callback(callback, event))  # noqa: PERF401

            if event_type not in self._waiters:
                continue

            for predicate, future in self._waiters[event_type]:
                if future.done():
                    continue

                try:
                    if predicate and predicate(event):
                        future.set_result(event)

                except Exception as exc:  # noqa: BLE001
                    future.set_exception(exc)

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
        predicate: WaiterPredicateT[events_base.EventT] | None = None,
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
            waiter_set.remove(pair)  # pyright: ignore[reportArgumentType]
            if not waiter_set:
                del self._waiters[event_type]
