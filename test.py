import asyncio
import logging

import dotenv

import fishmael

logging.basicConfig(level=logging.INFO)

async def main() -> None:
    dotenv.load_dotenv()
    client = await fishmael.Fishmael.from_env()

    import os
    rest = fishmael.RestClient(os.environ["TOKEN"], "https://discord.com/api/v10")

    # Temporary workaround to client.start() blocking forever.
    t = asyncio.create_task(client.start())
    await asyncio.sleep(0)

    # Listen and do something with all events of the provided type.
    # TODO: Maybe also support predicates?
    @client.listen(
        fishmael.events.ComponentInteractionEvent,
        # predicate=lambda event: event.guild_id == 701039771157397526,
    )
    async def foo(event: fishmael.events.ComponentInteractionEvent):
        print(event)

    # Return the next event that matches the given type and predicate, or raise
    # asyncio.TimeoutError if nothing is found within 5 seconds.
    # try:
    #     await client.wait_for(
    #         fishmael.events.CommandInteractionEvent,
    #         predicate=lambda event: event.guild_id == 701039771157397526,
    #         timeout=5,
    #     )
    # except asyncio.TimeoutError:
    #     print("Timed out!")


    await asyncio.sleep(1)


    # Stream all events that match the given type and predicate for the next 10
    # seconds.
    with client.stream(
        fishmael.events.ComponentInteractionEvent,
        # predicate=lambda event: event.guild_id == 701039771157397526,
        timeout=10,
    ) as stream:
        async with rest:
            async for event in stream:
                print("IN STREAM!")
                await rest.create_interaction_response(
                    event.interaction_id,
                    event.interaction.token,
                    4,
                    "holy moly",
                )

    await t


if __name__ == "__main__":
    asyncio.run(main())
