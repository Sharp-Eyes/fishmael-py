import collections.abc
import typing

from fishmael.models.shard import ShardId

class StreamKeyProvider(typing.Protocol):
    @classmethod
    def get_stream_key(cls, shard: ShardId, /) -> bytes: ...


class Streamable(StreamKeyProvider, typing.Protocol):
    @classmethod
    def from_raw(cls, data: collections.abc.Mapping[bytes, bytes], /) -> "Streamable": ...
