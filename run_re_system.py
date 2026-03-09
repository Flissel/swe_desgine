#!/usr/bin/env python
"""Wrapper — delegates to requirements_engineer.run_re_system"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from requirements_engineer.run_re_system import main, run_enterprise_mode, create_traceability_matrix, create_master_document, _validate_stage_output  # noqa: F401

if __name__ == "__main__":
    main()
