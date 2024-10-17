import asyncio
import logging

import dotenv

import fishmael

logging.basicConfig(level=logging.INFO)

async def main() -> None:
    dotenv.load_dotenv()

    client = await fishmael.Fishmael.from_env()

    @client.listen(fishmael.events.CommandInteractionEvent)
    async def foo(ev: fishmael.events.InteractionEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        print("omg???", ev.interaction_id)  # noqa: T201
        raise Exception

    @client.listen()
    async def bleh(ev: fishmael.events.ExceptionEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        raise ev.exception

    await client.start()


if __name__ == "__main__":
    asyncio.run(main())
