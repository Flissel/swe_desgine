"""Test script to run the dashboard server."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '.')

# Load .env for API keys
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f'Loaded .env from {env_path}')
except ImportError:
    print('Warning: python-dotenv not installed, API keys must be set in environment')

async def test_server(port: int = 8085, project_dir: str = None, open_browser: bool = True):
    from requirements_engineer.dashboard.server import create_dashboard_server

    print('Creating dashboard server...')
    server = create_dashboard_server(port=port, open_browser=open_browser)

    # Set project directory if specified
    if project_dir:
        # Resolve glob patterns
        project_path = Path(project_dir)
        if '*' in project_dir:
            # Find matching directories
            base_dir = Path(project_dir.split('*')[0]).parent
            pattern = Path(project_dir).name
            matches = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                project_path = matches[0]
                print(f'Using project: {project_path.name}')

        if project_path.exists():
            server.project_dir = project_path
            print(f'Project directory: {project_path}')
        else:
            print(f'Warning: Project directory not found: {project_dir}')

    print('Starting server...')
    await server.start()
    print(f'Server started at http://localhost:{port}')
    print('Press Ctrl+C to stop')

    # Keep running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run the RE System Dashboard')
    parser.add_argument('--port', type=int, default=8085, help='Port to run on (default: 8085)')
    parser.add_argument('--project', type=str, help='Project directory to load')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser automatically')
    args = parser.parse_args()

    try:
        asyncio.run(test_server(
            port=args.port,
            project_dir=args.project,
            open_browser=not args.no_browser
        ))
    except KeyboardInterrupt:
        print("\nServer stopped.")
