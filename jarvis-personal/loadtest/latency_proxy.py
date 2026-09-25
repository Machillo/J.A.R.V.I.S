"""TCP proxy that adds a fixed delay per direction (models Render <-> Supabase network latency)."""
from __future__ import annotations

import asyncio
import os

DELAY = float(os.getenv("PROXY_DELAY_MS", "5")) / 1000
LISTEN = int(os.getenv("PROXY_LISTEN_PORT", "55432"))
TARGET_HOST = os.getenv("PROXY_TARGET_HOST", "127.0.0.1")
TARGET_PORT = int(os.getenv("PROXY_TARGET_PORT", "5432"))


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            await asyncio.sleep(DELAY)
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def handle(client_reader, client_writer):
    server_reader, server_writer = await asyncio.open_connection(TARGET_HOST, TARGET_PORT)
    await asyncio.gather(pipe(client_reader, server_writer), pipe(server_reader, client_writer))


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", LISTEN)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
