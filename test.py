import asyncio
import logging

import dotenv

import fishmael

logging.basicConfig(level=logging.INFO)

async def main() -> None:
    dotenv.load_dotenv()

    client = await fishmael.Fishmael.from_env()

    t = asyncio.create_task(
        client.event_manager.wait_for(
            fishmael.events.InteractionEvent,
            timeout=3,
            predicate=lambda ev: ev.interaction.user_id == 256133489454350345,
        ),
    )
    await asyncio.sleep(0)
    print(client.event_manager)

    client._closing_event.set()
    await client.start()

    try:
        print(await t)
    except:
        pass

    print(client.event_manager)


if __name__ == "__main__":
    asyncio.run(main())
