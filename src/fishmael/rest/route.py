import collections.abc
import dataclasses
import sys
import typing

__all__: collections.abc.Sequence[str] = ("CompiledRoute", "Route")

_StrT = typing.TypeVar("_StrT", bound=typing.LiteralString)


def _intern(string: _StrT) -> _StrT:
    return typing.cast(_StrT, sys.intern(string))


GET: typing.Final = _intern("GET")
POST: typing.Final = _intern("POST")
PATCH: typing.Final = _intern("PATCH")
DELETE: typing.Final = _intern("DELETE")
PUT: typing.Final = _intern("PUT")


@dataclasses.dataclass(slots=True, frozen=True)
class Route:
    method: str
    path_template: str
    requires_auth: bool | None = dataclasses.field(default=None)
    # True:     auth MUST be provided
    # False:    auth MUST NOT be provided
    # None:     auth MAY be provided

    def compile(self, **url_params: object) -> "CompiledRoute":
        return CompiledRoute(self, self.path_template.format_map(url_params))

    def __str__(self) -> str:
        return f"({self.method}) {self.path_template}"


@dataclasses.dataclass(slots=True)
class CompiledRoute:
    route: Route = dataclasses.field()
    compiled_path: str = dataclasses.field()

    @property
    def method(self) -> str:
        return self.route.method

    @property
    def requires_auth(self) -> bool | None:
        return self.route.requires_auth

    def create_url(self, base_url: str) -> str:
        return base_url + self.compiled_path

    def __str__(self) -> str:
        return f"({self.route.method}) {self.compiled_path}"


GET_INTERACTION_RESPONSE: typing.Final = Route(GET, "/webhooks/{application_id}/{interaction_token}/messages/@original")
DELETE_INTERACTION_RESPONSE: typing.Final = Route(DELETE, "/webhooks/{application_id}/{interaction_token}/messages/@original")
PATCH_INTERACTION_RESPONSE: typing.Final = Route(PATCH, "/webhooks/{application_id}/{interaction_token}/messages/@original")
POST_INTERACTION_RESPONSE: typing.Final = Route(
    POST, "/interactions/{interaction_id}/{interaction_token}/callback",
)
