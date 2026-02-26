"""
gRPC Server for Change Propagation Worker

Starts the gRPC server and handles graceful shutdown.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from concurrent import futures
from typing import Optional

import grpc
from grpc import aio

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from requirements_engineer.grpc_worker.worker import PropagationWorker
from requirements_engineer.grpc_worker.config import load_config

# Import generated protobuf modules
try:
    from requirements_engineer.grpc_worker.proto import propagation_pb2_grpc
except ImportError:
    # Proto files not generated yet - will be generated on first run
    propagation_pb2_grpc = None

logger = logging.getLogger(__name__)


class GRPCServer:
    """gRPC Server wrapper with lifecycle management."""

    def __init__(self, config: dict):
        self.config = config
        self.server: Optional[aio.Server] = None
        self.worker: Optional[PropagationWorker] = None
        self._shutdown_event = asyncio.Event()

    async def start(self):
        """Start the gRPC server."""
        grpc_config = self.config.get("grpc", {})
        host = grpc_config.get("host", "localhost")
        port = grpc_config.get("port", 50051)
        max_workers = grpc_config.get("max_workers", 4)
        max_message_length = grpc_config.get("max_message_length", 100 * 1024 * 1024)

        # Create server with options
        options = [
            ("grpc.max_send_message_length", max_message_length),
            ("grpc.max_receive_message_length", max_message_length),
        ]

        self.server = aio.server(
            futures.ThreadPoolExecutor(max_workers=max_workers),
            options=options
        )

        # Initialize worker
        self.worker = PropagationWorker(self.config)
        await self.worker.initialize()

        # Register servicer
        if propagation_pb2_grpc:
            propagation_pb2_grpc.add_PropagationServiceServicer_to_server(
                self.worker, self.server
            )
        else:
            logger.warning("Proto modules not generated - server running in stub mode")

        # Bind to address
        address = f"{host}:{port}"
        self.server.add_insecure_port(address)

        # Start server
        await self.server.start()
        logger.info(f"gRPC Server started on {address}")

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        # Wait for shutdown
        await self._shutdown_event.wait()

    async def stop(self):
        """Stop the gRPC server gracefully."""
        if self.server:
            logger.info("Stopping gRPC server...")
            await self.server.stop(grace=5)
            logger.info("gRPC server stopped")

        if self.worker:
            await self.worker.cleanup()

    def _signal_handler(self):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()


async def serve(config_path: Optional[str] = None):
    """Main entry point for the gRPC server."""
    # Load configuration
    config = load_config(config_path)

    # Setup logging
    log_config = config.get("logging", {})
    logging.basicConfig(
        level=getattr(logging, log_config.get("level", "INFO")),
        format=log_config.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    # Create and start server
    server = GRPCServer(config)

    try:
        await server.start()
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await server.stop()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="gRPC Change Propagation Worker")
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to config file",
        default=None
    )
    parser.add_argument(
        "--generate-proto",
        action="store_true",
        help="Generate Python protobuf files and exit"
    )

    args = parser.parse_args()

    if args.generate_proto:
        generate_proto_files()
        return

    asyncio.run(serve(args.config))


def generate_proto_files():
    """Generate Python files from .proto definition."""
    import subprocess

    proto_dir = Path(__file__).parent / "proto"
    proto_file = proto_dir / "propagation.proto"

    if not proto_file.exists():
        print(f"Proto file not found: {proto_file}")
        return

    print(f"Generating Python files from {proto_file}...")

    try:
        subprocess.run([
            sys.executable, "-m", "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={proto_dir}",
            f"--grpc_python_out={proto_dir}",
            str(proto_file)
        ], check=True)
        print("Proto files generated successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Failed to generate proto files: {e}")
    except FileNotFoundError:
        print("grpc_tools not installed. Run: pip install grpcio-tools")


if __name__ == "__main__":
    main()
