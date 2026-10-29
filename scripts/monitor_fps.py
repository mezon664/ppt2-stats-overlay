import asyncio
import json
import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        n = 0
        async for message in ws:
            state = json.loads(message)
            n += 1
            if n % 20 == 0:
                print(f"fps={state['recognition']['fps']} frames={state['recognition']['frame_count']} "
                      f"capture={state.get('capture')}")


asyncio.run(main())
