#!/usr/bin/env python
"""
Start the RE Dashboard server standalone.

Usage:
  python start_dashboard.py                           # Dashboard only
  python start_dashboard.py --project re_ideas/services/whatsapp-messaging-service.json  # Auto-run pipeline
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env for API keys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed

from requirements_engineer.dashboard.server import DashboardServer


async def main():
    parser = argparse.ArgumentParser(description="RE Dashboard + Pipeline Runner")
    parser.add_argument(
        "--project", "-p",
        default=None,
        help="Path to project JSON — auto-starts pipeline after dashboard is up"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Dashboard port (default: 8080)"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to config YAML (default: auto-resolved to requirements_engineer/re_config.yaml)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open browser"
    )
    parser.add_argument(
        "--resume", "-r",
        default=None,
        help="Resume from existing output directory (e.g. enterprise_output/project_20260210_222409)"
    )
    args = parser.parse_args()

    # Check API key
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("[WARN] OPENROUTER_API_KEY not set. Pipeline execution will fail.")
        print("       Create a .env file with OPENROUTER_API_KEY=sk-or-...")
        if args.project:
            print("[ERROR] Cannot run pipeline without API key. Exiting.")
            sys.exit(1)

    # Start dashboard
    print("Starting RE Dashboard...")
    server = DashboardServer(port=args.port, open_browser=not args.no_browser)
    await server.start()
    print(f"Dashboard running at http://localhost:{args.port}")

    # Auto-run pipeline if --project given
    pipeline_task = None
    if args.project:
        project_path = str(Path(args.project).resolve())
        if not Path(project_path).exists():
            print(f"[ERROR] Project file not found: {project_path}")
            sys.exit(1)

        print(f"\n[AUTO] Starting pipeline for: {Path(project_path).name}")

        from requirements_engineer.run_re_system import run_enterprise_mode

        async def _run():
            try:
                output_dir = await run_enterprise_mode(
                    project_path=project_path,
                    config_path=args.config,
                    emitter=server.emitter,
                    resume_dir=args.resume,
                )
                print(f"\n[AUTO] Pipeline complete. Output: {output_dir}")
            except Exception as e:
                import traceback
                print(f"\n[AUTO] Pipeline error: {e}")
                traceback.print_exc()
                from requirements_engineer.dashboard.event_emitter import EventType
                await server.emitter.emit(EventType.PIPELINE_ERROR, {
                    "error": f"{type(e).__name__}: {e}"
                })

        pipeline_task = asyncio.create_task(_run())
        # Update server state so /api/pipeline/status works
        server._pipeline_task = pipeline_task
        server._pipeline_status["running"] = True
    else:
        print("Press Ctrl+C to stop")

    try:
        while True:
            await asyncio.sleep(1)
            # Exit after pipeline completes if auto-started
            if pipeline_task and pipeline_task.done():
                # Keep dashboard open for a bit so user can browse results
                print("\n[INFO] Pipeline done. Dashboard still running. Press Ctrl+C to stop.")
                pipeline_task = None  # Only print once
    except KeyboardInterrupt:
        print("\nStopping...")
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
