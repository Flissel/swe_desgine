"""Start dashboard server for verification."""
import asyncio
import sys
sys.path.insert(0, '.')
from requirements_engineer.dashboard.server import DashboardServer

async def main():
    server = DashboardServer(port=8801, open_browser=False)
    await server.start()
    print('SERVER READY on http://localhost:8766', flush=True)
    try:
        await asyncio.sleep(3600)
    except KeyboardInterrupt:
        await server.stop()

if __name__ == '__main__':
    asyncio.run(main())
