import collections.abc
import dataclasses
import json

from fishmael.models import deserialise, shard

__all__: collections.abc.Sequence[str] = ("CommandInteraction",)


@dataclasses.dataclass(slots=True)
class CommandInteraction:
    app_permissions: int | None
    application_id: int
    channel_id: int | None
    command_id: int
    guild_id: int | None
    guild_locale: str | None
    id: int
    kind: int
    locale: str | None
    options: collections.abc.Mapping[str, object]
    # pub resolved_attachments: collections.abc.Sequence[str]
    resolved_channels: collections.abc.Sequence[int]
    resolved_messages: collections.abc.Sequence[int]
    resolved_roles: collections.abc.Sequence[int]
    resolved_users: collections.abc.Sequence[int]
    target_id: int | None
    token: str
    user_id: int

    @classmethod
    def from_raw(cls, raw: collections.abc.Mapping[bytes, bytes]) -> "CommandInteraction":
        return cls(
            app_permissions=deserialise.get_and_cast(raw, b"app_permissions", int),
            application_id=int(raw[b"application_id"]),
            channel_id=deserialise.get_and_cast(raw, b"channel_id", int),
            command_id=int(raw[b"command_id"]),
            guild_id=deserialise.get_and_cast(raw, b"guild_id", int),
            guild_locale=deserialise.get_and_cast(raw, b"guild_locale", bytes.decode),
            id=int(raw[b"id"]),
            kind=int(raw[b"kind"]),
            locale=deserialise.get_and_cast(raw, b"locale", bytes.decode),
            options=json.loads(raw[b"options"]),
            # pub resolved_attachments=...
            resolved_channels=deserialise.get_and_cast_or(
                raw,
                b"resolved_channels",
                lambda b: list(map(int, b.decode().split())),
                default_factory=list,
            ),
            resolved_messages=deserialise.get_and_cast_or(
                raw,
                b"resolved_messages",
                lambda b: list(map(int, b.decode().split())),
                default_factory=list,
            ),
            resolved_roles=deserialise.get_and_cast_or(
                raw,
                b"resolved_roles",
                lambda b: list(map(int, b.decode().split())),
                default_factory=list,
            ),
            resolved_users=deserialise.get_and_cast_or(
                raw,
                b"resolved_users",
                lambda b: list(map(int, b.decode().split())),
                default_factory=list,
            ),
            target_id=deserialise.get_and_cast(raw, b"app_permissions", int),
            token=raw[b"token"].decode(),
            user_id=int(raw[b"user_id"]),
        )

    @classmethod
    def get_stream_key(cls, shard: shard.ShardId, /) -> bytes:
        return b"command_interaction:%i" % shard.number
