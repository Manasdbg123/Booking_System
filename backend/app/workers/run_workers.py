import asyncio

from app.core.logging import configure_logging
from app.workers import expiry_worker, outbox_worker


async def main():
    configure_logging()
    await asyncio.gather(expiry_worker.run_forever(), outbox_worker.run_forever())


if __name__ == "__main__":
    asyncio.run(main())
