"""
Pipeline Manifest — Tracks inputs/outputs for each pipeline stage.

Produces `pipeline_manifest.json` in the output directory, auto-saved
after every stage so that progress is visible even mid-run.
"""

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StageRecord:
    """Record for a single pipeline stage."""
    step: int                       # 1-15 (or 8.5 for trace)
    name: str                       # "discovery", "user_stories", etc.
    description: str                # Human-readable description
    status: str = "pending"         # pending | running | completed | failed | skipped
    duration_ms: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    quality_gate: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # ── Convenience methods (usable inside `with manifest.stage(...)` block) ──

    def add_input(self, name: str, type: str = "data", *,
                  path: str = "", count: int = 0, description: str = ""):
        """Register an input consumed by this stage."""
        entry: Dict[str, Any] = {"name": name, "type": type}
        if path:
            entry["path"] = path
        if count:
            entry["count"] = count
        if description:
            entry["description"] = description
        self.inputs.append(entry)

    def add_output(self, name: str, type: str = "data", *,
                   path: str = "", count: int = 0, description: str = ""):
        """Register an output produced by this stage."""
        entry: Dict[str, Any] = {"name": name, "type": type}
        if path:
            entry["path"] = path
        if count:
            entry["count"] = count
        if description:
            entry["description"] = description
        self.outputs.append(entry)

    def set_quality_gate(self, status: str, **metrics):
        """Attach quality gate result to this stage."""
        self.quality_gate = {"status": status, **metrics}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Remove None quality_gate / error to keep JSON tidy
        if d["quality_gate"] is None:
            del d["quality_gate"]
        if d["error"] is None:
            del d["error"]
        return d


class PipelineManifest:
    """
    Tracks inputs/outputs for each pipeline stage.

    Usage::

        manifest = PipelineManifest(project_name, output_dir)

        with manifest.stage(3, "discovery", "Discovery Pass") as s:
            s.add_input("project_data", "data", description="...")
            # ... stage work ...
            s.add_output("requirements", "data", count=12)

        # After all stages:
        manifest.finalize()
    """

    def __init__(self, project_name: str, output_dir: Path):
        self.project_name = project_name
        self.output_dir = Path(output_dir)
        self.pipeline_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.started_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.stages: List[StageRecord] = []
        self._current_stage: Optional[StageRecord] = None
        self._start_time = time.time()

    # ── Context manager for a pipeline stage ──

    @contextmanager
    def stage(self, step, name: str, description: str):
        """Context manager wrapping a pipeline stage.

        Yields the `StageRecord` so callers can add_input / add_output.
        Automatically records duration and status.  If an exception occurs
        the stage is marked ``failed`` and the error stored.
        """
        record = StageRecord(step=step, name=name, description=description, status="running")
        self._current_stage = record
        start = time.time()
        try:
            yield record
            record.status = "completed"
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            raise
        finally:
            record.duration_ms = int((time.time() - start) * 1000)
            self.stages.append(record)
            self._current_stage = None
            self._save()

    def skip_stage(self, step, name: str, description: str, reason: str = ""):
        """Mark a stage as skipped (dry-run, disabled, etc.)."""
        record = StageRecord(step=step, name=name, description=description, status="skipped")
        if reason:
            record.error = reason
        self.stages.append(record)
        self._save()

    # ── Cost tracking helpers ──

    def update_stage_cost(self, cost_usd: float, llm_calls: int):
        """Update cost/calls on the most recently completed stage."""
        if self.stages:
            self.stages[-1].cost_usd = round(cost_usd, 6)
            self.stages[-1].llm_calls = llm_calls
            self._save()

    # ── Lifecycle ──

    def finalize(self):
        """Mark the manifest as complete and save."""
        self.completed_at = datetime.now().isoformat()
        self._save()

    # ── Validation ──

    def validate_prerequisites(self) -> List[Dict[str, Any]]:
        """Check completed stages for missing/empty required outputs.

        Returns list of warnings like::

            [{"stage": "discovery", "step": 3,
              "warning": "Output 'requirements' missing or count=0"}]
        """
        REQUIRED: Dict[str, List[str]] = {
            "discovery": ["requirements"],
            "user_stories": ["user_stories"],
            "test_cases": ["test_cases"],
            "ux_design": ["personas"],
            "ui_design": ["components"],
            "api_spec": ["api_endpoints"],
            "data_dictionary": ["entities"],
        }
        warnings: List[Dict[str, Any]] = []
        for stage in self.stages:
            if stage.status != "completed":
                continue
            for req_name in REQUIRED.get(stage.name, []):
                found = any(
                    req_name in out.get("name", "") and out.get("count", 1) > 0
                    for out in stage.outputs
                )
                if not found:
                    warnings.append({
                        "stage": stage.name,
                        "step": stage.step,
                        "warning": f"Output '{req_name}' missing or count=0",
                    })
        return warnings

    # ── Serialization ──

    def to_dict(self) -> Dict[str, Any]:
        total_cost = sum(s.cost_usd for s in self.stages)
        total_duration = int((time.time() - self._start_time) * 1000)
        return {
            "project_name": self.project_name,
            "pipeline_id": self.pipeline_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_ms": total_duration,
            "total_cost_usd": round(total_cost, 4),
            "total_stages": len(self.stages),
            "stages": [s.to_dict() for s in self.stages],
        }

    def _save(self):
        """Write pipeline_manifest.json to output_dir."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / "pipeline_manifest.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # Non-critical — don't break the pipeline
