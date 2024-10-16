
import asyncio
import collections.abc
import dataclasses
import os

import disagain

from fishmael import event_manager as event_manager_m
from fishmael import models, stream
from fishmael.events import base as events_base

__all__: collections.abc.Sequence[str] = ("Fishmael",)


@dataclasses.dataclass
class Fishmael:
    redis: disagain.Redis
    stream_readers: collections.abc.Sequence[stream.ShardStreamReader]
    event_manager: event_manager_m.EventManager

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

    @classmethod
    async def from_env(
        cls,
        *shards: models.ShardId,
        redis: disagain.Redis | tuple[str, int] | str | None = None,
        event_manager: event_manager_m.EventManager | None = None,
    ) -> "Fishmael":
        # First ensure we have an active redis connection...
        if isinstance(redis, disagain.Redis):
            pass

        elif isinstance(redis, tuple):
            redis = disagain.Redis(*redis)

        elif isinstance(redis, str):
            redis = disagain.Redis.from_url(redis)

        elif "REDIS_URL" in os.environ:
            redis = disagain.Redis.from_url(os.environ["REDIS_URL"])

        else:
            msg = (
                "Please set the `REDIS_URL` environment variable, or"
                " provide a (host, port) tuple or a redis url."
            )
            raise LookupError(msg)

        # Next, ensure we know what shards to use...
        if not shards:
            # TODO: Read from config instead of this.
            #       Alternatively maybe read from redis as this is somewhat
            #       dependent on the rust backend?
            shards = (models.ShardId(0, 1),)

        readers = [
            stream.ShardStreamReader.for_streams(
                # TODO: Simple way to get all streamables
                models.ComponentInteraction,
                models.CommandInteraction,
                connection=await redis.get_connection(),
                shard=shard,
            )
            for shard in shards
        ]

        # Finally, ensure we have an event manager...
        manager = event_manager or event_manager_m.EventManager()

        return cls(redis, readers, manager)

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

    async def dispatch(self, streamable: models.protocol.Streamable) -> None:
        event_cls = events_base.streamable_to_event_map[type(streamable)]
        event = event_cls(streamable)
        await self.event_manager.dispatch(event)

    def listen(
        self,
        *event_types: type[events_base.EventT],
    ) -> collections.abc.Callable[
        [events_base.EventCallbackT[events_base.EventT]],
        events_base.EventCallbackT[events_base.EventT],
    ]:
        return self.event_manager.listen(*event_types)
