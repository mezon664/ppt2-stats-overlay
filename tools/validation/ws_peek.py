import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8765") as ws:
        s = json.loads(await ws.recv())
        print("display:", s.get("display"), "waiting_start:", s.get("waiting_start"), "elapsed:", s.get("match_elapsed_s"))
asyncio.run(main())
