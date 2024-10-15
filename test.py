import asyncio
import collections.abc
import dataclasses
import os

import disagain
import dotenv

import fishmael


async def main() -> None:
    dotenv.load_dotenv()
    redis_url = os.environ["REDIS_URL"]
    client = disagain.Redis.from_url(redis_url)

    # For demonstration, make two streams that each handle one event type.
    readers = [
        fishmael.stream.ShardStreamReader.for_streams(
            fishmael.models.CommandInteraction,
            connection=await client.get_connection(),
            shard=fishmael.models.ShardId(0, 1),
        ),
        fishmael.stream.ShardStreamReader.for_streams(
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
    stream_readers: collections.abc.Sequence[fishmael.stream.ShardStreamReader]

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




if __name__ == "__main__":
    asyncio.run(main())
