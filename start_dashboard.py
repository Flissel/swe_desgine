#!/usr/bin/env python
"""Wrapper — delegates to requirements_engineer.start_dashboard"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from requirements_engineer.start_dashboard import main  # noqa: F401

if __name__ == "__main__":
    asyncio.run(main())
