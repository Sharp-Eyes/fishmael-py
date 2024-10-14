import collections.abc
import typing

from fishmael.models.shard import ShardId

__all__: typing.Sequence[str] = ("StreamKeyProvider", "Streamable")


@typing.runtime_checkable
class StreamKeyProvider(typing.Protocol):
    @classmethod
    def get_stream_key(cls, shard: ShardId, /) -> bytes: ...


@typing.runtime_checkable
class Streamable(StreamKeyProvider, typing.Protocol):
    @classmethod
    def from_raw(cls, data: collections.abc.Mapping[bytes, bytes], /) -> "Streamable": ...
