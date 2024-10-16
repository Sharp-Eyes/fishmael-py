import collections.abc
import dataclasses
import typing

from fishmael import models
from fishmael.events import base as events_base

__all__: collections.abc.Sequence[str] = (
    "InteractionEvent",
    "CommandInteractionEvent",
    "ComponentInteractionEvent",
)


@dataclasses.dataclass(slots=True)
class InteractionEvent(events_base.Event):
    interaction: models.protocol.Interaction

    @property
    def user_id(self) -> int:
        return self.interaction.user_id

    @property
    def guild_id(self) -> int | None:
        return self.interaction.guild_id

    @property
    def interaction_id(self) -> int:
        return self.interaction.id

    # TODO: async methods to get user etc from redis.


@events_base.register_for_streamables(models.CommandInteraction)
@dataclasses.dataclass(slots=True)
class CommandInteractionEvent(InteractionEvent):
    interaction: models.CommandInteraction  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def resolved_channels(self) -> collections.abc.Sequence[int]:
        return self.interaction.resolved_channels

    @property
    def resolved_messages(self) -> collections.abc.Sequence[int]:
        return self.interaction.resolved_messages

    @property
    def resolved_roles(self) -> collections.abc.Sequence[int]:
        return self.interaction.resolved_roles

    @property
    def resolved_users(self) -> collections.abc.Sequence[int]:
        return self.interaction.resolved_users

    async def get_user(self, user_id: int, /, *, as_member: bool = False) -> typing.NoReturn:
        raise NotImplementedError  # etc.


@events_base.register_for_streamables(models.ComponentInteraction)
@dataclasses.dataclass(slots=True)
class ComponentInteractionEvent(InteractionEvent):
    interaction: models.ComponentInteraction  # pyright: ignore[reportIncompatibleVariableOverride]

    @property
    def message_id(self) -> int:
        return self.interaction.message_id

    @property
    def custom_id(self) -> str:
        return self.interaction.custom_id
