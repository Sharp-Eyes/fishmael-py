import collections.abc
import typing

__all__: collections.abc.Sequence[str] = ("get_and_cast", "get_and_cast_or")


T_co = typing.TypeVar("T_co", covariant=True)
T = typing.TypeVar("T")
D = typing.TypeVar("D")


class SupportsCastFromBytes(typing.Protocol[T_co]):
    def __call__(self, arg: bytes, /) -> T_co: ...


def get_and_cast(
    src: collections.abc.Mapping[bytes, bytes],
    key: bytes,
    type_: SupportsCastFromBytes[T],
    *,
    default: D = None,
) -> T | D:
    if key in src:
        return type_(src[key])
    return default

def get_and_cast_or(
    src: collections.abc.Mapping[bytes, bytes],
    key: bytes,
    type_: SupportsCastFromBytes[T],
    *,
    default_factory: collections.abc.Callable[[], T],
) -> T:
    if key in src:
        return type_(src[key])
    return default_factory()
