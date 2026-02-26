"""
Entry point for running the gRPC worker as a module.

Usage:
    python -m requirements_engineer.grpc_worker
    python -m requirements_engineer.grpc_worker --config /path/to/config.yaml
    python -m requirements_engineer.grpc_worker --generate-proto
"""

from requirements_engineer.grpc_worker.server import main

if __name__ == "__main__":
    main()
