import asyncio
import collections.abc
import dataclasses
import enum
import os
import typing

import disagain
import dotenv

import fishmael


async def main() -> None:
    dotenv.load_dotenv()
    redis_url = os.environ["REDIS_URL"]
    client = disagain.Redis.from_url(redis_url)

    # For demonstration, make two streams that each handle one event type.
    readers = [
        ShardStreamReader.for_streams(
            fishmael.models.CommandInteraction,
            connection=await client.get_connection(),
            shard=fishmael.models.ShardId(0, 1),
        ),
        ShardStreamReader.for_streams(
            fishmael.models.ComponentInteraction,
            connection=await client.get_connection(),
            shard=fishmael.models.ShardId(0, 1),
        ),
    ]

    # TODO: More convenient instantiation: e.g. default method that reads desired
    #       events from fishmael.toml and makes one reader for them per shard
    client = Fishmael(readers)
    await client.start()


@dataclasses.dataclass
class Fishmael:
    stream_readers: typing.Sequence["ShardStreamReader"]

    _stream_tasks: set[asyncio.Task[None]] = dataclasses.field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _closing_event: asyncio.Event = dataclasses.field(
        default_factory=asyncio.Event,
        init=False,
        repr=False,
    )

    async def start(self) -> None:
        for stream_reader in self.stream_readers:
            task = asyncio.create_task(stream_reader.stream_with_dispatcher(self.dispatch))
            self._stream_tasks.add(task)
            task.add_done_callback(self._stream_tasks.discard)

        # For the time being this means sleep forever.
        # TODO: Handle disconnects (make user-configurable; depending on usecase
        #       it may be desirable to keep this running even while the gateway
        #       is disconnected?)
        await self._closing_event.wait()

    async def dispatch(self, streamable: fishmael.models.protocol.Streamable) -> None:
        print("DISPATCH\n", streamable, "\n")  # noqa: T201


# TODO: Move to fishmael package.
class ShardStreamReaderState(enum.Enum):
    DISCONNECTED = enum.auto()
    STREAMING = enum.auto()


StreamToLastSeenMap: typing.TypeAlias = dict[bytes | str, bytes]
StreamToClassMap: typing.TypeAlias = dict[bytes | str, type[fishmael.models.protocol.Streamable]]

@dataclasses.dataclass
class ShardStreamReader:
    connection: disagain.connection.ActionableConnection
    shard: fishmael.models.ShardId

    _state: ShardStreamReaderState = dataclasses.field(
        default=ShardStreamReaderState.DISCONNECTED,
        init=False,
    )
    # Mapping of stream key to last-seen entry id in that stream
    _streams_to_last_seen: StreamToLastSeenMap = dataclasses.field(default_factory=dict, init=False)
    # Mapping of stream key to event class.
    _streams_to_class: StreamToClassMap = dataclasses.field(default_factory=dict, init=False)

    @classmethod
    def for_streams(
        cls,
        *desired_streams: type[fishmael.models.protocol.Streamable],
        connection: disagain.connection.ActionableConnection,
        shard: fishmael.models.ShardId,
    ) -> "ShardStreamReader":
        self = cls(connection, shard)
        self.add_streams(*desired_streams)
        return self

    def add_streams(self, *desired_streams: type[fishmael.models.protocol.Streamable]) -> None:
        if self._state is ShardStreamReaderState.STREAMING:
            msg = "ShardStreamReader streams cannot be modified while streaming."
            raise RuntimeError(msg)

        # TODO: Get and store actual last seen id.
        for stream_cls in desired_streams:
            key = stream_cls.get_stream_key(self.shard)
            self._streams_to_class[key] = stream_cls
            self._streams_to_last_seen[key] = b"0"

    @property
    def desired_streams(self) -> typing.Sequence[fishmael.models.protocol.Streamable]:
        return tuple(self._streams_to_class.values())

    def get_last_seen(self, stream: type[fishmael.models.protocol.Streamable]) -> bytes:
        return self._streams_to_last_seen[stream.get_stream_key(self.shard)]

    async def stream(self) -> collections.abc.AsyncGenerator[fishmael.models.protocol.Streamable]:
        while True:
            res = await self.connection.xread(self._streams_to_last_seen, block=0)
            for stream_key, entries in res.items():
                event_cls = self._streams_to_class[stream_key]

                # Realistically if we're here, entries should always be of
                # length >=1. However, there's no way to communicate this to
                # Pyright, so we'll have to make do with this.
                entry_id = None
                for entry_id, entry_data in entries:  # noqa: B007
                    yield event_cls.from_raw(entry_data)

                if entry_id:
                    self._streams_to_last_seen[stream_key] = entry_id

    async def stream_with_dispatcher(
        self,
        dispatcher: collections.abc.Callable[
            [fishmael.models.protocol.Streamable],
            collections.abc.Coroutine[None, None, None],
        ],
    ) -> None:
        async for entry in self.stream():
            await dispatcher(entry)


if __name__ == "__main__":
    asyncio.run(main())
