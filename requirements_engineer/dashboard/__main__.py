"""
Entry point for running the dashboard server as a module.

Usage:
    python -m requirements_engineer.dashboard
    python -m requirements_engineer.dashboard --port 8085
    python -m requirements_engineer.dashboard --port 8085 --project re_ideas/services/whatsapp-messaging-service.json
"""

import asyncio
import argparse
import os
import sys

# Load .env file if present
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"[SERVER] Loaded .env from {env_path}")
except ImportError:
    pass

from .server import create_dashboard_server, HAS_AIOHTTP
from .event_emitter import EventType


async def main():
    parser = argparse.ArgumentParser(description='RE System Dashboard Server')
    parser.add_argument('--port', type=int, default=8085, help='Server port (default: 8085)')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser automatically')
    parser.add_argument('--project', '-p', default=None,
                        help='Path to project JSON — auto-starts pipeline')
    parser.add_argument('--config', '-c', default=None,
                        help='Path to config YAML (default: auto-resolved to requirements_engineer/re_config.yaml)')
    args = parser.parse_args()

    # Validate API key if --project given
    if args.project and not os.environ.get("OPENROUTER_API_KEY"):
        print("[ERROR] OPENROUTER_API_KEY not set. Cannot run pipeline.")
        sys.exit(1)

    server = create_dashboard_server(port=args.port, open_browser=not args.no_browser)

    if not HAS_AIOHTTP:
        print("[ERROR] aiohttp required for pipeline mode")
        sys.exit(1)

    print(f"\n[DASHBOARD] Starting aiohttp server on http://localhost:{args.port}")
    await server.start()

    # Auto-run pipeline if --project given
    pipeline_task = None
    if args.project:
        project_path = os.path.abspath(args.project)
        if not os.path.exists(project_path):
            print(f"[ERROR] Project file not found: {project_path}")
            sys.exit(1)

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        sys.path.insert(0, project_root)

        print(f"\n[AUTO] Starting pipeline for: {os.path.basename(project_path)}")

        from requirements_engineer.run_re_system import run_enterprise_mode

        async def _run():
            try:
                output_dir = await run_enterprise_mode(
                    project_path=project_path,
                    config_path=args.config,
                    emitter=server.emitter,
                )
                print(f"\n[AUTO] Pipeline complete. Output: {output_dir}")
            except Exception as e:
                import traceback
                print(f"\n[AUTO] Pipeline error: {e}")
                traceback.print_exc()
                await server.emitter.emit(EventType.PIPELINE_ERROR, {
                    "error": f"{type(e).__name__}: {e}"
                })

        pipeline_task = asyncio.create_task(_run())
        server._pipeline_task = pipeline_task
        server._pipeline_status["running"] = True

    # Keep running until Ctrl+C
    try:
        while True:
            await asyncio.sleep(1)
            if pipeline_task and pipeline_task.done():
                print("\n[INFO] Pipeline done. Dashboard still running. Press Ctrl+C to stop.")
                pipeline_task = None
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
