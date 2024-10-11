import collections.abc
import dataclasses

__all__: collections.abc.Sequence[str] = ("ShardId",)


@dataclasses.dataclass
class ShardId:
    number: int
    total: int
