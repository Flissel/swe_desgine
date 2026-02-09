"""
Configuration loader for gRPC Worker
"""

import os
from pathlib import Path
from typing import Optional

import yaml


def load_config(config_path: Optional[str] = None) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses default config.yaml

    Returns:
        Configuration dictionary
    """
    if config_path:
        path = Path(config_path)
    else:
        # Default: config.yaml in same directory
        path = Path(__file__).parent / "config.yaml"

    if not path.exists():
        return get_default_config()

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Merge with defaults
    defaults = get_default_config()
    return deep_merge(defaults, config)


def get_default_config() -> dict:
    """Return default configuration."""
    return {
        "grpc": {
            "host": os.getenv("GRPC_HOST", "localhost"),
            "port": int(os.getenv("GRPC_PORT", "50051")),
            "max_workers": 4,
            "max_message_length": 100 * 1024 * 1024,
        },
        "propagation": {
            "max_depth": 2,
            "min_confidence": 0.5,
            "auto_approve_threshold": 0.95,
            "batch_size": 5,
        },
        "kilo": {
            "enabled": True,
            "timeout_seconds": 60,
            "mode": "code",
            "yolo_mode": True,
            "max_retries": 2,
        },
        "llm": {
            "model": os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-20250514"),
            "temperature": 0.3,
            "max_tokens": 4000,
        },
        "connection_types": {
            "epic": ["user_story", "requirement"],
            "requirement": ["user_story", "diagram", "test"],
            "user_story": ["test", "task"],
        },
        "logging": {
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    }


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Dictionary to merge on top

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result
