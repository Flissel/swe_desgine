"""
Entry point for running the dashboard server as a module.

Usage:
    python -m requirements_engineer.dashboard
    python -m requirements_engineer.dashboard --port 8085
"""

import asyncio
import argparse
import os

# Load .env file if present
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"[SERVER] Loaded .env from {env_path}")

from .server import create_dashboard_server, HAS_AIOHTTP


async def main():
    parser = argparse.ArgumentParser(description='RE System Dashboard Server')
    parser.add_argument('--port', type=int, default=8085, help='Server port (default: 8085)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser automatically')
    args = parser.parse_args()

    server = create_dashboard_server(port=args.port, open_browser=not args.no_browser)

    if HAS_AIOHTTP:
        # aiohttp server runs async
        print(f"\n[DASHBOARD] Starting aiohttp server on http://localhost:{args.port}")
        await server.start()

        # Keep running until Ctrl+C
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")
            await server.stop()
    else:
        # Simple HTTP server
        print(f"\n[DASHBOARD] Starting simple HTTP server on http://localhost:{args.port}")
        server.start()

        # Keep running until Ctrl+C
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
