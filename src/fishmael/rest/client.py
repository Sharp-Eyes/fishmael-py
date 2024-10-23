import asyncio
import collections.abc
import contextlib
import dataclasses
import http
import json
import sys
import typing

import aiohttp
import yarl

from fishmael.rest import route

__all__: collections.abc.Sequence[str] = ("RestClient",)


_APPLICATION_JSON: typing.Final[str] = sys.intern("application/json")
_AUTHORIZATION_HEADER: typing.Final = sys.intern("Authorization")
_USER_AGENT_HEADER: typing.Final = sys.intern("User-Agent")
_USER_AGENT: typing.Final = "DiscordBot (https://github.com/fishmael-dev/fishmael-py, 0.1.0)"
_RETRY_ERROR_CODES: typing.Final = frozenset((
    http.HTTPStatus.INTERNAL_SERVER_ERROR,
    http.HTTPStatus.BAD_GATEWAY,
    http.HTTPStatus.SERVICE_UNAVAILABLE,
    http.HTTPStatus.GATEWAY_TIMEOUT,
))
_UTF_8: typing.Final = "utf-8"


async def cancel_futures(futures: typing.Iterable[asyncio.Future[typing.Any]]) -> None:
    for future in futures:
        if not future.done() and not future.cancelled():
            future.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await future


async def first_completed(
    *awaitables: typing.Awaitable[typing.Any],
    timeout: float | None = None,
) -> None:
    futures = tuple(map(asyncio.ensure_future, awaitables))
    iter_ = asyncio.as_completed(futures, timeout=timeout)

    try:
        await next(iter_)
    finally:
        await cancel_futures(futures)


@dataclasses.dataclass
class RestClient:

    token: str
    base_url: str
    _session: aiohttp.ClientSession | None = dataclasses.field(default=None, init=False)
    _close_event: asyncio.Event | None = dataclasses.field(default_factory=asyncio.Event, init=False)

    def start(self) -> None:
        if self._session:
            msg = "Cannot start an already started REST client."
            raise RuntimeError(msg)

        self._close_event = asyncio.Event()
        self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if not self._session or not self._close_event:
            msg = "Cannot close an inactive REST client."
            raise RuntimeError(msg)

        self._close_event.set()
        self._close_event = None

        await self._session.close()
        self._session = None

    async def __aenter__(self) -> typing.Self:
        self.start()
        return self

    async def __aexit__(self, *_exc_data: object) -> None:
        await self.close()

    def _assert_session(self) -> aiohttp.ClientSession:
        if not self._session:
            msg = "Cannot use an inactive REST client."
            raise RuntimeError(msg)

        return self._session

    async def request(
        self,
        route: route.CompiledRoute,
        *,
        query: yarl.Query | None = None,
        data: collections.abc.Mapping[str, object] | collections.abc.Collection[object] | None = None,
    ):
        if not self._close_event:
            msg = "Cannot use an inactive REST client."
            raise RuntimeError(msg)

        request_task = asyncio.create_task(self._request(route, query=query, data=data))

        await first_completed(request_task, self._close_event.wait())

        if not request_task.cancelled():
            return request_task.result()

        msg = "The REST client was closed mid-request."
        raise RuntimeError(msg)

    async def _request(
        self,
        route: route.CompiledRoute,
        *,
        query: yarl.Query | None = None,
        data: collections.abc.Mapping[str, object] | collections.abc.Collection[object] | None = None,
    ) -> collections.abc.Mapping[str, object] | collections.abc.Collection[object] | None:
        session = self._assert_session()

        headers = {_USER_AGENT_HEADER: _USER_AGENT}
        if route.requires_auth:
            headers[_AUTHORIZATION_HEADER] = f"Bot {self.token}"

        payload = None
        if data is not None:
            payload = aiohttp.BytesPayload(
                json.dumps(data).encode(_UTF_8),
                content_type=_APPLICATION_JSON,
                encoding=_UTF_8,
            )

        try:
            response = await session.request(
                route.method,
                route.create_url(self.base_url),
                headers=headers,
                params=query,
                data=payload,
            )

        except (asyncio.TimeoutError, aiohttp.ClientConnectionError):  # noqa: TRY302
            # TODO: Retry logic
            raise

        if response.status == http.HTTPStatus.NO_CONTENT:
            return None

        if http.HTTPStatus.OK <= response.status < http.HTTPStatus.MULTIPLE_CHOICES:
            if response.content_type == _APPLICATION_JSON:
                return json.loads(await response.read())

            msg = f"expected JSON response, got {response.content_type!r} ({response.real_url!s})"
            raise RuntimeError(msg)

        if response.status in _RETRY_ERROR_CODES:
            # TODO: More retry logic
            raise NotImplementedError

        print(await response.read())

        response.raise_for_status()
        raise RuntimeError  # Should be unreachable.

    async def create_interaction_response(
        self,
        interaction_id: int,
        interaction_token: str,
        response_type: int,
        content: str,
    ) -> None:
        route_ = route.POST_INTERACTION_RESPONSE.compile(
            interaction_id=interaction_id,
            interaction_token=interaction_token,
        )

        data = {"content": content}
        body: dict[str, object] = {
            "type": response_type,
            "data": data,
        }

        await self.request(route_, data=body)
