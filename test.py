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

    reader = ShardStreamReader(
        await client.get_connection(),
        fishmael.models.ShardId(0, 1),
    )

    async for entry in reader.stream(
        fishmael.models.CommandInteraction,
        fishmael.models.ComponentInteraction,
    ):
        print(entry, "\n")  # noqa: T201

    await client.disconnect()


@dataclasses.dataclass
class ShardStreamReader:
    connection: disagain.connection.ActionableConnection
    shard: fishmael.models.ShardId

    async def stream(
        self,
        *desired_streams: type[fishmael.models.protocol.Streamable],
    ) -> collections.abc.AsyncGenerator[fishmael.models.protocol.Streamable]:
        # Mapping of stream key to last-seen entry id in that stream
        streams_to_last_seen: dict[bytes | str, bytes] = {
            stream.get_stream_key(self.shard): b"0"
            for stream in desired_streams
        }

        # Mapping of stream key to event class.
        streams_to_class = dict(zip(streams_to_last_seen, desired_streams, strict=True))

        while True:
            res = await self.connection.xread(streams_to_last_seen, block=0)
            for stream_key, entries in res.items():
                event_cls = streams_to_class[stream_key]

                # Realistically if we're here, entries should always be of
                # length >=1. However, there's no way to communicate this to
                # Pyright, so we'll have to make do with this.
                entry_id = None
                for entry_id, entry_data in entries:  # noqa: B007
                    yield event_cls.from_raw(entry_data)

                if entry_id:
                    streams_to_last_seen[stream_key] = entry_id


if __name__ == "__main__":
    asyncio.run(main())
