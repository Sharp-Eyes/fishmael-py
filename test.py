import asyncio
import typing

import dotenv

import fishmael


async def main() -> None:
    dotenv.load_dotenv()

    client = await fishmael.Fishmael.from_env()

    @client.listen()
    async def foo(ev: fishmael.events.InteractionEvent) -> None:  # pyright: ignore[reportUnusedFunction]
        print("omg???", ev.interaction_id)  # noqa: T201

    await client.start()


if __name__ == "__main__":
    asyncio.run(main())
