import collections.abc
import dataclasses
import typing

from fishmael import models

__all__: collections.abc.Sequence[str] = ("Event", "ExceptionEvent")


EventT = typing.TypeVar("EventT", bound="Event")
InstantiableEventT = typing.TypeVar("InstantiableEventT", bound="InstantiableEvent")

EventCallbackT = collections.abc.Callable[[EventT], collections.abc.Coroutine[None, None, None]]


# NOTE: This protocol *must* be expliticly inherited from by *all* events.
class Event(typing.Protocol):
    """Base type for all events"""

    __slots__ = ()

    dispatches: typing.ClassVar[collections.abc.Sequence[type["Event"]]]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls.dispatches = tuple(sub_cls for sub_cls in cls.mro() if Event in sub_cls.mro())


Event.dispatches = (Event,)  # pyright: ignore[reportAttributeAccessIssue]


# NOTE: This works under the assumption that every event class will be
#       instantiated with a single Streamable as argument.
class InstantiableEvent(Event, typing.Protocol):
    dispatches: typing.ClassVar[collections.abc.Sequence[type["Event"]]]

    def __new__(cls: type[typing.Self], streamable: models.protocol.Streamable) -> typing.Self:
        ...


streamable_to_event_map: dict[type[models.protocol.Streamable], type[InstantiableEvent]] = {}


def register_for_streamables(
    *streamables: type[models.protocol.Streamable],
) -> collections.abc.Callable[[type[InstantiableEventT]], type[InstantiableEventT]]:
    def wrapper(cls: type[InstantiableEventT]) -> type[InstantiableEventT]:
        streamable_to_event_map.update(dict.fromkeys(streamables, cls))
        return cls

    return wrapper


@dataclasses.dataclass(slots=True)
class ExceptionEvent(Event):
    exception: Exception
    failed_event: Event
    failed_callback: EventCallbackT[Event]

    async def retry(self) -> None:
        await self.failed_callback(self.failed_event)
