import asyncio, time, urllib.request, websockets

async def bench(n=1282):
    urllib.request.urlopen("http://localhost:8000/api/stream/restart", data=b"")
    t0 = time.perf_counter()
    async with websockets.connect("ws://localhost:8000/ws/stream") as ws:
        received = 0
        while received < n:
            await asyncio.wait_for(ws.recv(), timeout=180)
            received += 1
            if received % 200 == 0:
                el = time.perf_counter() - t0
                print(f"  {received}/{n}  {el:.2f}s  {received/el:.1f} tx/s")
        total = time.perf_counter() - t0
        print(f"")
        print(f"DONE: {n} tx in {total:.2f}s -> {n/total:.2f} tx/s effective")
        print(f"Expected minimum (no detection): {n/15:.1f}s")
        print(f"Detection overhead: {total - n/15:.2f}s")

asyncio.run(bench())
