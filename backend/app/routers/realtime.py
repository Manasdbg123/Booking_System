import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis_client import get_redis

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/shows/{show_id}")
async def show_events(websocket: WebSocket, show_id: uuid.UUID):
    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = f"show:{show_id}:events"
    await pubsub.subscribe(channel)

    async def reader():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            # keep the connection alive; we don't expect client->server messages
            # besides periodic pings, but read anyway to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.close()
