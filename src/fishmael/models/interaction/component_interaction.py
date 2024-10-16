import collections.abc
import dataclasses
import typing

from fishmael.models import deserialise, shard

__all__: typing.Sequence[str] = ("ComponentInteraction",)


@dataclasses.dataclass(slots=True)
class ComponentInteraction:
    app_permissions: int | None
    application_id: int
    channel_id: int | None
    component_type: int
    custom_id: str
    guild_id: int | None
    guild_locale: str | None
    id: int
    kind: int
    locale: str | None
    message_id: int
    token: str
    user_id: int
    values: collections.abc.Sequence[str]

    @classmethod
    def from_raw(cls, raw: collections.abc.Mapping[bytes, bytes], /) -> "ComponentInteraction":
        return cls(
            app_permissions=deserialise.get_and_cast(raw, b"app_permissions", int),
            application_id=int(raw[b"application_id"]),
            channel_id=deserialise.get_and_cast(raw, b"channel_id", int),
            component_type=int(raw[b"component_type"]),
            custom_id=raw[b"custom_id"].decode(),
            guild_id=deserialise.get_and_cast(raw, b"guild_id", int),
            guild_locale=deserialise.get_and_cast(raw, b"guild_locale", bytes.decode),
            id=int(raw[b"id"]),
            kind=int(raw[b"kind"]),
            locale=deserialise.get_and_cast(raw, b"locale", bytes.decode),
            message_id=int(raw[b"message_id"]),
            token=raw[b"token"].decode(),
            user_id=int(raw[b"user_id"]),
            values=deserialise.get_and_cast_or(
                raw,
                b"values",
                lambda b: b.decode().split(),
                default_factory=list,
            ),
        )

    @classmethod
    def get_stream_key(cls, shard: shard.ShardId, /) -> bytes:
        return b"component_interaction:%i" % shard.number
