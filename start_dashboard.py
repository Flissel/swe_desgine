#!/usr/bin/env python
"""Start the RE Dashboard server standalone."""
import asyncio
import sys

# Add project to path
sys.path.insert(0, '.')

from requirements_engineer.dashboard.server import DashboardServer

async def main():
    print("Starting RE Dashboard...")
    server = DashboardServer(port=8080, open_browser=True)
    await server.start()
    print("Dashboard running at http://localhost:8080")
    print("Press Ctrl+C to stop")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        await server.stop()

if __name__ == "__main__":
    asyncio.run(main())
