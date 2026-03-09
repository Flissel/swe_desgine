#!/usr/bin/env python
"""Auto-restart pipeline with checkpoint resume on crash."""
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

PROJECT = "re_ideas/services/whatsapp-messaging-service.json"
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds
ROOT = Path(__file__).parent
LOG = ROOT / "enterprise_output" / "pipeline_auto.log"


def find_resume_dir():
    """Find latest output dir with _checkpoints/ for this project."""
    enterprise = ROOT / "enterprise_output"
    candidates = sorted(
        enterprise.glob("whatsapp-messaging-service_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for d in candidates:
        if (d / "_checkpoints").exists() and any((d / "_checkpoints").glob("stage_*.json")):
            return str(d)
    return None


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_pipeline(resume_dir=None):
    cmd = [
        sys.executable, "-u", "run_re_system.py",
        "--project", PROJECT,
        "--mode", "enterprise",
    ]
    if resume_dir:
        cmd.extend(["--resume", resume_dir])
        log(f"RESUME from {Path(resume_dir).name}")
    else:
        log("FRESH start (no checkpoints found)")

    import os
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=False, timeout=7200, env=env)
    return proc.returncode


def main():
    LOG.parent.mkdir(exist_ok=True)
    log("=" * 60)
    log("Auto-restart pipeline with checkpoints")
    log("=" * 60)

    for attempt in range(1, MAX_RETRIES + 1):
        log(f"--- Attempt {attempt}/{MAX_RETRIES} ---")
        resume_dir = find_resume_dir()
        try:
            rc = run_pipeline(resume_dir)
        except subprocess.TimeoutExpired:
            log("TIMEOUT after 120 min")
            rc = -1
        except Exception as e:
            log(f"ERROR: {e}")
            rc = -1

        if rc == 0:
            log("SUCCESS - Pipeline completed!")
            return 0

        log(f"CRASH (exit code {rc}). Restarting in {RETRY_DELAY}s...")
        time.sleep(RETRY_DELAY)

    log(f"FAILED after {MAX_RETRIES} attempts")
    return 1


if __name__ == "__main__":
    sys.exit(main())
