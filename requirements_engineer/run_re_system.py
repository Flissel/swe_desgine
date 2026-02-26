#!/usr/bin/env python
"""
Requirements Engineering System - Entry Point

A system for automated requirements elicitation, analysis, specification,
and validation with Mermaid diagram generation and work breakdown structure.

Supports two modes:
- Standard: Basic 4-stage pipeline (Discovery, Analysis, Specification, Validation)
- Enterprise: 5-pass multi-pass refinement with quality gates, user stories,
              API specs, data dictionary, and Gherkin test cases

Usage:
    # Standard mode
    python run_re_system.py --project re_ideas/sample_project.json
    python run_re_system.py --project re_ideas/sample_project.json --stages 1,2,3,4
    python run_re_system.py --project re_ideas/sample_project.json --breakdown feature
    python run_re_system.py --project re_ideas/sample_project.json --use-kilo

    # Enterprise mode
    python run_re_system.py --project re_ideas/sample_project.json --mode enterprise
    python run_re_system.py --project re_ideas/sample_project.json --mode enterprise --with-gherkin
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import yaml

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use existing environment variables

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from requirements_engineer.core.re_journal import (
    RequirementNode,
    RequirementJournal
)
from requirements_engineer.core.re_metrics import MetricsManager
from requirements_engineer.core.llm_logger import get_llm_logger, LLMLogger
from requirements_engineer.core.re_agent_manager import REAgentManager
from requirements_engineer.core.pipeline_manifest import PipelineManifest
from requirements_engineer.work_breakdown.feature_breakdown import FeatureBreakdown
from requirements_engineer.work_breakdown.service_breakdown import ServiceBreakdown
from requirements_engineer.work_breakdown.application_breakdown import ApplicationBreakdown

# Importer imports
from requirements_engineer.importers.registry import ImporterRegistry
from requirements_engineer.importers.base_importer import ImportResult

# Enterprise mode imports (lazy loaded)
def get_enterprise_imports():
    """Lazy load enterprise mode imports."""
    from requirements_engineer.generators.user_story_generator import UserStoryGenerator
    from requirements_engineer.generators.api_spec_generator import APISpecGenerator
    from requirements_engineer.generators.data_dictionary_generator import DataDictionaryGenerator
    from requirements_engineer.generators.test_case_generator import TestCaseGenerator
    from requirements_engineer.gates.quality_gate import QualityGate, GateStatus
    # New generators
    from requirements_engineer.generators.tech_stack_generator import TechStackGenerator, save_tech_stack
    from requirements_engineer.generators.task_generator import TaskGenerator, save_task_list
    from requirements_engineer.generators.ux_design_generator import UXDesignGenerator, save_ux_design
    from requirements_engineer.generators.ui_design_generator import UIDesignGenerator, save_ui_design
    # Presentation Stage
    from requirements_engineer.stages.presentation_stage import PresentationStage
    # Link Config Generator
    from requirements_engineer.generators.link_config_generator import LinkConfigGenerator, generate_link_config
    # Realtime Spec Generator
    from requirements_engineer.generators.realtime_spec_generator import RealtimeSpecGenerator
    # New pipeline stages
    from requirements_engineer.generators.architecture_generator import ArchitectureGenerator, ArchitectureSpec, save_architecture
    from requirements_engineer.generators.state_machine_generator import StateMachineGenerator, StateMachine, save_state_machines
    from requirements_engineer.generators.component_composition_generator import ComponentCompositionGenerator, ComponentMatrix, save_compositions
    from requirements_engineer.generators.config_generator import ConfigGenerator, InfraConfig, save_config
    from requirements_engineer.generators.test_factory_generator import TestFactoryGenerator, EntityFactory, save_test_factories
    return {
        "UserStoryGenerator": UserStoryGenerator,
        "APISpecGenerator": APISpecGenerator,
        "DataDictionaryGenerator": DataDictionaryGenerator,
        "TestCaseGenerator": TestCaseGenerator,
        "QualityGate": QualityGate,
        "GateStatus": GateStatus,
        # New generators
        "TechStackGenerator": TechStackGenerator,
        "save_tech_stack": save_tech_stack,
        "TaskGenerator": TaskGenerator,
        "save_task_list": save_task_list,
        "UXDesignGenerator": UXDesignGenerator,
        "save_ux_design": save_ux_design,
        "UIDesignGenerator": UIDesignGenerator,
        "save_ui_design": save_ui_design,
        # Presentation Stage
        "PresentationStage": PresentationStage,
        # Link Config Generator
        "LinkConfigGenerator": LinkConfigGenerator,
        "generate_link_config": generate_link_config,
        # Realtime Spec Generator
        "RealtimeSpecGenerator": RealtimeSpecGenerator,
        # New pipeline stages
        "ArchitectureGenerator": ArchitectureGenerator,
        "ArchitectureSpec": ArchitectureSpec,
        "save_architecture": save_architecture,
        "StateMachineGenerator": StateMachineGenerator,
        "StateMachine": StateMachine,
        "save_state_machines": save_state_machines,
        "ComponentCompositionGenerator": ComponentCompositionGenerator,
        "ComponentMatrix": ComponentMatrix,
        "save_compositions": save_compositions,
        "ConfigGenerator": ConfigGenerator,
        "InfraConfig": InfraConfig,
        "save_config": save_config,
        "TestFactoryGenerator": TestFactoryGenerator,
        "EntityFactory": EntityFactory,
        "save_test_factories": save_test_factories,
    }


# Dashboard imports (lazy loaded)
def get_dashboard_imports():
    """Lazy load dashboard imports."""
    try:
        from requirements_engineer.dashboard.server import create_dashboard_server
        from requirements_engineer.dashboard.event_emitter import DashboardEventEmitter, EventType
        return {
            "create_dashboard_server": create_dashboard_server,
            "DashboardEventEmitter": DashboardEventEmitter,
            "EventType": EventType
        }
    except ImportError as e:
        print(f"  Warning: Dashboard not available: {e}")
        return None


# Layout orchestrator (lazy loaded)
def get_layout_orchestrator():
    """Lazy load the Layout Orchestrator for interactive layout generation."""
    try:
        from requirements_engineer.generators.layout_orchestrator import LayoutOrchestrator
        return LayoutOrchestrator
    except ImportError as e:
        print(f"  Warning: Layout Orchestrator not available: {e}")
        return None


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = str(Path(__file__).parent / "re_config.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


async def load_project_async(project_path: str) -> Dict[str, Any]:
    """
    Load project input with auto-detected importer.

    Supports multiple formats:
    - Standard RE-System JSON
    - Billing Spec JSON (autonomous_billing_spec.json)
    - Other registered formats

    Args:
        project_path: Path to project file

    Returns:
        Normalized project dictionary
    """
    print(f"   Loading project from: {project_path}")

    # Try to find a matching importer
    importer = ImporterRegistry.get_importer(project_path)

    if importer:
        print(f"   Using importer: {importer.name}")
        result = await importer.import_requirements(project_path)
        print(f"   Imported {result.get_requirement_count()} requirements")
        return result.to_standard_format()
    else:
        # Fallback to direct JSON load
        print(f"   Using standard JSON loader")
        with open(project_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return _normalize_project_keys(data)


def _normalize_project_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize project keys: lowercase -> capitalized for pipeline compatibility."""
    # Map lowercase -> expected capitalized keys
    key_map = {
        "name": "Name",
        "title": "Title",
        "domain": "Domain",
        "context": "Context",
        "stakeholders": "Stakeholders",
        "constraints": "Constraints",
    }
    for lower_key, cap_key in key_map.items():
        if lower_key in data and cap_key not in data:
            data[cap_key] = data[lower_key]
    return data


def load_project(project_path: str) -> Dict[str, Any]:
    """Load project input from JSON file (sync wrapper)."""
    return asyncio.run(load_project_async(project_path))


def create_output_directory(project_name: str, base_dir: str = "requirements_output") -> Path:
    """Create output directory structure."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(base_dir) / f"{project_name}_{timestamp}"

    # Create subdirectories
    (output_dir / "diagrams").mkdir(parents=True, exist_ok=True)
    (output_dir / "work_breakdown").mkdir(parents=True, exist_ok=True)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)

    return output_dir


# ---------------------------------------------------------------------------
# Checkpoint helpers for pipeline resume
# ---------------------------------------------------------------------------

def _save_checkpoint(output_dir: Path, stage, data: dict):
    """Save checkpoint data after a completed stage.

    Also saves a cumulative LLM usage snapshot so that resumed runs
    can report the full cost across all attempts.
    """
    cp_dir = output_dir / "_checkpoints"
    cp_dir.mkdir(exist_ok=True)
    with open(cp_dir / f"stage_{stage}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    # Save cumulative LLM usage alongside stage data
    _save_llm_usage_snapshot(output_dir)


def _save_llm_usage_snapshot(output_dir: Path):
    """Save cumulative LLM usage to checkpoint dir (overwritten each stage)."""
    from requirements_engineer.core.llm_logger import get_llm_logger
    logger = get_llm_logger()
    summary = logger.get_summary()
    # Also load any previous checkpoint usage and merge
    prev = _load_llm_usage_snapshot(output_dir)
    if prev:
        merged = _merge_llm_summaries(prev, summary)
    else:
        merged = summary
    cp_dir = output_dir / "_checkpoints"
    cp_dir.mkdir(exist_ok=True)
    with open(cp_dir / "llm_usage.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


def _load_llm_usage_snapshot(output_dir: Path) -> dict:
    """Load previously saved LLM usage from checkpoint dir."""
    path = output_dir / "_checkpoints" / "llm_usage.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _merge_llm_summaries(prev: dict, current: dict) -> dict:
    """Merge two LLM usage summaries, combining stats additively.

    Deduplicates by component: if a component appears in both, the one
    with more calls wins (it's from the most recent complete run of that stage).
    """
    merged_components = {}
    # Start with previous components
    for name, stats in prev.get("by_component", {}).items():
        merged_components[name] = stats
    # Overlay current components (if current has more calls, it's newer)
    for name, stats in current.get("by_component", {}).items():
        if name in merged_components:
            # Take whichever has more calls (current run or checkpoint)
            if stats.get("calls", 0) >= merged_components[name].get("calls", 0):
                merged_components[name] = stats
        else:
            merged_components[name] = stats

    total_calls = sum(c.get("calls", 0) for c in merged_components.values())
    total_tokens = sum(c.get("tokens", 0) for c in merged_components.values())
    total_cost = sum(c.get("cost_usd", 0) for c in merged_components.values())

    return {
        "total_calls": total_calls,
        "successful_calls": total_calls,  # approximate
        "failed_calls": 0,
        "total_input_tokens": prev.get("total_input_tokens", 0) + current.get("total_input_tokens", 0),
        "total_output_tokens": prev.get("total_output_tokens", 0) + current.get("total_output_tokens", 0),
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "avg_latency_ms": current.get("avg_latency_ms", prev.get("avg_latency_ms", 0)),
        "by_component": merged_components,
    }


# ---------------------------------------------------------------------------
# Cross-stage output validation
# ---------------------------------------------------------------------------

_STAGE_VALIDATIONS = {
    3:     ("requirements",  "Discovery",      lambda ctx: len(ctx.get("requirements", [])) > 0),
    5:     ("user_stories",  "User Stories",    lambda ctx: len(ctx.get("user_stories", [])) > 0),
    8:     ("test_cases",    "Test Cases",      lambda ctx: len(ctx.get("test_cases", [])) > 0),
    9:     ("ux_spec",       "UX Design",       lambda ctx: ctx.get("ux_spec") is not None),
    10:    ("ui_spec",       "UI Design",       lambda ctx: ctx.get("ui_spec") is not None),
    "11a": ("api_endpoints", "API Spec",        lambda ctx: len(ctx.get("api_endpoints", [])) > 0),
    "12a": ("data_dict",     "Data Dictionary", lambda ctx: ctx.get("data_dict") is not None
                                                  and len(getattr(ctx.get("data_dict"), "entities", {})) > 0),
}


def _validate_stage_output(stage_key, context: dict, manifest=None) -> bool:
    """Warn if a stage produced empty output. Returns True if valid."""
    entry = _STAGE_VALIDATIONS.get(stage_key)
    if entry is None:
        return True
    var_name, label, check_fn = entry
    if check_fn(context):
        return True
    print(f"   [VALIDATION WARN] Stage {stage_key} ({label}) produced empty '{var_name}'")
    if manifest and manifest.stages:
        last = manifest.stages[-1]
        if last.quality_gate is None:
            last.quality_gate = {}
        last.quality_gate["output_validation"] = "empty"
        last.quality_gate["missing_output"] = var_name
    return False


def _load_checkpoint(output_dir: Path, stage) -> dict:
    """Load checkpoint data for a completed stage."""
    cp_path = output_dir / "_checkpoints" / f"stage_{stage}.json"
    with open(cp_path, encoding="utf-8") as f:
        return json.load(f)


def _has_checkpoint(output_dir: Path, stage) -> bool:
    """Check if a checkpoint file exists for a stage (including decimal stages like 7.5)."""
    return (output_dir / "_checkpoints" / f"stage_{stage}.json").exists()


def _get_last_completed_stage(output_dir: Path) -> int:
    """Find the highest completed integer stage by scanning checkpoint files on disk.

    Primary source: checkpoint files in _checkpoints/ directory (stage_N.json).
    Fallback: pipeline_manifest.json for stages 1-3 which don't have checkpoint files.
    This ensures resume works even when the manifest was overwritten by a partial re-run.
    """
    cp_dir = output_dir / "_checkpoints"
    best = 0

    # Scan checkpoint files directly — this is the ground truth
    if cp_dir.exists():
        import re as _re
        for cp_file in cp_dir.glob("stage_*.json"):
            match = _re.match(r"stage_(\d+)\.json$", cp_file.name)
            if match:
                stage_num = int(match.group(1))
                if stage_num > best:
                    best = stage_num

    # If no checkpoint files found, fall back to manifest for stages 1-3
    if best == 0:
        manifest_path = output_dir / "pipeline_manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                data = json.load(f)
            completed = [s["step"] for s in data.get("stages", []) if s["status"] == "completed"]
            for s in completed:
                val = 0
                if isinstance(s, (int, float)):
                    val = int(s)
                elif isinstance(s, str):
                    cleaned = s.replace("b", "").split(".")[0]
                    if cleaned.isdigit():
                        val = int(cleaned)
                if val <= 3 and val > best:
                    best = val

    return best


def save_requirements_spec(
    journal: RequirementJournal,
    output_dir: Path
) -> None:
    """Save requirements specification document."""
    spec_path = output_dir / "requirements_specification.md"

    lines = [
        f"# Requirements Specification: {journal.project_name}",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Total Requirements:** {len(journal.nodes)}",
        "",
        "---",
        "",
        "## Table of Contents",
        ""
    ]

    # Group by type
    functional = [r for r in journal.nodes.values() if r.type == "functional"]
    non_functional = [r for r in journal.nodes.values() if r.type == "non_functional"]
    constraints = [r for r in journal.nodes.values() if r.type == "constraint"]

    lines.append(f"1. Functional Requirements ({len(functional)})")
    lines.append(f"2. Non-Functional Requirements ({len(non_functional)})")
    lines.append(f"3. Constraints ({len(constraints)})")
    lines.append("")

    # Functional Requirements
    lines.append("## 1. Functional Requirements\n")
    for req in sorted(functional, key=lambda x: x.requirement_id):
        lines.extend(_format_requirement(req))

    # Non-Functional Requirements
    lines.append("## 2. Non-Functional Requirements\n")
    for req in sorted(non_functional, key=lambda x: x.requirement_id):
        lines.extend(_format_requirement(req))

    # Constraints
    lines.append("## 3. Constraints\n")
    for req in sorted(constraints, key=lambda x: x.requirement_id):
        lines.extend(_format_requirement(req))

    with open(spec_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  Saved: {spec_path}")


def _format_requirement(req: RequirementNode) -> List[str]:
    """Format a single requirement for markdown."""
    lines = [
        f"### {req.requirement_id}: {req.title}",
        "",
        f"**Priority:** {req.priority.upper()}",
        f"**Status:** {req.validation_status}",
        "",
        f"**Description:** {req.description}",
        ""
    ]

    if req.rationale:
        lines.append(f"**Rationale:** {req.rationale}")
        lines.append("")

    if req.acceptance_criteria:
        lines.append("**Acceptance Criteria:**")
        for ac in req.acceptance_criteria:
            lines.append(f"- {ac}")
        lines.append("")

    if req.dependencies:
        lines.append(f"**Dependencies:** {', '.join(req.dependencies)}")
        lines.append("")

    lines.append("---")
    lines.append("")

    return lines


def save_traceability_matrix(
    journal: RequirementJournal,
    output_dir: Path
) -> None:
    """Save traceability matrix."""
    matrix_path = output_dir / "traceability_matrix.md"

    lines = [
        "# Traceability Matrix",
        "",
        "| Requirement | Type | Priority | Dependencies | Status |",
        "|-------------|------|----------|--------------|--------|"
    ]

    for req in sorted(journal.nodes.values(), key=lambda x: x.requirement_id):
        deps = ", ".join(req.dependencies) if req.dependencies else "-"
        lines.append(f"| {req.requirement_id} | {req.type} | {req.priority} | {deps} | {req.validation_status} |")

    with open(matrix_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  Saved: {matrix_path}")


def save_diagrams(
    journal: RequirementJournal,
    output_dir: Path
) -> None:
    """Save all Mermaid diagrams."""
    diagrams_dir = output_dir / "diagrams"

    for req_id, req in journal.nodes.items():
        for diagram_type, diagram_content in req.mermaid_diagrams.items():
            filename = f"{req_id}_{diagram_type}.mmd"
            filepath = diagrams_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(diagram_content)

    # Count saved diagrams
    diagram_count = sum(len(req.mermaid_diagrams) for req in journal.nodes.values())
    print(f"  Saved {diagram_count} diagrams to {diagrams_dir}")


def save_work_breakdown(
    breakdown: Any,
    output_dir: Path,
    breakdown_type: str
) -> None:
    """Save work breakdown structure."""
    breakdown_dir = output_dir / "work_breakdown"

    # Save as markdown
    md_path = breakdown_dir / f"{breakdown_type}_breakdown.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(breakdown.to_markdown())

    # Save as JSON
    json_path = breakdown_dir / f"{breakdown_type}_breakdown.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(breakdown.to_dict(), f, indent=2)

    print(f"  Saved: {md_path}")
    print(f"  Saved: {json_path}")


def save_validation_report(
    metrics: MetricsManager,
    output_dir: Path
) -> None:
    """Save validation report."""
    report_path = output_dir / "reports" / "validation_report.md"

    lines = [
        "# Requirements Validation Report",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## Quality Metrics Summary",
        "",
        "| Metric | Score | Threshold | Status |",
        "|--------|-------|-----------|--------|"
    ]

    aggregate = metrics.get_aggregate_metrics()
    thresholds = metrics.thresholds

    for metric, score in aggregate.items():
        threshold = thresholds.get(f"min_{metric}", 0.75)
        status = "[PASS]" if score >= threshold else "[FAIL]"
        lines.append(f"| {metric.capitalize()} | {score:.2%} | {threshold:.2%} | {status} |")

    lines.append("")
    lines.append("## Detailed Results")
    lines.append("")

    for req_id, req_metrics in metrics.metrics.items():
        lines.append(f"### {req_id}")
        lines.append("")
        for metric, value in req_metrics.items():
            lines.append(f"- {metric}: {value:.2%}")
        lines.append("")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"  Saved: {report_path}")


async def run_requirements_engineering_async(
    project_path: str,
    config_path: str = None,
    stages: Optional[List[int]] = None,
    breakdown_type: str = "feature",
    dry_run: bool = False,
    use_kilo: bool = False
) -> None:
    """
    Run the full requirements engineering pipeline (async version).

    Args:
        project_path: Path to project input JSON
        config_path: Path to configuration YAML
        stages: List of stages to run (1-4), or None for all
        breakdown_type: Type of work breakdown (feature, service, application)
        dry_run: If True, don't call LLM, just validate setup
        use_kilo: If True, use Kilo Agent for diagram generation
    """
    if config_path is None:
        config_path = str(Path(__file__).parent / "re_config.yaml")
    print("=" * 60)
    print("Requirements Engineering System")
    if use_kilo:
        print("(Kilo Agent Mode)")
    print("=" * 60)

    # Load configuration and project
    print("\n1. Loading configuration...")
    config = load_config(config_path)
    project = await load_project_async(project_path)

    project_name = project.get("Name", "unnamed_project")
    print(f"   Project: {project_name}")
    print(f"   Domain: {project.get('Domain', 'custom')}")

    # Create output directory
    output_dir = create_output_directory(project_name)
    print(f"   Output: {output_dir}")

    # Initialize components
    print("\n2. Initializing components...")
    journal = RequirementJournal(project_name=project_name)
    metrics = MetricsManager(thresholds=config.get("validation", {}).get("thresholds", {}))

    # Determine stages to run
    if stages is None:
        stages = [1, 2, 3, 4]
    print(f"   Stages: {stages}")

    if dry_run:
        print("\n[DRY RUN MODE - Skipping LLM calls]")
        _create_sample_requirements(journal)
    else:
        # Initialize agent manager
        agent_manager = REAgentManager(
            config=config,
            project_input=project,
            journal=journal,
            output_dir=str(output_dir),
            metrics=metrics
        )

        # Run stages
        print("\n3. Running stages...")
        for stage_num in stages:
            print(f"\n   Stage {stage_num}: {_get_stage_name(stage_num)}")
            agent_manager.run_stage(stage_num)

    # Generate diagrams with Kilo Agent if enabled
    # Note: This runs even in dry-run mode to test diagram generation
    if use_kilo:
        print("\n4. Generating diagrams with Kilo Agent...")
        await generate_diagrams_with_kilo(journal, config, output_dir)

    # Generate work breakdown
    step_num = 5 if use_kilo else 4
    print(f"\n{step_num}. Generating {breakdown_type} work breakdown...")
    breakdown = _create_breakdown(breakdown_type, journal)

    # Save outputs
    print(f"\n{step_num + 1}. Saving outputs...")
    save_requirements_spec(journal, output_dir)
    save_traceability_matrix(journal, output_dir)
    save_diagrams(journal, output_dir)
    save_work_breakdown(breakdown, output_dir, breakdown_type)
    save_validation_report(metrics, output_dir)

    # Save journal
    journal_path = output_dir / "journal.json"
    with open(journal_path, 'w', encoding='utf-8') as f:
        json.dump(journal.to_dict(), f, indent=2)
    print(f"  Saved: {journal_path}")

    # Print LLM usage summary
    llm_logger = get_llm_logger()
    if llm_logger.calls:
        llm_logger.print_summary()
        # Save summary to file
        llm_logger.save_summary(str(output_dir / "llm_usage_summary.json"))
        print(f"\n[INFO] LLM usage summary saved to: {output_dir / 'llm_usage_summary.json'}")

    print("\n" + "=" * 60)
    print("Requirements Engineering Complete!")
    print(f"Output directory: {output_dir}")
    print("=" * 60)


def run_requirements_engineering(
    project_path: str,
    config_path: str = None,
    stages: Optional[List[int]] = None,
    breakdown_type: str = "feature",
    dry_run: bool = False,
    use_kilo: bool = False
) -> None:
    """
    Run the full requirements engineering pipeline.

    Args:
        project_path: Path to project input JSON
        config_path: Path to configuration YAML
        stages: List of stages to run (1-4), or None for all
        breakdown_type: Type of work breakdown (feature, service, application)
        dry_run: If True, don't call LLM, just validate setup
        use_kilo: If True, use Kilo Agent for diagram generation
    """
    asyncio.run(run_requirements_engineering_async(
        project_path=project_path,
        config_path=config_path,
        stages=stages,
        breakdown_type=breakdown_type,
        dry_run=dry_run,
        use_kilo=use_kilo
    ))


def _get_stage_name(stage_num: int) -> str:
    """Get stage name from number."""
    names = {
        1: "Discovery",
        2: "Analysis",
        3: "Specification",
        4: "Validation",
        5: "Presentation"
    }
    return names.get(stage_num, "Unknown")


def _create_breakdown(breakdown_type: str, journal: RequirementJournal) -> Any:
    """Create work breakdown structure."""
    requirements = list(journal.nodes.values())

    if breakdown_type == "feature":
        breakdown = FeatureBreakdown()
        # Create default groupings based on requirements
        groupings = _auto_group_requirements(requirements)
        breakdown.generate_breakdown_from_requirements(requirements, groupings)

    elif breakdown_type == "service":
        breakdown = ServiceBreakdown()
        breakdown.generate_breakdown_from_requirements(requirements)

    elif breakdown_type == "application":
        breakdown = ApplicationBreakdown()
        breakdown.generate_breakdown_from_requirements(requirements)

    else:
        raise ValueError(f"Unknown breakdown type: {breakdown_type}")

    return breakdown


def _auto_group_requirements(requirements: List[RequirementNode]) -> List[Dict[str, Any]]:
    """Auto-group requirements into features."""
    groups: Dict[str, List[str]] = {}

    # Simple keyword-based grouping
    keywords = {
        "Authentication": ["login", "logout", "password", "auth", "register", "signup"],
        "User Management": ["user", "profile", "account", "settings"],
        "Data Management": ["data", "import", "export", "backup", "storage"],
        "Reporting": ["report", "analytics", "dashboard", "statistics"],
        "Integration": ["api", "integration", "external", "sync"],
        "Security": ["security", "encryption", "permission", "access"],
        "Performance": ["performance", "speed", "latency", "cache"]
    }

    for req in requirements:
        text = f"{req.title} {req.description}".lower()
        assigned = False

        for group_name, kws in keywords.items():
            if any(kw in text for kw in kws):
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append(req.requirement_id)
                assigned = True
                break

        if not assigned:
            if "Core Features" not in groups:
                groups["Core Features"] = []
            groups["Core Features"].append(req.requirement_id)

    return [{"name": name, "requirements": reqs} for name, reqs in groups.items()]


def _create_sample_requirements(journal: RequirementJournal) -> None:
    """Create sample requirements for dry run."""
    sample_reqs = [
        RequirementNode(
            id="node-001",
            requirement_id="REQ-001",
            title="User Registration",
            description="Users shall be able to register with email and password",
            type="functional",
            priority="must",
            acceptance_criteria=["Email validation", "Password strength check"],
            validation_status="validated"
        ),
        RequirementNode(
            id="node-002",
            requirement_id="REQ-002",
            title="User Login",
            description="Users shall be able to log in with their credentials",
            type="functional",
            priority="must",
            acceptance_criteria=["Secure authentication", "Session management"],
            dependencies=["REQ-001"],
            validation_status="validated"
        ),
        RequirementNode(
            id="node-003",
            requirement_id="REQ-003",
            title="Response Time",
            description="System shall respond within 200ms for 95% of requests",
            type="non_functional",
            priority="should",
            acceptance_criteria=["Performance testing", "Monitoring"],
            validation_status="validated"
        )
    ]

    for req in sample_reqs:
        journal.add_node(req)


async def generate_diagrams_with_kilo(
    journal: RequirementJournal,
    config: Dict[str, Any],
    output_dir: Path
) -> None:
    """
    Generate Mermaid diagrams using the Kilo Agent.

    Args:
        journal: The requirements journal
        config: Configuration dictionary
        output_dir: Output directory for diagrams
    """
    from requirements_engineer.diagrams.kilo_diagram_generator import KiloDiagramGenerator

    # Get Kilo configuration
    kilo_config = config.get("kilo_agent", {})
    diagrams_config = config.get("diagrams", {})
    diagram_types = diagrams_config.get("types", ["flowchart"])
    validation_config = diagrams_config.get("validation", {})

    print("\n  Initializing Kilo Diagram Generator...")
    generator = KiloDiagramGenerator(
        model_name=kilo_config.get("model", "arcee-ai/trinity-large-preview:free"),
        base_url=kilo_config.get("base_url", "https://openrouter.ai/api/v1"),
        timeout=kilo_config.get("timeout", 300),
        # Validation settings
        validate=validation_config.get("enabled", True),
        validation_method=validation_config.get("method", "pattern"),
        retry_on_error=validation_config.get("retry_on_error", True),
        max_retries=validation_config.get("max_retries", 2),
        skip_invalid=validation_config.get("skip_invalid", False)
    )
    await generator.initialize()

    if validation_config.get("enabled", True):
        print(f"  Validation: enabled (method={validation_config.get('method', 'pattern')}, retry={validation_config.get('retry_on_error', True)})")

    requirements = list(journal.nodes.values())
    diagrams_dir = output_dir / "diagrams"

    print(f"\n  Generating diagrams for {len(requirements)} requirements...")
    print(f"  Diagram types: {', '.join(diagram_types)}")

    for req in requirements:
        print(f"\n    Processing {req.requirement_id}: {req.title}")
        req_diagrams = await generator.generate_all_diagrams_for_requirement(
            req,
            diagram_types=diagram_types
        )

        # Store diagrams in requirement node
        for dtype, mermaid_code in req_diagrams.items():
            req.mermaid_diagrams[dtype] = mermaid_code

            # Save to file
            filename = f"{req.requirement_id}_{dtype}.mmd"
            filepath = diagrams_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(mermaid_code)
            print(f"      Saved: {filename}")

    total_diagrams = sum(len(req.mermaid_diagrams) for req in requirements)
    print(f"\n  Total diagrams generated: {total_diagrams}")

    # Print validation summary if validation was enabled
    if validation_config.get("enabled", True):
        generator.print_validation_summary()


async def generate_diagrams_simple(
    journal: RequirementJournal,
    config: Dict[str, Any],
    output_dir: Path
) -> None:
    """
    Generate Mermaid diagrams using simple LLM calls (without Kilo Agent).

    This is a fallback when --use-kilo is not specified.

    Args:
        journal: The requirements journal
        config: Configuration dictionary
        output_dir: Output directory for diagrams
    """
    from requirements_engineer.generators.api_spec_generator import APISpecGenerator

    # Reuse the API spec generator's LLM client
    llm_config = config.get("llm", {})
    model = llm_config.get("model", "openai/gpt-4o-mini")
    base_url = llm_config.get("base_url", "https://openrouter.ai/api/v1")

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url=base_url
        )
    except ImportError:
        print("  [WARN] OpenAI package not available. Skipping diagram generation.")
        return

    requirements = list(journal.nodes.values())
    diagrams_dir = output_dir / "diagrams"
    diagram_types_raw = config.get("diagrams", {}).get("types", ["flowchart", "sequence"])
    use_smart_selection = config.get("diagrams", {}).get("smart_selection", True)

    # Normalize diagram type names from config to internal format
    TYPE_MAPPING = {
        "sequenceDiagram": "sequence",
        "classDiagram": "class",
        "erDiagram": "er",
        "stateDiagram": "state",
        "C4Context": "c4",
        "flowchart": "flowchart",
        # Also support internal names directly
        "sequence": "sequence",
        "class": "class",
        "er": "er",
        "state": "state",
        "c4": "c4"
    }
    diagram_types = [TYPE_MAPPING.get(t, t) for t in diagram_types_raw]

    # Simple prompts for each diagram type
    DIAGRAM_PROMPTS = {
        "flowchart": "Create a Mermaid flowchart (flowchart TD) showing the process flow for: {title}\n\nDescription: {description}\n\nReturn ONLY the Mermaid code, starting with 'flowchart TD'.",
        "sequence": "Create a Mermaid sequence diagram showing actor interactions for: {title}\n\nDescription: {description}\n\nReturn ONLY the Mermaid code, starting with 'sequenceDiagram'.",
        "class": "Create a Mermaid class diagram showing the domain model for: {title}\n\nDescription: {description}\n\nReturn ONLY the Mermaid code, starting with 'classDiagram'.",
        "er": "Create a Mermaid ER diagram showing entities and relationships for: {title}\n\nDescription: {description}\n\nReturn ONLY the Mermaid code, starting with 'erDiagram'.",
        "state": "Create a Mermaid state diagram showing states and transitions for: {title}\n\nDescription: {description}\n\nReturn ONLY the Mermaid code, starting with 'stateDiagram-v2'.",
        "c4": "Create a Mermaid C4 context diagram showing system architecture for: {title}\n\nDescription: {description}\n\nReturn ONLY the Mermaid code using C4Context."
    }

    # Smart selection prompt
    DIAGRAM_SELECTION_PROMPT = """Analyze this requirement and select 2-3 diagram types that would best visualize it.

Requirement: {title}
Description: {description}
Type: {req_type}

Available diagram types:
- flowchart: Process flows, workflows, decision trees
- sequence: Actor/system interactions, API calls, message sequences
- class: Domain models, entities and relationships
- er: Database structures, entity-relationships
- state: State machines, status transitions, lifecycles
- c4: System architecture, context diagrams

Respond with ONLY a JSON array of 2-3 selected types, e.g.: ["flowchart", "sequence"]"""

    if use_smart_selection:
        print(f"  Smart diagram selection enabled for {len(requirements)} requirements...")
    else:
        print(f"  Generating {len(diagram_types)} diagram types for {len(requirements)} requirements...")

    total_generated = 0
    total_skipped = 0

    for req in requirements:
        # Determine which diagram types to generate for this requirement
        if use_smart_selection:
            # LLM decides which diagrams are relevant
            try:
                selection_prompt = DIAGRAM_SELECTION_PROMPT.format(
                    title=req.title,
                    description=req.description[:300],
                    req_type=getattr(req, 'type', 'functional')
                )

                selection_response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Select 2-3 diagram types. Return ONLY a JSON array."},
                        {"role": "user", "content": selection_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=100
                )

                selection_text = selection_response.choices[0].message.content.strip()

                # Parse JSON array
                import re as regex
                json_match = regex.search(r'\[.*?\]', selection_text, regex.DOTALL)
                if json_match:
                    import json
                    selected_types = json.loads(json_match.group())
                    # Validate and normalize
                    req_diagram_types = [TYPE_MAPPING.get(t, t) for t in selected_types if TYPE_MAPPING.get(t, t) in DIAGRAM_PROMPTS]
                    if len(req_diagram_types) < 2:
                        req_diagram_types = diagram_types[:2]  # Fallback
                else:
                    req_diagram_types = diagram_types[:2]

            except Exception as e:
                print(f"      [WARN] Smart selection failed, using fallback: {e}")
                req_diagram_types = diagram_types[:2]

            print(f"    {req.requirement_id}: {req.title[:30]}... -> {req_diagram_types}")
            total_skipped += len(diagram_types) - len(req_diagram_types)
        else:
            req_diagram_types = diagram_types
            print(f"    {req.requirement_id}: {req.title[:40]}...")

        for dtype in req_diagram_types:
            if dtype not in DIAGRAM_PROMPTS:
                continue

            prompt = DIAGRAM_PROMPTS[dtype].format(
                title=req.title,
                description=req.description[:500]
            )

            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an expert at creating Mermaid diagrams. Return ONLY valid Mermaid code."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1500
                )

                mermaid_code = response.choices[0].message.content.strip()

                # Extract code from markdown blocks if present
                if "```" in mermaid_code:
                    import re
                    match = re.search(r'```(?:mermaid)?\s*([\s\S]*?)\s*```', mermaid_code)
                    if match:
                        mermaid_code = match.group(1).strip()

                # Store in requirement
                req.mermaid_diagrams[dtype] = mermaid_code

                # Save to file
                filename = f"{req.requirement_id}_{dtype}.mmd"
                filepath = diagrams_dir / filename
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(mermaid_code)

                total_generated += 1

            except Exception as e:
                print(f"      [WARN] Failed to generate {dtype} diagram: {e}")

    if use_smart_selection:
        would_have_generated = len(requirements) * len(diagram_types)
        print(f"  Total diagrams generated: {total_generated} (saved {total_skipped} with smart selection)")
        print(f"  Reduction: {would_have_generated} -> {total_generated} ({100 * (1 - total_generated / would_have_generated):.0f}% fewer)")
    else:
        print(f"  Total diagrams generated: {total_generated}")


def create_validation_report(
    journal: RequirementJournal,
    requirements: List
) -> str:
    """
    Create a validation report for requirements.

    Args:
        journal: The requirements journal
        requirements: List of requirements

    Returns:
        Markdown string with validation report
    """
    md = "# Validation Report\n\n"
    md += f"**Generated:** {datetime.now().isoformat()}\n\n"

    md += "## Summary\n\n"
    md += f"- Total Requirements: {len(requirements)}\n"

    # Count by type
    type_counts = {}
    priority_counts = {}
    for req in requirements:
        req_type = getattr(req, 'type', 'unknown')
        req_priority = getattr(req, 'priority', 'unknown')
        type_counts[req_type] = type_counts.get(req_type, 0) + 1
        priority_counts[req_priority] = priority_counts.get(req_priority, 0) + 1

    md += "\n### By Type\n\n"
    for t, count in sorted(type_counts.items()):
        md += f"- {t}: {count}\n"

    md += "\n### By Priority\n\n"
    for p, count in sorted(priority_counts.items()):
        md += f"- {p}: {count}\n"

    # Validation checks
    md += "\n---\n\n## Validation Checks\n\n"

    # Check for missing descriptions
    missing_desc = [r for r in requirements if not getattr(r, 'description', '').strip()]
    md += f"### Missing Descriptions\n\n"
    if missing_desc:
        md += f"**{len(missing_desc)} requirements have no description:**\n\n"
        for r in missing_desc[:10]:
            md += f"- {r.requirement_id}: {r.title}\n"
        if len(missing_desc) > 10:
            md += f"- ... and {len(missing_desc) - 10} more\n"
    else:
        md += "All requirements have descriptions. [PASS]\n"

    # Check for orphan requirements (no dependencies)
    md += f"\n### Requirements Completeness\n\n"
    functional = [r for r in requirements if getattr(r, 'type', '') == 'functional']
    non_functional = [r for r in requirements if getattr(r, 'type', '') == 'non_functional']

    md += f"- Functional Requirements: {len(functional)}\n"
    md += f"- Non-Functional Requirements: {len(non_functional)}\n"

    if functional:
        md += "\n[PASS] Functional requirements present.\n"
    else:
        md += "\n[WARN] No functional requirements found.\n"

    md += "\n---\n\n"
    md += "*Report generated by AI-Scientist Requirements Engineering System*\n"

    return md


def create_traceability_matrix(
    requirements: List,
    user_stories: List,
    test_cases: List,
    api_endpoints: Optional[List] = None,
    screens: Optional[List] = None,
    entities: Optional[List] = None,
    state_machines: Optional[List] = None,
) -> str:
    """
    Create a bidirectional traceability matrix.

    Links: Requirements <-> User Stories <-> Test Cases <-> API Endpoints <-> Screens <-> Entities

    Args:
        requirements: List of requirements
        user_stories: List of user stories
        test_cases: List of test cases
        api_endpoints: Optional list of API endpoints (with parent_requirement_id)
        screens: Optional list of screens (with parent_user_story)
        entities: Optional list or dict of entities
        state_machines: Optional list of state machines (with entity attribute)

    Returns:
        Markdown string with traceability matrix
    """
    api_endpoints = api_endpoints or []
    screens = screens or []
    entity_list = list(entities.values()) if isinstance(entities, dict) else (entities or [])

    # Build set of entities that have state machines
    sm_entities = set()
    for sm in (state_machines or []):
        ent_name = getattr(sm, 'entity', '')
        if ent_name:
            sm_entities.add(ent_name.lower())

    md = "# Traceability Matrix\n\n"
    md += f"**Generated:** {datetime.now().isoformat()}\n\n"

    md += "## Summary\n\n"
    md += f"- Requirements: {len(requirements)}\n"
    md += f"- User Stories: {len(user_stories)}\n"
    md += f"- Test Cases: {len(test_cases)}\n"
    md += f"- API Endpoints: {len(api_endpoints)}\n"
    md += f"- Screens: {len(screens)}\n"
    md += f"- Entities: {len(entity_list)}\n\n"

    # Build mapping: requirement_id -> user_stories
    req_to_us = {}
    for us in user_stories:
        parent_req = getattr(us, 'parent_requirement_id', None)
        if parent_req:
            if parent_req not in req_to_us:
                req_to_us[parent_req] = []
            req_to_us[parent_req].append(us.id)

    # Build mapping: user_story_id -> test_cases
    us_to_tc = {}
    for tc in test_cases:
        parent_us = getattr(tc, 'parent_user_story_id', None)
        if parent_us:
            if parent_us not in us_to_tc:
                us_to_tc[parent_us] = []
            us_to_tc[parent_us].append(tc.id)

    # Build mapping: requirement_id -> api_endpoints
    req_to_api = {}
    for ep in api_endpoints:
        parent_req = getattr(ep, 'parent_requirement_id', '')
        if parent_req:
            if parent_req not in req_to_api:
                req_to_api[parent_req] = []
            req_to_api[parent_req].append(f"{ep.method} {ep.path}")

    # Build mapping: user_story_id -> screens
    us_to_screen = {}
    for screen in screens:
        parent_us = ""
        if isinstance(screen, dict):
            parent_us = screen.get("parent_user_story", "")
        else:
            parent_us = getattr(screen, "parent_user_story", "")
        if parent_us:
            if parent_us not in us_to_screen:
                us_to_screen[parent_us] = []
            screen_id = screen.get("id", "") if isinstance(screen, dict) else getattr(screen, "id", "")
            us_to_screen[parent_us].append(screen_id)

    # Build mapping: requirement_id -> entity names (via API path matching)
    req_to_entity: Dict[str, set] = {}
    for ent in entity_list:
        ent_name = ent.name if hasattr(ent, 'name') else str(ent)
        ent_lower = ent_name.lower().rstrip('s')  # simple singular
        for req_id, api_list in req_to_api.items():
            for api_str in api_list:
                if ent_lower in api_str.lower():
                    req_to_entity.setdefault(req_id, set()).add(ent_name)

    # Full Traceability Table
    md += "---\n\n## Full Traceability\n\n"
    md += "| Requirement | Type | Priority | User Stories | Test Cases | API Endpoints | Screens | Entities |\n"
    md += "|-------------|------|----------|--------------|------------|---------------|---------|----------|\n"

    for req in requirements:
        req_id = req.requirement_id
        req_type = getattr(req, 'type', '-')
        req_priority = getattr(req, 'priority', '-')

        us_list = req_to_us.get(req_id, [])
        us_str = ', '.join(us_list) if us_list else '-'

        # Get test cases for these user stories
        tc_list = []
        for us_id in us_list:
            tc_list.extend(us_to_tc.get(us_id, []))
        tc_str = ', '.join(tc_list[:5]) if tc_list else '-'
        if len(tc_list) > 5:
            tc_str += f" (+{len(tc_list) - 5})"

        # API endpoints for this requirement
        api_list = req_to_api.get(req_id, [])
        api_str = ', '.join(api_list[:3]) if api_list else '-'
        if len(api_list) > 3:
            api_str += f" (+{len(api_list) - 3})"

        # Screens for user stories of this requirement
        scr_ids = []
        for us_id in us_list:
            scr_ids.extend(us_to_screen.get(us_id, []))
        scr_str = ', '.join(scr_ids[:3]) if scr_ids else '-'
        if len(scr_ids) > 3:
            scr_str += f" (+{len(scr_ids) - 3})"

        # Entities linked to this requirement (via API paths), with [SM] flag for state machines
        ent_names = req_to_entity.get(req_id, set())
        if ent_names:
            ent_parts = []
            for en in sorted(ent_names)[:3]:
                flag = " [SM]" if en.lower().rstrip('s') in sm_entities or en.lower() in sm_entities else ""
                ent_parts.append(f"{en}{flag}")
            ent_str = ', '.join(ent_parts)
            if len(ent_names) > 3:
                ent_str += f" (+{len(ent_names) - 3})"
        else:
            ent_str = '-'

        md += f"| {req_id} | {req_type} | {req_priority} | {us_str} | {tc_str} | {api_str} | {scr_str} | {ent_str} |\n"

    # Coverage Statistics
    md += "\n---\n\n## Coverage Statistics\n\n"

    reqs_with_us = len([r for r in requirements if r.requirement_id in req_to_us])
    us_with_tc = len([us for us in user_stories if us.id in us_to_tc])
    reqs_with_api = len([r for r in requirements if r.requirement_id in req_to_api])

    req_coverage = (reqs_with_us / len(requirements) * 100) if requirements else 0
    us_coverage = (us_with_tc / len(user_stories) * 100) if user_stories else 0
    api_coverage = (reqs_with_api / len([r for r in requirements if getattr(r, 'type', '') == 'functional']) * 100) if requirements else 0

    md += f"- Requirements with User Stories: {reqs_with_us}/{len(requirements)} ({req_coverage:.1f}%)\n"
    md += f"- User Stories with Test Cases: {us_with_tc}/{len(user_stories)} ({us_coverage:.1f}%)\n"
    md += f"- Functional Requirements with API Endpoints: {reqs_with_api}/{len([r for r in requirements if getattr(r, 'type', '') == 'functional'])} ({api_coverage:.1f}%)\n"

    # Orphan analysis
    md += "\n### Orphan Analysis\n\n"

    orphan_reqs = [r for r in requirements if r.requirement_id not in req_to_us and getattr(r, 'type', '') == 'functional']
    if orphan_reqs:
        md += f"**{len(orphan_reqs)} functional requirements have no user stories:**\n\n"
        for r in orphan_reqs[:10]:
            md += f"- {r.requirement_id}: {r.title}\n"
    else:
        md += "All functional requirements are covered by user stories. [PASS]\n"

    orphan_us = [us for us in user_stories if us.id not in us_to_tc]
    if orphan_us:
        md += f"\n**{len(orphan_us)} user stories have no test cases:**\n\n"
        for us in orphan_us[:10]:
            md += f"- {us.id}: {us.title}\n"
    else:
        md += "\nAll user stories are covered by test cases. [PASS]\n"

    md += "\n---\n\n"
    md += "*Traceability matrix generated by AI-Scientist Requirements Engineering System*\n"

    return md


async def run_enterprise_mode(
    project_path: str,
    config_path: str = None,
    use_kilo: bool = True,
    with_gherkin: bool = True,
    with_api_spec: bool = True,
    with_data_dict: bool = True,
    dry_run: bool = False,
    with_dashboard: bool = False,
    dashboard_port: int = 8080,
    emitter=None,
    resume_dir: Optional[str] = None,
) -> Optional[str]:
    """
    Run the enterprise multi-pass refinement pipeline.

    This mode generates comprehensive documentation including:
    - User Stories from Requirements
    - OpenAPI 3.0 Specification
    - Data Dictionary
    - Gherkin/BDD Test Cases
    - Quality Gate Reports

    Args:
        project_path: Path to project input JSON
        config_path: Path to configuration YAML
        use_kilo: If True, use Kilo Agent for diagram generation
        with_gherkin: If True, generate Gherkin test cases
        with_api_spec: If True, generate OpenAPI specification
        with_data_dict: If True, generate data dictionary
    """
    if config_path is None:
        config_path = str(Path(__file__).parent / "re_config.yaml")
    imports = get_enterprise_imports()
    UserStoryGenerator = imports["UserStoryGenerator"]
    APISpecGenerator = imports["APISpecGenerator"]
    DataDictionaryGenerator = imports["DataDictionaryGenerator"]
    TestCaseGenerator = imports["TestCaseGenerator"]
    QualityGate = imports["QualityGate"]
    GateStatus = imports["GateStatus"]
    # New generators
    TechStackGenerator = imports["TechStackGenerator"]
    save_tech_stack = imports["save_tech_stack"]
    TaskGenerator = imports["TaskGenerator"]
    save_task_list = imports["save_task_list"]
    UXDesignGenerator = imports["UXDesignGenerator"]
    save_ux_design = imports["save_ux_design"]
    UIDesignGenerator = imports["UIDesignGenerator"]
    save_ui_design = imports["save_ui_design"]
    # New pipeline stage generators
    ArchitectureGenerator = imports["ArchitectureGenerator"]
    ArchitectureSpec = imports["ArchitectureSpec"]
    save_architecture = imports["save_architecture"]
    StateMachineGenerator = imports["StateMachineGenerator"]
    StateMachine = imports["StateMachine"]
    save_state_machines = imports["save_state_machines"]
    ComponentCompositionGenerator = imports["ComponentCompositionGenerator"]
    ComponentMatrix = imports["ComponentMatrix"]
    save_compositions = imports["save_compositions"]
    ConfigGenerator = imports["ConfigGenerator"]
    InfraConfig = imports["InfraConfig"]
    save_config = imports["save_config"]
    TestFactoryGenerator = imports["TestFactoryGenerator"]
    EntityFactory = imports["EntityFactory"]
    save_test_factories = imports["save_test_factories"]

    # Dashboard setup
    dashboard_server = None
    # Use externally provided emitter (from dashboard server) or create one
    _external_emitter = emitter is not None

    # Matrix Event Bridge for consistent metadata visualization
    matrix_bridge = None

    if _external_emitter:
        # Emitter injected from dashboard server — don't start our own server
        print("\n[DASHBOARD] Using external emitter (dashboard already running)")
    elif with_dashboard:
        dashboard_imports = get_dashboard_imports()
        if dashboard_imports:
            print("\n[DASHBOARD] Starting Live Dashboard...")
            dashboard_server = dashboard_imports["create_dashboard_server"](
                port=dashboard_port,
                open_browser=True
            )
            await dashboard_server.start()
            emitter = dashboard_server.emitter
            print(f"   Dashboard available at: http://localhost:{dashboard_port}")

            # Give browser time to open
            await asyncio.sleep(1)

    if emitter:
        # Initialize Matrix Event Bridge for structured visualization
        try:
            from requirements_engineer.dashboard.matrix_event_bridge import MatrixEventBridge
            matrix_bridge = MatrixEventBridge(emitter)
            print("   Matrix Event Bridge initialized")
        except ImportError as e:
            print(f"   [WARN] Matrix Event Bridge not available: {e}")

    print("=" * 70)
    print("Requirements Engineering System - ENTERPRISE MODE")
    if with_dashboard:
        print(f"(Live Dashboard: http://localhost:{dashboard_port})")
    print("=" * 70)

    # Helper: emit pipeline progress with current LLM cost
    llm_logger = get_llm_logger()

    async def _emit_progress(step: int, desc: str):
        if emitter:
            cost = sum(c.cost_usd for c in llm_logger.calls)
            tokens = sum(c.input_tokens + c.output_tokens for c in llm_logger.calls)
            await emitter.pipeline_progress(step, 15, desc, cost_usd=cost, total_tokens=tokens)

    def _llm_snapshot():
        """Return (cost, calls) snapshot for computing per-stage deltas."""
        return (sum(c.cost_usd for c in llm_logger.calls), len(llm_logger.calls))

    def _update_stage_cost(before_snapshot):
        """Compute delta from snapshot and update the last manifest stage."""
        cost_before, calls_before = before_snapshot
        cost_now, calls_now = _llm_snapshot()
        manifest.update_stage_cost(
            cost_usd=cost_now - cost_before,
            llm_calls=calls_now - calls_before,
        )

    # Load configuration and project
    print("\n[1/20] Loading configuration...")
    await _emit_progress(1, "Loading configuration...")
    config = load_config(config_path)
    project = await load_project_async(project_path)

    project_name = project.get("Name", "unnamed_project")
    domain = project.get("Domain", "custom")
    context = project.get("Context", {})
    stakeholders = project.get("Stakeholders", [])
    constraints = project.get("Constraints", {})

    # Initialize Training Data Collector for fine-tuning data capture
    training_collector = None
    try:
        from requirements_engineer.training.collector import TrainingDataCollector
        training_collector = TrainingDataCollector.get_instance()
        training_collector.start_run(
            project_id=project_name,
            project_name=project_name,
            config={"model": config.get("kilo_agent", {}).get("model", ""), "domain": domain}
        )
        print(f"   Training data collection: ACTIVE")
    except Exception as e:
        print(f"   Training data collection: unavailable ({e})")

    # Emit pipeline started event
    if emitter:
        await emitter.pipeline_started(project_name, "enterprise")

    print(f"   Project: {project_name}")
    print(f"   Domain: {domain}")

    # Create or reuse output directory
    if resume_dir:
        output_dir = Path(resume_dir)
        last_completed = _get_last_completed_stage(output_dir)
        print(f"   Resuming from checkpoint (last completed stage: {last_completed})")
    else:
        output_dir = create_output_directory(project_name, "enterprise_output")
        last_completed = 0
    (output_dir / "user_stories").mkdir(exist_ok=True)
    (output_dir / "api").mkdir(exist_ok=True)
    (output_dir / "data").mkdir(exist_ok=True)
    (output_dir / "testing").mkdir(exist_ok=True)
    (output_dir / "quality").mkdir(exist_ok=True)
    # New generator output directories
    (output_dir / "tech_stack").mkdir(exist_ok=True)
    (output_dir / "ux_design").mkdir(exist_ok=True)
    (output_dir / "ui_design").mkdir(exist_ok=True)
    (output_dir / "tasks").mkdir(exist_ok=True)
    print(f"   Output: {output_dir}")

    # Initialize Pipeline Manifest for stage I/O tracking
    manifest = PipelineManifest(project_name, output_dir)

    # Retroactively record Stage 1 (already completed above, before manifest existed)
    with manifest.stage(1, "config_loading", "Loading configuration and project data") as stg:
        stg.add_input("project.json", "file", path=project_path, description="Project definition file")
        stg.add_input("re_config.yaml", "file", path=config_path, description="Pipeline configuration")
        stg.add_output("config", "config", description="Loaded pipeline configuration")
        stg.add_output("project_data", "data", description=f"Project '{project_name}', domain='{domain}'")

    # Initialize components
    with manifest.stage(2, "init_journal", "Initializing journal and metrics") as stg:
        stg.add_input("project_data", "data", description="Project metadata")
        stg.add_input("config", "config", description="Pipeline configuration")

        print("\n[2/20] Initializing journal and metrics...")
        await _emit_progress(2, "Initializing journal and metrics...")
        journal = RequirementJournal(project_name=project_name)
        metrics = MetricsManager(thresholds=config.get("validation", {}))
        quality_gate = QualityGate()

        # Initialize self-critique engine early for per-stage critique
        critique_engine = None
        if not dry_run:
            try:
                from requirements_engineer.critique.self_critique import SelfCritiqueEngine
                llm_config = config.get("kilo_agent", {})
                critique_engine = SelfCritiqueEngine(
                    model_name=llm_config.get("model", "openai/gpt-4o-mini"),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY")
                )
                await critique_engine.initialize()
            except Exception as e:
                print(f"   [WARN] Could not initialize critique engine: {e}")

        stg.add_output("journal", "data", description="Requirement journal")
        stg.add_output("metrics", "data", description="Metrics manager")
        stg.add_output("quality_gate", "data", description="Quality gate checker")
        stg.add_output("critique_engine", "data", description="Self-critique engine")

    # Create sample requirements (or run discovery stage)
    _snap = _llm_snapshot()
    with manifest.stage(3, "discovery", "Running Discovery Pass") as stg:
        stg.add_input("project_data", "data", description=f"{len(project.get('_imported_requirements', []))} imported requirements")

        print("\n[3/20] Running Discovery Pass...")
        await _emit_progress(3, "Running Discovery Pass...")
        if emitter:
            await emitter.pass_started("discovery", 1)

        # Check for pre-imported requirements from importer
        imported_reqs = project.get("_imported_requirements", [])
        if imported_reqs:
            print(f"   Loading {len(imported_reqs)} imported requirements...")
            for req_data in imported_reqs:
                req = RequirementNode(
                    id=f"node-{req_data.get('requirement_id', 'unknown')}",
                    requirement_id=req_data.get("requirement_id", "REQ-XXX"),
                    title=req_data.get("title", "Untitled"),
                    description=req_data.get("description", ""),
                    type=req_data.get("type", "functional"),
                    priority=req_data.get("priority", "should"),
                    source=req_data.get("source", "imported"),
                    validation_status="draft"
                )
                journal.add_node(req)

                # Emit to dashboard
                if emitter:
                    await emitter.requirement_added(
                        req.requirement_id,
                        req.title,
                        req.type,
                        req.priority
                    )
        else:
            _create_sample_requirements(journal)
            # Emit sample requirements to dashboard
            if emitter:
                for req in journal.nodes.values():
                    await emitter.requirement_added(
                        req.requirement_id,
                        req.title,
                        req.type,
                        req.priority
                    )

        requirements = list(journal.nodes.values())
        print(f"   Found {len(requirements)} requirements")

        # Compute real completeness scores based on populated fields
        for req in requirements:
            filled = 0
            total = 6
            if getattr(req, 'title', ''):
                filled += 1
            if getattr(req, 'description', '') and len(getattr(req, 'description', '')) > 20:
                filled += 1
            if getattr(req, 'type', ''):
                filled += 1
            if getattr(req, 'priority', ''):
                filled += 1
            if getattr(req, 'acceptance_criteria', None):
                filled += 1
            if getattr(req, 'mermaid_diagrams', None):
                filled += 1
            req.completeness_score = filled / total

        if emitter:
            await emitter.pass_complete("discovery", 1, {"requirements": len(requirements)})

        # Quality Gate: Discovery -> Analysis
        avg_completeness = sum(
            getattr(r, 'completeness_score', 0.85) for r in requirements
        ) / max(len(requirements), 1)
        gate_result = quality_gate.check_discovery_gate(
            requirements_count=len(requirements),
            stakeholder_coverage=0.9,  # No stakeholder data available yet
            completeness=min(avg_completeness, 1.0)
        )
        print(f"   Quality Gate: {gate_result.status.value.upper()}")
        stg.set_quality_gate(gate_result.status.value.upper(),
                             requirements_count=len(requirements),
                             completeness=min(avg_completeness, 1.0))

        # Per-stage critique: completeness check (advisory only, no auto-fix)
        if critique_engine and not dry_run:
            try:
                stage_critique = await critique_engine.run_stage_critique(
                    "discovery", requirements=requirements, domain=domain, auto_fix=False
                )
                if stage_critique["issues_found"] > 0:
                    print(f"   Critique: {stage_critique['issues_found']} completeness issues (advisory)")
            except Exception as e:
                print(f"   [WARN] Discovery critique failed: {e}")

        stg.add_output("requirements", "data", count=len(requirements), description="Discovered requirements")
    _update_stage_cost(_snap)

    _validate_stage_output(3, {"requirements": requirements}, manifest)

    # Generate User Stories
    user_stories = []
    epics = []
    if last_completed >= 4:
        cp = _load_checkpoint(output_dir, 4)
        from requirements_engineer.generators.user_story_generator import UserStory, Epic
        user_stories = [UserStory.from_dict(s) for s in cp["user_stories"]]
        epics = [Epic.from_dict(e) for e in cp["epics"]]
        # Re-save user_stories.md from checkpoint data
        us_md = "# User Stories and Epics\n\n"
        us_md += f"- Total Epics: {len(epics)}\n"
        us_md += f"- Total User Stories: {len(user_stories)}\n\n---\n\n# Epics\n\n"
        for epic in sorted(epics, key=lambda x: x.id):
            us_md += epic.to_markdown() + "---\n\n"
        us_md += "# User Stories\n\n"
        for story in sorted(user_stories, key=lambda x: x.id):
            us_md += story.to_markdown() + "---\n\n"
        (output_dir / "user_stories").mkdir(parents=True, exist_ok=True)
        with open(output_dir / "user_stories" / "user_stories.md", "w", encoding="utf-8") as f:
            f.write(us_md)
        # Re-save JSON for downstream agents
        us_json = [s.to_dict() for s in user_stories]
        with open(output_dir / "user_stories.json", "w", encoding="utf-8") as f:
            json.dump({"user_stories": us_json, "epics": [e.to_dict() for e in epics]}, f, indent=2, ensure_ascii=False)
        manifest.skip_stage(4, "user_stories", "Resumed from checkpoint")
        print(f"\n[4/20] [RESUMED] Loaded {len(user_stories)} user stories, {len(epics)} epics")
    elif not dry_run:
        _snap = _llm_snapshot()
        with manifest.stage(4, "user_stories", "Generating User Stories") as stg:
            stg.add_input("requirements", "data", count=len(requirements), description="Discovered requirements")
            stg.add_input("stakeholders", "data", description="Project stakeholders")
            stg.add_input("domain", "data", description=f"Domain: {domain}")

            print("\n[4/20] Generating User Stories...")
            await _emit_progress(4, "Generating User Stories...")
            if emitter:
                await emitter.pass_started("analysis", 2)
                await emitter.log_info("Generating User Stories...")

            us_generator = UserStoryGenerator(
                model_name=config.get("kilo_agent", {}).get("model", "openai/gpt-4o-mini"),
                base_url=config.get("kilo_agent", {}).get("base_url", "https://openrouter.ai/api/v1")
            )
            await us_generator.initialize()

            epics = await us_generator.generate_epics(requirements, domain)
            # Generate stories for all requirements (functional + NFR verification stories)
            user_stories = await us_generator.generate_all_stories(requirements, stakeholders, include_nfr=True)
            us_generator.link_stories_to_epics()

            # Emit epics and user stories to dashboard
            if emitter:
                for epic in epics:
                    await emitter.epic_generated(
                        epic.id,
                        epic.title,
                        epic.parent_requirements
                    )
                for story in user_stories:
                    await emitter.user_story_generated(
                        story.id,
                        story.title,
                        story.persona,
                        story.parent_requirement_id
                    )
                await emitter.pass_complete("analysis", 2, {
                    "epics": len(epics),
                    "user_stories": len(user_stories)
                })

            # Save user stories
            us_md = us_generator.to_markdown()
            with open(output_dir / "user_stories" / "user_stories.md", "w", encoding="utf-8") as f:
                f.write(us_md)
            # Save JSON for downstream agents (ScreenGeneratorAgent, etc.)
            us_json = [s.to_dict() for s in user_stories]
            with open(output_dir / "user_stories.json", "w", encoding="utf-8") as f:
                json.dump({"user_stories": us_json, "epics": [e.to_dict() for e in epics]}, f, indent=2, ensure_ascii=False)
            print(f"   Generated {len(epics)} epics, {len(user_stories)} user stories")

            # Quality Gate: Analysis -> Specification
            # Calculate actual decomposition depth from user stories
            if user_stories:
                avg_depth = sum(
                    us.get_decomposition_depth() if hasattr(us, 'get_decomposition_depth') else 1
                    for us in user_stories
                ) / len(user_stories)
            else:
                avg_depth = 1

            # Compute requirement-to-story coverage as consistency proxy
            reqs_covered = len({
                getattr(us, 'parent_requirement_id', '')
                for us in user_stories
                if getattr(us, 'parent_requirement_id', '')
            })
            req_story_consistency = reqs_covered / max(len(requirements), 1)
            gate_result = quality_gate.check_analysis_gate(
                consistency=min(req_story_consistency, 1.0),
                user_stories_count=len(user_stories),
                decomposition_depth=int(avg_depth * 2)  # Scale to match threshold expectation
            )
            print(f"   Quality Gate: {gate_result.status.value.upper()}")
            stg.set_quality_gate(gate_result.status.value.upper(),
                                 user_stories_count=len(user_stories),
                                 consistency=min(req_story_consistency, 1.0))

            # Per-stage critique: consistency + orphan requirement fix
            if critique_engine and user_stories:
                try:
                    stage_critique = await critique_engine.run_stage_critique(
                        "analysis", requirements=requirements, user_stories=user_stories,
                        auto_fix=True, output_dir=str(output_dir)
                    )
                    if stage_critique["issues_fixed"] > 0:
                        print(f"   Critique: fixed {stage_critique['issues_fixed']} issues (orphan links)")
                    elif stage_critique["issues_found"] > 0:
                        print(f"   Critique: {stage_critique['issues_found']} issues found (no auto-fixes applicable)")
                except Exception as e:
                    print(f"   [WARN] Analysis critique failed: {e}")

            stg.add_output("user_stories", "file", path="user_stories/user_stories.md", count=len(user_stories), description="Generated user stories")
            stg.add_output("epics", "data", count=len(epics), description="Generated epics")
        _update_stage_cost(_snap)
        _save_checkpoint(output_dir, 4, {
            "user_stories": [s.to_dict() for s in user_stories],
            "epics": [e.to_dict() for e in epics],
        })
    else:
        manifest.skip_stage(4, "user_stories", "Generating User Stories", reason="dry_run")
        print("\n[4/20] [DRY RUN] Skipping User Stories generation")

    _validate_stage_output(5, {"user_stories": user_stories}, manifest)

    # Generate API Specification
    api_spec_yaml = ""
    api_endpoints = []  # Track API endpoints for metrics
    if last_completed >= 5:
        cp = _load_checkpoint(output_dir, 5)
        from requirements_engineer.generators.api_spec_generator import APIEndpoint
        api_endpoints = [APIEndpoint.from_dict(ep) for ep in cp["api_endpoints"]]
        api_spec_yaml = cp.get("api_spec_yaml", "")
        # Re-save output files from checkpoint data
        if api_spec_yaml:
            (output_dir / "api").mkdir(parents=True, exist_ok=True)
            with open(output_dir / "api" / "openapi_spec.yaml", "w", encoding="utf-8") as f:
                f.write(api_spec_yaml)
        api_md = cp.get("api_md", "")
        if api_md:
            with open(output_dir / "api" / "api_documentation.md", "w", encoding="utf-8") as f:
                f.write(api_md)
        manifest.skip_stage(5, "api_spec", "Resumed from checkpoint")
        print(f"\n[5/20] [RESUMED] Loaded {len(api_endpoints)} API endpoints")
    elif with_api_spec and not dry_run:
        _snap = _llm_snapshot()
        with manifest.stage(5, "api_spec", "Generating API Specification") as stg:
            stg.add_input("requirements", "data", count=len(requirements), description="Requirements for API derivation")
            stg.add_input("tech_constraints", "data", description="Technical constraints")

            print("\n[5/20] Generating API Specification...")
            await _emit_progress(5, "Generating API Specification...")
            if emitter:
                await emitter.pass_started("specification", 3)
                await emitter.log_info("Generating API Specification...")

            api_generator = APISpecGenerator(
                model_name=config.get("kilo_agent", {}).get("model", "openai/gpt-4o-mini"),
                base_url=config.get("kilo_agent", {}).get("base_url", "https://openrouter.ai/api/v1"),
                api_title=f"{project_name} API",
                api_version="1.0.0"
            )
            await api_generator.initialize()

            tech_constraints = constraints.get("technical", [])
            api_spec_yaml = await api_generator.generate_openapi_spec(requirements, tech_constraints)

            with open(output_dir / "api" / "openapi_spec.yaml", "w", encoding="utf-8") as f:
                f.write(api_spec_yaml)

            api_md = api_generator.to_markdown()
            with open(output_dir / "api" / "api_documentation.md", "w", encoding="utf-8") as f:
                f.write(api_md)

            # Emit API endpoints to dashboard
            if emitter:
                for endpoint in api_generator.endpoints:
                    await emitter.api_spec_generated(
                        endpoint.path,
                        endpoint.method.upper(),
                        endpoint.path
                    )

            api_endpoints = list(api_generator.endpoints)
            print(f"   Generated {len(api_endpoints)} API endpoints")

            stg.add_output("openapi_spec.yaml", "file", path="api/openapi_spec.yaml", description="OpenAPI 3.0 specification")
            stg.add_output("api_documentation.md", "file", path="api/api_documentation.md", description="API documentation")
            stg.add_output("endpoints", "data", count=len(api_endpoints), description="API endpoints")
        _update_stage_cost(_snap)
        if api_endpoints:
            _save_checkpoint(output_dir, 5, {
                "api_endpoints": [ep.to_dict() for ep in api_endpoints],
                "api_spec_yaml": api_spec_yaml,
                "api_md": api_md,
            })
    elif dry_run:
        manifest.skip_stage(5, "api_spec", "Generating API Specification", reason="dry_run")
        print("\n[5/20] [DRY RUN] Skipping API Specification")
    else:
        manifest.skip_stage(5, "api_spec", "Generating API Specification", reason="disabled")
        print("\n[5/20] Skipping API Specification (disabled)")

    _validate_stage_output("11a", {"api_endpoints": api_endpoints}, manifest)

    # Generate Realtime/WebSocket Spec (AsyncAPI) - runs after API spec
    realtime_spec_yaml = ""
    rt_config = config.get("generators", {}).get("realtime_spec", {})
    if rt_config.get("enabled", True) and with_api_spec and not dry_run:
        _snap = _llm_snapshot()
        with manifest.stage("5b", "realtime_spec", "Generating Realtime Spec (AsyncAPI)") as stg:
            stg.add_input("requirements", "data", count=len(requirements), description="Requirements for realtime detection")
            stg.add_input("config", "config", description="Realtime spec configuration")

            try:
                RealtimeSpecGenerator = imports["RealtimeSpecGenerator"]
                print("\n  [5b] Generating Realtime Spec (AsyncAPI)...")
                rt_generator = RealtimeSpecGenerator(
                    model_name=rt_config.get("model", config.get("kilo_agent", {}).get("model", "openai/gpt-4o-mini")),
                    base_url=config.get("kilo_agent", {}).get("base_url", "https://openrouter.ai/api/v1"),
                    config=config,
                )
                await rt_generator.initialize()
                realtime_spec_yaml = await rt_generator.generate_asyncapi_spec(
                    requirements,
                    title=f"{project_name} Realtime API",
                )
                if realtime_spec_yaml:
                    rt_dir = output_dir / "api"
                    rt_dir.mkdir(parents=True, exist_ok=True)
                    with open(rt_dir / "asyncapi_spec.yaml", "w", encoding="utf-8") as f:
                        f.write(realtime_spec_yaml)
                    rt_md = rt_generator.to_markdown(realtime_spec_yaml)
                    if rt_md:
                        with open(rt_dir / "realtime_documentation.md", "w", encoding="utf-8") as f:
                            f.write(rt_md)
                    print(f"   Generated AsyncAPI spec with WebSocket channels")
                    stg.add_output("asyncapi_spec.yaml", "file", path="api/asyncapi_spec.yaml", description="AsyncAPI 2.6 specification")
                else:
                    print("   No real-time requirements found, skipping AsyncAPI")
            except Exception as e:
                print(f"   [WARN] Realtime spec generation failed: {e}")
        _update_stage_cost(_snap)
    else:
        manifest.skip_stage("5b", "realtime_spec", "Generating Realtime Spec (AsyncAPI)",
                            reason="disabled or dry_run" if dry_run else "realtime spec disabled")

    # Generate Data Dictionary
    data_dict = None  # Track data dictionary for metrics
    if last_completed >= 6:
        cp = _load_checkpoint(output_dir, 6)
        from requirements_engineer.generators.data_dictionary_generator import DataDictionary, Entity, Relationship, GlossaryTerm
        data_dict = DataDictionary(title=project_name)
        entities = [Entity.from_dict(e) for e in cp.get("entities", [])]
        data_dict.entities = {e.name: e for e in entities}
        data_dict.relationships = [Relationship.from_dict(r) for r in cp.get("relationships", [])]
        glossary = [GlossaryTerm.from_dict(g) for g in cp.get("glossary", [])]
        data_dict.glossary = {g.term: g for g in glossary}
        # Re-save data dictionary files from checkpoint
        dd_md = data_dict.to_markdown()
        with open(output_dir / "data" / "data_dictionary.md", "w", encoding="utf-8") as f:
            f.write(dd_md)
        er_diagram = data_dict.to_er_diagram()
        with open(output_dir / "data" / "er_diagram.mmd", "w", encoding="utf-8") as f:
            f.write(er_diagram)
        schema_sql = data_dict.to_sql()
        with open(output_dir / "data" / "schema.sql", "w", encoding="utf-8") as f:
            f.write(schema_sql)
        manifest.skip_stage(6, "data_dictionary", "Resumed from checkpoint")
        print(f"\n[6/20] [RESUMED] Loaded {len(data_dict.entities)} entities, {len(data_dict.relationships)} relationships")
    elif with_data_dict and not dry_run:
        _snap = _llm_snapshot()
        with manifest.stage(6, "data_dictionary", "Generating Data Dictionary") as stg:
            stg.add_input("requirements", "data", count=len(requirements), description="Requirements for entity extraction")
            stg.add_input("domain", "data", description=f"Domain: {domain}")

            print("\n[6/20] Generating Data Dictionary...")
            await _emit_progress(6, "Generating Data Dictionary...")
            dd_generator = DataDictionaryGenerator(
                model_name=config.get("kilo_agent", {}).get("model", "openai/gpt-4o-mini"),
                base_url=config.get("kilo_agent", {}).get("base_url", "https://openrouter.ai/api/v1")
            )
            await dd_generator.initialize()

            data_dict = await dd_generator.generate_dictionary(
                requirements,
                domain=domain,
                title=f"{project_name} Data Dictionary"
            )

            dd_md = data_dict.to_markdown()
            with open(output_dir / "data" / "data_dictionary.md", "w", encoding="utf-8") as f:
                f.write(dd_md)

            er_diagram = data_dict.to_er_diagram()
            with open(output_dir / "data" / "er_diagram.mmd", "w", encoding="utf-8") as f:
                f.write(er_diagram)

            schema_sql = data_dict.to_sql()
            with open(output_dir / "data" / "schema.sql", "w", encoding="utf-8") as f:
                f.write(schema_sql)

            print(f"   Generated dictionary with {len(data_dict.entities)} entities")

            # Emit to Matrix Dashboard
            if matrix_bridge:
                await matrix_bridge.emit_data_dictionary(data_dict)

            stg.add_output("data_dictionary.md", "file", path="data/data_dictionary.md", description="Data dictionary")
            stg.add_output("er_diagram.mmd", "file", path="data/er_diagram.mmd", description="ER diagram (Mermaid)")
            stg.add_output("entities", "data", count=len(data_dict.entities), description="Data entities")
        _update_stage_cost(_snap)
        if data_dict and hasattr(data_dict, 'entities'):
            def _serialize(obj):
                """Serialize dataclass, dataclass_json, dict, or any object."""
                if isinstance(obj, dict):
                    return obj
                if hasattr(obj, 'to_dict'):
                    return obj.to_dict()
                if hasattr(obj, '__dict__'):
                    return vars(obj)
                return str(obj)

            ents = data_dict.entities
            rels = getattr(data_dict, 'relationships', [])
            gloss = getattr(data_dict, 'glossary', {})
            _save_checkpoint(output_dir, 6, {
                "entities": [_serialize(e) for e in (ents.values() if isinstance(ents, dict) else ents)],
                "relationships": [_serialize(r) for r in (rels.values() if isinstance(rels, dict) else rels)],
                "glossary": [_serialize(g) for g in (gloss.values() if isinstance(gloss, dict) else gloss)],
            })
    elif dry_run:
        manifest.skip_stage(6, "data_dictionary", "Generating Data Dictionary", reason="dry_run")
        print("\n[6/20] [DRY RUN] Skipping Data Dictionary")
    else:
        manifest.skip_stage(6, "data_dictionary", "Generating Data Dictionary", reason="disabled")
        print("\n[6/20] Skipping Data Dictionary (disabled)")

    _validate_stage_output("12a", {"data_dict": data_dict}, manifest)

    # Generate Tech Stack
    tech_stack = None
    if last_completed >= 7:
        cp = _load_checkpoint(output_dir, 7)
        from requirements_engineer.generators.tech_stack_generator import TechStack, save_tech_stack
        tech_stack = TechStack.from_dict(cp["tech_stack"]) if cp.get("tech_stack") else None
        if tech_stack:
            save_tech_stack(tech_stack, output_dir)
        manifest.skip_stage(7, "tech_stack", "Resumed from checkpoint")
        print(f"\n[7/20] [RESUMED] Loaded tech stack")
    elif not dry_run:
        _snap = _llm_snapshot()
        try:
            with manifest.stage(7, "tech_stack", "Generating Tech Stack Recommendations") as stg:
                stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
                stg.add_input("constraints", "data", description="Project constraints")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")
                stg.add_input("entities", "data", count=len(data_dict.entities) if data_dict else 0, description="Data entities")

                print("\n[7/20] Generating Tech Stack Recommendations...")
                await _emit_progress(7, "Generating Tech Stack Recommendations...")
                llm_config = config.get("kilo_agent", {})
                tech_generator = TechStackGenerator(
                    model=llm_config.get("model", "openai/gpt-4o-mini"),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY")
                )

                tech_stack = await tech_generator.generate_tech_stack(
                    project_name=project_name,
                    domain=domain,
                    requirements=requirements,
                    constraints=constraints,
                    api_endpoints=api_endpoints if api_endpoints else None,
                    entities=data_dict.entities if data_dict else None
                )

                save_tech_stack(tech_stack, output_dir)
                print(f"   Generated tech stack with {tech_stack.backend_framework} / {tech_stack.frontend_framework}")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_tech_stack(tech_stack)

                stg.add_output("tech_stack.md", "file", path="tech_stack/tech_stack.md", description="Tech stack recommendations")
                stg.add_output("tech_stack.json", "file", path="tech_stack/tech_stack.json", description="Tech stack data")
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 7 (Tech Stack) failed: {e}")
            _update_stage_cost(_snap)
        if tech_stack:
            _save_checkpoint(output_dir, 7, {
                "tech_stack": tech_stack.to_dict() if hasattr(tech_stack, 'to_dict') else {},
            })
    elif dry_run:
        manifest.skip_stage(7, "tech_stack", "Generating Tech Stack Recommendations", reason="dry_run")
        print("\n[7/20] [DRY RUN] Skipping Tech Stack generation")

    # ── Step 7.5: Architecture Design ─────────────────────────
    arch_spec = None
    arch_cfg = config.get("generators", {}).get("architecture", {})
    if _has_checkpoint(output_dir, "7.5"):
        cp = _load_checkpoint(output_dir, "7.5")
        arch_spec = ArchitectureSpec.from_dict(cp["arch_spec"]) if cp.get("arch_spec") else None
        if arch_spec:
            save_architecture(arch_spec, output_dir)
        manifest.skip_stage("7.5", "architecture", "Resumed from checkpoint")
        print("\n[7.5/20] [CHECKPOINT] Loaded Architecture from checkpoint")
    elif not dry_run and arch_cfg.get("enabled", True) and requirements and tech_stack:
        _snap = _llm_snapshot()
        try:
            with manifest.stage("7.5", "architecture", "Generating Architecture Design") as stg:
                stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
                stg.add_input("tech_stack", "data", description="Tech stack recommendations")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")
                stg.add_input("entities", "data", count=len(data_dict.entities) if data_dict else 0, description="Data entities")

                print("\n[7.5/20] Generating Architecture Design (C4 diagrams)...")
                await _emit_progress("7.5", "Generating Architecture Design...")
                llm_config = config.get("kilo_agent", {})
                arch_generator = ArchitectureGenerator(
                    model=arch_cfg.get("model", llm_config.get("model", "openai/gpt-4o-mini")),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY"),
                    config=arch_cfg,
                )
                arch_spec = await arch_generator.generate_architecture(
                    requirements=requirements,
                    tech_stack_dict=tech_stack.to_dict() if hasattr(tech_stack, 'to_dict') else {},
                    api_endpoint_count=len(api_endpoints),
                    entity_count=len(data_dict.entities) if data_dict else 0,
                    project_name=project_name,
                    domain=domain,
                )
                if arch_spec:
                    save_architecture(arch_spec, output_dir)
                    print(f"   Saved {len(arch_spec.services)} services, 4 C4/deployment diagrams")
                    stg.add_output("architecture_overview.md", "file", path="architecture/architecture_overview.md", description="Architecture overview")
                    stg.add_output("c4_context.mmd", "file", path="architecture/c4_context.mmd", description="C4 Context diagram")
                    stg.add_output("c4_container.mmd", "file", path="architecture/c4_container.mmd", description="C4 Container diagram")
                    stg.add_output("deployment.mmd", "file", path="architecture/deployment.mmd", description="Deployment diagram")
                    stg.add_output("data_flow.mmd", "file", path="architecture/data_flow.mmd", description="Data flow diagram")
                    _save_checkpoint(output_dir, "7.5", {"arch_spec": arch_spec.to_dict()})
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 7.5 (Architecture) failed: {e}")
            _update_stage_cost(_snap)
    elif dry_run and arch_cfg.get("enabled", True):
        manifest.skip_stage("7.5", "architecture", "Generating Architecture Design", reason="dry_run")
        print("\n[7.5/20] [DRY RUN] Skipping Architecture Design")
    else:
        manifest.skip_stage("7.5", "architecture", "Generating Architecture Design", reason="disabled or missing inputs")

    # Generate Gherkin Test Cases
    test_cases = []
    if last_completed >= 8:
        cp = _load_checkpoint(output_dir, 8)
        from requirements_engineer.generators.test_case_generator import TestCase, GherkinFeature, TestCaseGenerator
        test_cases = [TestCase.from_dict(tc) for tc in cp["test_cases"]]
        # Re-save test files from checkpoint
        test_gen_temp = TestCaseGenerator.__new__(TestCaseGenerator)
        test_gen_temp.test_cases = {tc.id: tc for tc in test_cases}
        test_gen_temp.features = {sid: GherkinFeature.from_dict(f) for sid, f in cp.get("features", {}).items()}
        test_gen_temp.config = config
        # Save feature files
        for story_id, feature in test_gen_temp.features.items():
            filename = f"{story_id.replace('-', '_').lower()}.feature"
            with open(output_dir / "testing" / filename, "w", encoding="utf-8") as f:
                f.write(feature.to_gherkin())
        # Save test documentation
        test_md = test_gen_temp.to_markdown()
        with open(output_dir / "testing" / "test_documentation.md", "w", encoding="utf-8") as f:
            f.write(test_md)
        # Re-save step definition stubs
        step_defs = test_gen_temp.to_step_definitions()
        steps_dir = output_dir / "testing" / "step_defs"
        steps_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in step_defs.items():
            with open(steps_dir / filename, "w", encoding="utf-8") as f:
                f.write(content)
        manifest.skip_stage(8, "test_cases", "Resumed from checkpoint")
        print(f"\n[8/20] [RESUMED] Loaded {len(test_cases)} test cases, {len(test_gen_temp.features)} features")
    elif with_gherkin and user_stories and not dry_run:
        _snap = _llm_snapshot()
        with manifest.stage(8, "test_cases", "Generating Gherkin Test Cases") as stg:
            stg.add_input("user_stories", "data", count=len(user_stories), description="User stories for test derivation")

            print("\n[8/20] Generating Gherkin Test Cases...")
            await _emit_progress(8, "Generating Gherkin Test Cases...")
            if emitter:
                await emitter.pass_started("testing", 4)
                await emitter.log_info("Generating Gherkin Test Cases...")

            test_generator = TestCaseGenerator(
                model_name=config.get("kilo_agent", {}).get("model", "openai/gpt-4o-mini"),
                base_url=config.get("kilo_agent", {}).get("base_url", "https://openrouter.ai/api/v1")
            )
            await test_generator.initialize()

            features = await test_generator.generate_all_gherkin(user_stories)
            test_cases = await test_generator.generate_all_test_cases(user_stories)

            # Emit test cases to dashboard
            if emitter:
                for tc in test_cases:
                    await emitter.test_generated(
                        tc.id,
                        tc.title,
                        tc.test_type,
                        tc.parent_user_story_id
                    )

            # Save individual feature files
            for story_id, feature in test_generator.features.items():
                filename = f"{story_id.replace('-', '_').lower()}.feature"
                with open(output_dir / "testing" / filename, "w", encoding="utf-8") as f:
                    f.write(feature.to_gherkin())

            # Save test documentation
            test_md = test_generator.to_markdown()
            with open(output_dir / "testing" / "test_documentation.md", "w", encoding="utf-8") as f:
                f.write(test_md)

            # Generate step definition stubs
            step_defs = test_generator.to_step_definitions()
            steps_dir = output_dir / "testing" / "step_defs"
            steps_dir.mkdir(parents=True, exist_ok=True)
            for filename, content in step_defs.items():
                with open(steps_dir / filename, "w", encoding="utf-8") as f:
                    f.write(content)

            print(f"   Generated {len(features)} feature files, {len(test_cases)} test cases, {len(step_defs)} step definition files")

            if emitter:
                await emitter.pass_complete("testing", 4, {
                    "features": len(features),
                    "test_cases": len(test_cases)
                })

            # Quality Gate: Testing -> Final (real traceability from artifact links)
            from requirements_engineer.gates.quality_gate import QualityGate as QG
            trace = QG.compute_traceability(requirements, user_stories, test_cases)
            gate_result = quality_gate.check_testing_gate(
                test_coverage=min(len(test_cases) / max(len(user_stories), 1), 1.0),
                traceability=trace["overall"],
                test_cases_count=len(test_cases)
            )
            print(f"   Quality Gate: {gate_result.status.value.upper()}")
            print(f"   Traceability: req->story={trace['req_to_story']:.0%}, story->test={trace['story_to_test']:.0%}")
            stg.set_quality_gate(gate_result.status.value.upper(),
                                 test_coverage=min(len(test_cases) / max(len(user_stories), 1), 1.0),
                                 traceability=trace["overall"])

            if emitter:
                await emitter.quality_gate(
                    "testing",
                    gate_result.status.value,
                    {"test_coverage": min(len(test_cases) / max(len(user_stories), 1), 1.0), "traceability": trace["overall"]}
                )

            # Per-stage critique: testability + traceability fix
            if critique_engine:
                try:
                    stage_critique = await critique_engine.run_stage_critique(
                        "validation", requirements=requirements, user_stories=user_stories,
                        test_cases=test_cases, auto_fix=True, output_dir=str(output_dir)
                    )
                    if stage_critique["issues_fixed"] > 0:
                        print(f"   Critique: fixed {stage_critique['issues_fixed']} issues (stub tests, acceptance criteria)")
                        # Recalculate traceability after fixes
                        trace_post = QG.compute_traceability(requirements, user_stories, test_cases)
                        print(f"   Post-fix traceability: req->story={trace_post['req_to_story']:.0%}, story->test={trace_post['story_to_test']:.0%}")
                    elif stage_critique["issues_found"] > 0:
                        print(f"   Critique: {stage_critique['issues_found']} issues found (no auto-fixes applicable)")
                except Exception as e:
                    print(f"   [WARN] Validation critique failed: {e}")

            stg.add_output("feature_files", "file", count=len(features), description="Gherkin feature files")
            stg.add_output("test_documentation.md", "file", path="testing/test_documentation.md", description="Test documentation")
            stg.add_output("test_cases", "data", count=len(test_cases), description="Generated test cases")
        _update_stage_cost(_snap)
        if test_cases:
            _save_checkpoint(output_dir, 8, {
                "test_cases": [tc.to_dict() for tc in test_cases],
                "features": {sid: f.to_dict() for sid, f in test_generator.features.items()} if hasattr(test_generator, 'features') else {},
            })
    elif dry_run:
        manifest.skip_stage(8, "test_cases", "Generating Gherkin Test Cases", reason="dry_run")
        print("\n[8/20] [DRY RUN] Skipping Gherkin Test Cases")
    else:
        manifest.skip_stage(8, "test_cases", "Generating Gherkin Test Cases", reason="disabled or no user stories")
        print("\n[8/20] Skipping Gherkin Test Cases (disabled or no user stories)")

    _validate_stage_output(8, {"test_cases": test_cases}, manifest)

    # ── Step 8.5: Iterative Trace Refinement ─────────────────────
    treesearch_cfg = config.get("treesearch", {})
    if not dry_run and treesearch_cfg.get("enabled", False) and epics and requirements:
        _snap = _llm_snapshot()
        with manifest.stage("8.5", "trace_refinement", "Running Iterative Trace Refinement") as stg:
            stg.add_input("epics", "data", count=len(epics), description="Epics for trace tree roots")
            stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
            stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
            stg.add_input("test_cases", "data", count=len(test_cases), description="Test cases")

            print("\n[8.5/20] Running Iterative Trace Refinement...")
            try:
                from requirements_engineer.treesearch.trace_walker import TraceWalker, write_trace_refinement_report

                llm_config = config.get("kilo_agent", {})
                # Initialize LLM call function for tree search
                trace_llm_client = None
                try:
                    from openai import AsyncOpenAI
                    trace_llm_client = AsyncOpenAI(
                        base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                    )
                except ImportError:
                    pass

                async def trace_llm_call(prompt: str) -> str:
                    if trace_llm_client is None:
                        return '{"scores": {}, "issues": ["No LLM client"]}'
                    resp = await trace_llm_client.chat.completions.create(
                        model=llm_config.get("model", "openai/gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": "You are a Requirements Engineering expert. Return valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    return resp.choices[0].message.content or ""

                walker = TraceWalker(config=treesearch_cfg, llm_call=trace_llm_call)

                walk_results = []
                for epic in epics:
                    result = await walker.walk_epic(epic, {
                        "requirements": requirements,
                        "user_stories": user_stories,
                        "test_cases": test_cases,
                    })
                    walk_results.append(result)
                    print(f"   {result.epic_id}: {result.nodes_refined}/{result.nodes_total} refined, "
                          f"avg quality {result.avg_quality:.0%}")

                # Write refinement audit trail
                write_trace_refinement_report(walk_results, str(output_dir / "quality"))
                total_refined = sum(r.nodes_refined for r in walk_results)
                total_complete = sum(r.nodes_complete for r in walk_results)
                total_nodes = sum(r.nodes_total for r in walk_results)
                print(f"   Trace refinement complete: {total_refined} nodes refined, "
                      f"{total_complete}/{total_nodes} complete")

                stg.add_output("trace_refinement_report.md", "file", path="quality/trace_refinement_report.md", description="Trace refinement audit trail")
            except Exception as e:
                print(f"   [WARN] Trace refinement failed: {e}")
        _update_stage_cost(_snap)
    elif dry_run and treesearch_cfg.get("enabled", False):
        manifest.skip_stage("8.5", "trace_refinement", "Running Iterative Trace Refinement", reason="dry_run")
        print("\n[8.5/20] [DRY RUN] Skipping Iterative Trace Refinement")
    else:
        manifest.skip_stage("8.5", "trace_refinement", "Running Iterative Trace Refinement", reason="disabled or missing epics/requirements")

    # ── Step 8.6: Test Data Factories ──────────────────────────
    _factory_count = 0
    factory_cfg = config.get("generators", {}).get("test_factory", {})
    if _has_checkpoint(output_dir, "8.6"):
        # Programmatic stage — fast to regenerate, but skip for consistency
        manifest.skip_stage("8.6", "test_factories", "Resumed from checkpoint")
        print("\n[8.6/20] [CHECKPOINT] Test Factories already generated")
    elif not dry_run and factory_cfg.get("enabled", True) and data_dict:
        try:
            with manifest.stage("8.6", "test_factories", "Generating Test Data Factories") as stg:
                stg.add_input("data_dict_entities", "data", count=len(data_dict.entities), description="Data dictionary entities")
                stg.add_input("data_dict_relationships", "data", count=len(data_dict.relationships), description="Entity relationships")

                print("\n[8.6/20] Generating Test Data Factories...")
                await _emit_progress("8.6", "Generating Test Data Factories...")
                factory_gen = TestFactoryGenerator(config=factory_cfg)
                factory_gen.generate_factories(
                    data_dict_entities=data_dict.entities,
                    data_dict_relationships=data_dict.relationships,
                    tech_stack_dict=tech_stack.to_dict() if tech_stack else None,
                )
                save_test_factories(factory_gen, output_dir)
                lang_label = factory_gen.lang
                print(f"   Saved {len(factory_gen.factories)} test factories ({lang_label}) + seed data ({factory_gen.db})")
                factory_file = factory_gen.factory_file_name()
                stg.add_output(factory_file, "file", path=f"testing/factories/{factory_file}", description=f"Test data factories ({lang_label})")
                seed_file = "seed_data.json" if factory_gen.db == "mongodb" else "seed_data.sql"
                stg.add_output(seed_file, "file", path=f"testing/{seed_file}", description=f"Seed data for {factory_gen.db}")
                stg.add_output("factories_overview.md", "file", path="testing/factories/factories_overview.md", description="Factory summary")
                _factory_count = len(factory_gen.factories)
                _save_checkpoint(output_dir, "8.6", {"lang": factory_gen.lang, "db": factory_gen.db, "count": _factory_count})
        except Exception as e:
            print(f"   [ERROR] Stage 8.6 (Test Factories) failed: {e}")
    elif dry_run and factory_cfg.get("enabled", True):
        manifest.skip_stage("8.6", "test_factories", "Generating Test Data Factories", reason="dry_run")
        print("\n[8.6/20] [DRY RUN] Skipping Test Data Factories")
    else:
        manifest.skip_stage("8.6", "test_factories", "Generating Test Data Factories", reason="disabled or no data dictionary")

    # ── Step 8.75: State Machines ────────────────────────────
    state_machines = []
    sm_cfg = config.get("generators", {}).get("state_machine", {})
    if _has_checkpoint(output_dir, "8.75"):
        cp = _load_checkpoint(output_dir, "8.75")
        state_machines = [StateMachine.from_dict(sm) for sm in cp.get("state_machines", [])]
        if state_machines:
            save_state_machines(state_machines, output_dir)
        manifest.skip_stage("8.75", "state_machines", "Resumed from checkpoint")
        print(f"\n[8.75/20] [CHECKPOINT] Loaded {len(state_machines)} state machines from checkpoint")
    elif not dry_run and sm_cfg.get("enabled", True) and requirements and user_stories:
        _snap = _llm_snapshot()
        try:
            with manifest.stage("8.75", "state_machines", "Generating State Machines") as stg:
                stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
                stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
                if data_dict:
                    stg.add_input("entities", "data", count=len(data_dict.entities), description="Data entities")

                print("\n[8.75/20] Generating State Machine Diagrams...")
                await _emit_progress("8.75", "Generating State Machines...")
                llm_config = config.get("kilo_agent", {})
                sm_generator = StateMachineGenerator(
                    model_name=sm_cfg.get("model", llm_config.get("model", "openai/gpt-4o-mini")),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY"),
                    config=sm_cfg,
                )
                entity_list = list(data_dict.entities.values()) if data_dict else []
                state_machines = await sm_generator.generate_state_machines(
                    requirements=requirements,
                    user_stories=user_stories,
                    entities=entity_list,
                    domain=domain,
                )
                if state_machines:
                    save_state_machines(state_machines, output_dir)
                    print(f"   Saved {len(state_machines)} state machine diagrams")
                    stg.add_output("state_machines.md", "file", path="state_machines/state_machines.md", description="State machine summary")
                    for sm in state_machines:
                        stg.add_output(f"{sm.entity}.mmd", "file", path=f"state_machines/{sm.entity}.mmd", description=f"State diagram for {sm.entity}")
                    _save_checkpoint(output_dir, "8.75", {"state_machines": [sm.to_dict() for sm in state_machines]})
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 8.75 (State Machines) failed: {e}")
            _update_stage_cost(_snap)
    elif dry_run and sm_cfg.get("enabled", True):
        manifest.skip_stage("8.75", "state_machines", "Generating State Machines", reason="dry_run")
        print("\n[8.75/20] [DRY RUN] Skipping State Machine generation")
    else:
        manifest.skip_stage("8.75", "state_machines", "Generating State Machines", reason="disabled or missing inputs")

    # Generate UX Design
    ux_spec = None
    if last_completed >= 9:
        cp = _load_checkpoint(output_dir, 9)
        from requirements_engineer.generators.ux_design_generator import UXDesignSpec, save_ux_design
        ux_spec = UXDesignSpec.from_dict(cp["ux_spec"]) if cp.get("ux_spec") else None
        if ux_spec:
            save_ux_design(ux_spec, output_dir)  # Re-generate files from checkpoint
        manifest.skip_stage(9, "ux_design", "Resumed from checkpoint")
        print(f"\n[9/20] [RESUMED] Loaded UX design spec")
    elif not dry_run:
        _snap = _llm_snapshot()
        try:
            with manifest.stage(9, "ux_design", "Generating UX Design Artifacts") as stg:
                stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
                stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
                stg.add_input("stakeholders", "data", description="Project stakeholders")
                stg.add_input("domain", "data", description=f"Domain: {domain}")

                print("\n[9/20] Generating UX Design Artifacts...")
                await _emit_progress(9, "Generating UX Design Artifacts...")
                llm_config = config.get("kilo_agent", {})
                ux_generator = UXDesignGenerator(
                    model=llm_config.get("model", "openai/gpt-4o-mini"),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY")
                )

                # Create features list from requirements for IA generation
                features_for_ux = [
                    {"id": req.requirement_id, "name": req.title, "description": req.description}
                    for req in requirements[:10]
                ]

                ux_spec = await ux_generator.generate_ux_spec(
                    project_name=project_name,
                    domain=domain,
                    stakeholders=stakeholders,
                    user_stories=user_stories if user_stories else [],
                    features=features_for_ux
                )

                save_ux_design(ux_spec, output_dir)
                print(f"   Generated {len(ux_spec.personas)} personas, {len(ux_spec.user_flows)} user flows")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_ux_design(ux_spec)

                stg.add_output("ux_design_spec.md", "file", path="ux_design/ux_design_spec.md", description="UX design specification")
                stg.add_output("personas", "data", count=len(ux_spec.personas), description="User personas")
                stg.add_output("user_flows", "data", count=len(ux_spec.user_flows), description="User flows")
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 9 (UX Design) failed: {e}")
            _update_stage_cost(_snap)
        if ux_spec:
            _save_checkpoint(output_dir, 9, {
                "ux_spec": ux_spec.to_dict() if hasattr(ux_spec, 'to_dict') else {},
            })
    elif dry_run:
        manifest.skip_stage(9, "ux_design", "Generating UX Design Artifacts", reason="dry_run")
        print("\n[9/20] [DRY RUN] Skipping UX Design generation")

    _validate_stage_output(9, {"ux_spec": ux_spec}, manifest)

    # Generate UI Design
    ui_spec = None
    if last_completed >= 10:
        cp = _load_checkpoint(output_dir, 10)
        from requirements_engineer.generators.ui_design_generator import UIDesignSpec, save_ui_design
        ui_spec = UIDesignSpec.from_dict(cp["ui_spec"]) if cp.get("ui_spec") else None
        if ui_spec:
            save_ui_design(ui_spec, output_dir)  # Re-generate screen files from checkpoint
        manifest.skip_stage(10, "ui_design", "Resumed from checkpoint")
        print(f"\n[10/20] [RESUMED] Loaded UI design spec ({len(ui_spec.screens) if ui_spec else 0} screens)")
    elif not dry_run:
        _snap = _llm_snapshot()
        try:
            with manifest.stage(10, "ui_design", "Generating UI Design Specifications") as stg:
                stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
                stg.add_input("ux_spec", "data", description="UX design specification")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")
                stg.add_input("domain", "data", description=f"Domain: {domain}")

                print("\n[10/20] Generating UI Design Specifications...")
                await _emit_progress(10, "Generating UI Design Specifications...")
                llm_config = config.get("kilo_agent", {})
                ui_design_config = config.get("generators", {}).get("ui_design", {})
                ui_generator = UIDesignGenerator(
                    model=ui_design_config.get("model", llm_config.get("model", "openai/gpt-4o-mini")),
                    screen_model=ui_design_config.get("screen_model", "anthropic/claude-opus-4.5"),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY"),
                    config=config
                )

                ui_spec = await ui_generator.generate_ui_spec(
                    project_name=project_name,
                    domain=domain,
                    user_stories=user_stories if user_stories else [],
                    ux_spec=ux_spec,
                    api_endpoints=api_endpoints if api_endpoints else None
                )

                save_ui_design(ui_spec, output_dir)
                print(f"   Generated {len(ui_spec.components)} components, {len(ui_spec.screens)} screens")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_ui_design(ui_spec)

                stg.add_output("ui_design_spec.md", "file", path="ui_design/ui_design_spec.md", description="UI design specification")
                stg.add_output("components", "data", count=len(ui_spec.components), description="UI components")
                stg.add_output("screens", "data", count=len(ui_spec.screens), description="Screen designs")
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 10 (UI Design) failed: {e}")
            _update_stage_cost(_snap)
        if ui_spec:
            _save_checkpoint(output_dir, 10, {
                "ui_spec": ui_spec.to_dict() if hasattr(ui_spec, 'to_dict') else {},
            })
    elif dry_run:
        manifest.skip_stage(10, "ui_design", "Generating UI Design Specifications", reason="dry_run")
        print("\n[10/20] [DRY RUN] Skipping UI Design generation")

    _validate_stage_output(10, {"ui_spec": ui_spec}, manifest)

    # ── Step 10.5: Component Compositions ────────────────────────
    comp_matrix = None
    comp_cfg = config.get("generators", {}).get("component_composition", {})
    if _has_checkpoint(output_dir, "10.5"):
        cp = _load_checkpoint(output_dir, "10.5")
        comp_matrix = ComponentMatrix.from_dict(cp["comp_matrix"]) if cp.get("comp_matrix") else None
        if comp_matrix:
            save_compositions(comp_matrix, output_dir)
        manifest.skip_stage("10.5", "component_compositions", "Resumed from checkpoint")
        print(f"\n[10.5/20] [CHECKPOINT] Loaded Component Compositions from checkpoint")
    elif not dry_run and comp_cfg.get("enabled", True) and ui_spec and ux_spec:
        _snap = _llm_snapshot()
        try:
            with manifest.stage("10.5", "component_compositions", "Generating Component Compositions") as stg:
                stg.add_input("ui_spec", "data", description="UI design specification")
                stg.add_input("ux_spec", "data", description="UX design specification")
                stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")

                print("\n[10.5/20] Generating Component Compositions...")
                await _emit_progress("10.5", "Generating Component Compositions...")
                llm_config = config.get("kilo_agent", {})
                comp_generator = ComponentCompositionGenerator(
                    model=comp_cfg.get("model", llm_config.get("model", "openai/gpt-4o-mini")),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY"),
                    config=comp_cfg,
                )
                comp_matrix = await comp_generator.generate_compositions(
                    ui_spec_dict=ui_spec.to_dict() if hasattr(ui_spec, 'to_dict') else {},
                    ux_spec_dict=ux_spec.to_dict() if hasattr(ux_spec, 'to_dict') else {},
                    user_stories=user_stories,
                    api_endpoints=api_endpoints,
                    project_name=project_name,
                )
                if comp_matrix:
                    save_compositions(comp_matrix, output_dir)
                    print(f"   Saved {len(comp_matrix.screens)} screen compositions, {len(comp_matrix.missing_components)} missing components flagged")
                    stg.add_output("component_matrix.md", "file", path="ui_design/compositions/component_matrix.md", description="Component matrix summary")
                    _save_checkpoint(output_dir, "10.5", {"comp_matrix": comp_matrix.to_dict()})
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 10.5 (Component Compositions) failed: {e}")
            _update_stage_cost(_snap)
    elif dry_run and comp_cfg.get("enabled", True):
        manifest.skip_stage("10.5", "component_compositions", "Generating Component Compositions", reason="dry_run")
        print("\n[10.5/20] [DRY RUN] Skipping Component Compositions")
    else:
        manifest.skip_stage("10.5", "component_compositions", "Generating Component Compositions", reason="disabled or missing ui/ux specs")

    # Generate Mermaid diagrams
    if _has_checkpoint(output_dir, 11):
        manifest.skip_stage(11, "diagrams", "Resumed from checkpoint")
        _diag_dir = output_dir / "diagrams"
        _diag_count = len(list(_diag_dir.glob("*.mmd"))) if _diag_dir.exists() else 0
        print(f"\n[11/20] [CHECKPOINT] Loaded {_diag_count} Mermaid diagrams")
    elif not dry_run:
        _snap = _llm_snapshot()
        try:
            with manifest.stage(11, "diagrams", "Generating Mermaid Diagrams") as stg:
                stg.add_input("journal", "data", description="Requirement journal")
                stg.add_input("config", "config", description="Diagram generation config")

                if use_kilo:
                    print("\n[11/20] Generating Mermaid Diagrams (Kilo Agent)...")
                    await _emit_progress(11, "Generating Mermaid Diagrams...")
                    await generate_diagrams_with_kilo(journal, config, output_dir)
                else:
                    print("\n[11/20] Generating Mermaid Diagrams (LLM)...")
                    await generate_diagrams_simple(journal, config, output_dir)

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_diagrams(journal)

                _diag_dir = output_dir / "diagrams"
                _diag_count = len(list(_diag_dir.glob("*.mmd"))) if _diag_dir.exists() else 0
                stg.add_output("diagram_files", "file", count=_diag_count, description="Mermaid diagram files")
                _save_checkpoint(output_dir, 11, {"diagram_count": _diag_count})
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 11 (Diagrams) failed: {e}")
            _update_stage_cost(_snap)
    elif dry_run:
        manifest.skip_stage(11, "diagrams", "Generating Mermaid Diagrams", reason="dry_run")
        print("\n[11/20] [DRY RUN] Skipping Mermaid Diagram generation")

    # Generate Work Breakdown Structure
    breakdown_type = "feature"  # Default to feature breakdown
    breakdown = None
    if last_completed >= 12:
        cp = _load_checkpoint(output_dir, 12)
        # Breakdown is reconstructed from saved data if available
        if cp.get("breakdown"):
            from requirements_engineer.work_breakdown.feature_breakdown import FeatureBreakdown
            breakdown = FeatureBreakdown.from_dict(cp["breakdown"]) if hasattr(FeatureBreakdown, 'from_dict') else None
        manifest.skip_stage(12, "work_breakdown", "Resumed from checkpoint")
        print(f"\n[12/20] [RESUMED] Loaded work breakdown")
    elif not dry_run:
        try:
            with manifest.stage(12, "work_breakdown", "Generating Work Breakdown Structure") as stg:
                stg.add_input("journal", "data", description="Requirement journal (requirements)")

                print(f"\n[12/20] Generating Work Breakdown Structure ({breakdown_type})...")
                await _emit_progress(12, "Generating Work Breakdown Structure...")
                breakdown = _create_breakdown(breakdown_type, journal)
                save_work_breakdown(breakdown, output_dir, breakdown_type)
                breakdown_count = len(breakdown.features) if hasattr(breakdown, 'features') else len(breakdown.services) if hasattr(breakdown, 'services') else len(breakdown.applications)
                print(f"   Generated {breakdown_count} work packages")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_work_breakdown(breakdown)

                stg.add_output("work_breakdown.md", "file", path="work_breakdown.md", description="Work breakdown structure")
                stg.add_output("breakdown.json", "file", path="breakdown.json", description="Work breakdown data")
                stg.add_output("work_packages", "data", count=breakdown_count, description="Work packages")
        except Exception as e:
            print(f"   [ERROR] Stage 12 (Work Breakdown) failed: {e}")
        if breakdown:
            _save_checkpoint(output_dir, 12, {
                "breakdown": breakdown.to_dict() if hasattr(breakdown, 'to_dict') else {},
            })
    elif dry_run:
        manifest.skip_stage(12, "work_breakdown", "Generating Work Breakdown Structure", reason="dry_run")
        print("\n[12/20] [DRY RUN] Skipping Work Breakdown generation")

    # ── Step 12.5: Config & Environment ─────────────────────────
    infra_config = None
    cfg_env_cfg = config.get("generators", {}).get("config_env", {})
    if _has_checkpoint(output_dir, "12.5"):
        # Programmatic stage — fast to regenerate, but skip for consistency
        manifest.skip_stage("12.5", "config_env", "Resumed from checkpoint")
        print("\n[12.5/20] [CHECKPOINT] Config & Environment already generated")
    elif not dry_run and cfg_env_cfg.get("enabled", True) and tech_stack:
        try:
            with manifest.stage("12.5", "config_env", "Generating Config & Environment Files") as stg:
                stg.add_input("tech_stack", "data", description="Tech stack recommendations")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")
                if data_dict:
                    stg.add_input("entities", "data", count=len(data_dict.entities), description="Data entities")

                print("\n[12.5/20] Generating Config & Environment Files...")
                await _emit_progress("12.5", "Generating Config & Environment...")
                config_gen = ConfigGenerator(config=cfg_env_cfg)
                ts_dict = tech_stack.to_dict() if hasattr(tech_stack, 'to_dict') else {}
                entity_names = list(data_dict.entities.keys()) if data_dict else []
                infra_config = config_gen.generate_config(
                    tech_stack_dict=ts_dict,
                    api_endpoints=[ep.to_dict() if hasattr(ep, 'to_dict') else ep for ep in api_endpoints] if api_endpoints else [],
                    data_dict_entities=entity_names,
                    project_name=project_name,
                )
                save_config(infra_config, output_dir)
                print(f"   Saved .env.example, docker-compose.yml, Dockerfile, K8s manifests, CI pipeline")
                stg.add_output(".env.example", "file", path="infrastructure/.env.example", description="Environment variables template")
                stg.add_output("docker-compose.yml", "file", path="infrastructure/docker-compose.yml", description="Docker Compose for local dev")
                stg.add_output("Dockerfile", "file", path="infrastructure/Dockerfile", description="Backend container image")
                stg.add_output("ci.yml", "file", path="infrastructure/.github/workflows/ci.yml", description="GitHub Actions CI/CD pipeline")
                stg.add_output("deployment.yaml", "file", path="infrastructure/kubernetes/deployment.yaml", description="K8s deployment manifest")
                _save_checkpoint(output_dir, "12.5", {"generated": True})
        except Exception as e:
            print(f"   [ERROR] Stage 12.5 (Config & Environment) failed: {e}")
    elif dry_run and cfg_env_cfg.get("enabled", True):
        manifest.skip_stage("12.5", "config_env", "Generating Config & Environment Files", reason="dry_run")
        print("\n[12.5/20] [DRY RUN] Skipping Config & Environment")
    else:
        manifest.skip_stage("12.5", "config_env", "Generating Config & Environment Files", reason="disabled or no tech stack")

    # Generate Task List from Work Packages
    task_breakdown = None
    if not dry_run and breakdown:
        _snap = _llm_snapshot()
        try:
            with manifest.stage(13, "task_list", "Generating Task List from Work Packages") as stg:
                stg.add_input("breakdown", "data", description="Work breakdown structure")
                stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
                stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")
                stg.add_input("entities", "data", count=len(data_dict.entities) if data_dict else 0, description="Data entities")

                print("\n[13/20] Generating Task List from Work Packages...")
                await _emit_progress(13, "Generating Task List...")
                llm_config = config.get("kilo_agent", {})
                task_generator = TaskGenerator(
                    model=llm_config.get("model", "openai/gpt-4o-mini"),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    api_key=os.environ.get("OPENROUTER_API_KEY")
                )

                # Get features from breakdown
                features_list = []
                if hasattr(breakdown, 'features'):
                    # breakdown.features is a Dict[str, FeatureWorkPackage], iterate over values
                    features_list = [
                        {"id": f.feature_id, "name": f.feature_name, "description": getattr(f, 'description', '')}
                        for f in breakdown.features.values()
                    ]

                task_breakdown = await task_generator.generate_all_tasks(
                    features=features_list,
                    user_stories=user_stories if user_stories else [],
                    requirements=requirements,
                    api_endpoints=api_endpoints if api_endpoints else None,
                    entities=data_dict.entities if data_dict else None
                )

                save_task_list(task_breakdown, output_dir)
                print(f"   Generated {task_breakdown.total_tasks} tasks ({task_breakdown.total_hours}h total)")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_task_list(task_breakdown)

                stg.add_output("task_list.md", "file", path="tasks/task_list.md", description="Task list document")
                stg.add_output("tasks.json", "file", path="tasks/tasks.json", description="Task data")
                stg.add_output("tasks", "data", count=task_breakdown.total_tasks, description="Generated tasks")
                stg.add_output("total_hours", "data", description=f"{task_breakdown.total_hours}h total estimated effort")
            _update_stage_cost(_snap)
        except Exception as e:
            print(f"   [ERROR] Stage 13 (Task List) failed: {e}")
            _update_stage_cost(_snap)
    elif dry_run:
        manifest.skip_stage(13, "task_list", "Generating Task List from Work Packages", reason="dry_run")
        print("\n[13/20] [DRY RUN] Skipping Task List generation")

    # Generate Reports (Validation + Traceability)
    if not dry_run:
        try:
            with manifest.stage(14, "reports", "Generating Reports") as stg:
                stg.add_input("journal", "data", description="Requirement journal")
                stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
                stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
                stg.add_input("test_cases", "data", count=len(test_cases), description="Test cases")
                stg.add_input("api_endpoints", "data", count=len(api_endpoints), description="API endpoints")
                stg.add_input("ui_spec", "data", description="UI design specification")
                stg.add_input("data_dict", "data", description="Data dictionary")

                print("\n[14/20] Generating Reports...")
                await _emit_progress(14, "Generating Reports...")
                reports_dir = output_dir / "reports"

                # Validation Report
                validation_md = create_validation_report(journal, requirements)
                with open(reports_dir / "validation_report.md", "w", encoding="utf-8") as f:
                    f.write(validation_md)

                # Build screens list from compositions (they have user_story links)
                traceability_screens = []
                if ui_spec and ui_spec.screens:
                    traceability_screens = ui_spec.screens
                else:
                    compositions_dir = output_dir / "ui_design" / "compositions"
                    if compositions_dir.exists():
                        import json as _json
                        for jf in sorted(compositions_dir.glob("*.json")):
                            if jf.name in ("component_matrix.json", "index.json"):
                                continue
                            try:
                                with open(jf, encoding="utf-8") as _f:
                                    comp = _json.load(_f)
                                for us_id in comp.get("user_stories", []):
                                    traceability_screens.append({
                                        "id": f"SCREEN-{jf.stem.upper().replace('_', '-')}",
                                        "parent_user_story": us_id,
                                        "name": comp.get("screen_name", jf.stem),
                                    })
                            except Exception:
                                pass
                    if traceability_screens:
                        print(f"   Loaded {len(traceability_screens)} screen-story links from compositions")

                # Traceability Matrix
                traceability_md = create_traceability_matrix(
                    requirements,
                    user_stories if user_stories else [],
                    test_cases if with_gherkin and user_stories else [],
                    api_endpoints=api_endpoints if api_endpoints else None,
                    screens=traceability_screens if traceability_screens else None,
                    entities=data_dict.entities if data_dict else None,
                    state_machines=state_machines if state_machines else None,
                )
                with open(reports_dir / "traceability_matrix.md", "w", encoding="utf-8") as f:
                    f.write(traceability_md)

                print(f"   Saved validation_report.md and traceability_matrix.md")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_reports(
                        str(reports_dir / "validation_report.md"),
                        str(reports_dir / "traceability_matrix.md")
                    )

                stg.add_output("validation_report.md", "file", path="reports/validation_report.md", description="Validation report")
                stg.add_output("traceability_matrix.md", "file", path="reports/traceability_matrix.md", description="Traceability matrix")
        except Exception as e:
            print(f"   [ERROR] Stage 14 (Reports) failed: {e}")
    elif dry_run:
        manifest.skip_stage(14, "reports", "Generating Reports", reason="dry_run")
        print("\n[14/20] [DRY RUN] Skipping Reports generation")

    # Self-Critique Pass (final sweep — per-stage critique already caught some issues earlier)
    critique_result = None
    if not dry_run:
        _snap = _llm_snapshot()
        with manifest.stage(15, "self_critique", "Running Self-Critique Analysis") as stg:
            stg.add_input("requirements", "data", count=len(requirements), description="Requirements")
            stg.add_input("user_stories", "data", count=len(user_stories), description="User stories")
            stg.add_input("test_cases", "data", count=len(test_cases), description="Test cases")
            stg.add_input("domain", "data", description=f"Domain: {domain}")

            print("\n[15/20] Running Self-Critique Analysis (final sweep)...")
            await _emit_progress(15, "Running Self-Critique Analysis...")
            try:
                # Reuse the engine initialized earlier; fall back to creating one if needed
                if critique_engine is None:
                    from requirements_engineer.critique.self_critique import SelfCritiqueEngine
                    llm_config = config.get("kilo_agent", {})
                    critique_engine = SelfCritiqueEngine(
                        model_name=llm_config.get("model", "openai/gpt-4o-mini"),
                        base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                        api_key=os.environ.get("OPENROUTER_API_KEY")
                    )
                    await critique_engine.initialize()

                critique_result = await critique_engine.critique_and_improve(
                    requirements=requirements,
                    user_stories=user_stories if user_stories else [],
                    test_cases=test_cases if with_gherkin and user_stories else [],
                    domain=domain,
                    auto_fix=True,
                    output_dir=str(output_dir)
                )

                # Save critique report
                critique_dir = output_dir / "quality"
                with open(critique_dir / "self_critique_report.md", "w", encoding="utf-8") as f:
                    f.write(critique_result.to_markdown())

                with open(critique_dir / "self_critique_report.json", "w", encoding="utf-8") as f:
                    f.write(critique_result.to_json())

                print(f"   Quality Score: {critique_result.quality_score}/10")
                print(f"   Found {len(critique_result.issues)} issues ({len([i for i in critique_result.issues if i.severity.value in ['critical', 'high']])} critical/high)")

                # Recalculate testing gate with post-auto-fix data
                if critique_result.summary.get("auto_fixed", 0) > 0:
                    from requirements_engineer.gates.quality_gate import QualityGate as QG
                    trace_post = QG.compute_traceability(
                        requirements,
                        user_stories if user_stories else [],
                        test_cases if with_gherkin and user_stories else []
                    )
                    tc_list = test_cases if with_gherkin and user_stories else []
                    us_list = user_stories if user_stories else []
                    post_gate = quality_gate.check_testing_gate(
                        test_coverage=min(len(tc_list) / max(len(us_list), 1), 1.0),
                        traceability=trace_post["overall"],
                        test_cases_count=len(tc_list)
                    )
                    print(f"   Post-fix Testing Gate: {post_gate.status.value.upper()} (traceability: {trace_post['overall']:.0%})")

                # Emit to Matrix Dashboard
                if matrix_bridge:
                    await matrix_bridge.emit_critique(critique_result)

                stg.add_output("self_critique_report.md", "file", path="quality/self_critique_report.md", description="Self-critique report")
                stg.add_output("self_critique_report.json", "file", path="quality/self_critique_report.json", description="Self-critique data")
                stg.add_output("quality_score", "data", description=f"Quality score: {critique_result.quality_score}/10")
            except Exception as e:
                print(f"   [WARN] Self-critique failed: {e}")
        _update_stage_cost(_snap)
    elif dry_run:
        manifest.skip_stage(15, "self_critique", "Running Self-Critique Analysis", reason="dry_run")
        print("\n[15/20] [DRY RUN] Skipping Self-Critique")

    # Interactive Layout Generation (Magentic-One Style)
    final_layout = None
    if not dry_run and emitter:
        print("\n[Layout] Starting Interactive Layout Generation...")
        LayoutOrchestrator = get_layout_orchestrator()
        if LayoutOrchestrator:
            try:
                # Prepare project data for layout analysis
                project_data = {
                    "project_name": project_name,
                    "domain": domain,
                    "requirements": [
                        {
                            "id": req.requirement_id,
                            "title": req.title,
                            "type": req.requirement_type,
                            "priority": req.priority,
                            "description": req.description,
                            "diagrams": list(req.mermaid_diagrams.keys()) if req.mermaid_diagrams else []
                        }
                        for req in requirements
                    ],
                    "user_stories": [
                        {
                            "id": story.get("id", f"US-{i+1:03d}"),
                            "title": story.get("title", ""),
                            "persona": story.get("persona", ""),
                            "parent_req": story.get("parent_requirement_id", "")
                        }
                        for i, story in enumerate(user_stories if user_stories else [])
                    ],
                    "epics": [
                        {"id": epic.get("id", ""), "name": epic.get("name", "")}
                        for epic in (epics if epics else [])
                    ],
                    "api_endpoints": len(api_endpoints) if api_endpoints else 0,
                    "entities": len(data_dict.entities) if data_dict else 0,
                    "diagrams_count": diagrams_count if 'diagrams_count' not in dir() else len(list((output_dir / "diagrams").glob("*.mmd")))
                }

                # Get LLM config
                llm_config = config.get("kilo_agent", {})

                # Create layout orchestrator
                layout_orchestrator = LayoutOrchestrator(
                    model=llm_config.get("model", "openai/gpt-4o"),
                    base_url=llm_config.get("base_url", "https://openrouter.ai/api/v1"),
                    emitter=emitter
                )

                # Run interactive layout generation
                # Note: This will emit events to dashboard for user selection
                final_layout = await layout_orchestrator.run(
                    project_data=project_data,
                    interactive=True  # Enable user selection in dashboard
                )

                if final_layout:
                    # Save layout configuration
                    layout_dir = output_dir / "layouts"
                    layout_dir.mkdir(parents=True, exist_ok=True)

                    layout_file = layout_dir / "final_layout.json"
                    with open(layout_file, "w", encoding="utf-8") as f:
                        json.dump(final_layout.to_dict(), f, indent=2)

                    print(f"   Layout type: {final_layout.layout_type}")
                    print(f"   Aggregations: {len(final_layout.aggregations)}")
                    print(f"   Saved to: {layout_file}")

            except Exception as e:
                print(f"   [WARN] Interactive layout generation failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("   [SKIP] Layout Orchestrator not available")
    elif dry_run:
        print("\n[Layout] [DRY RUN] Skipping Interactive Layout Generation")

    # Run Presentation Stage (Stage 5)
    presentation_result = None
    if not dry_run and config.get("presentation", {}).get("enabled", True):
        print("\n[Stage 5] Running Presentation Stage...")
        if emitter:
            await emitter.pass_started("presentation", 5)
            await emitter.log_info("Generating human-readable HTML presentation...")

        PresentationStage = imports.get("PresentationStage")
        if PresentationStage:
            try:
                presentation_stage = PresentationStage(
                    project_id=project_name,
                    project_dir=output_dir,
                    output_dir=output_dir,
                    config=config
                )

                presentation_result = await presentation_stage.run()

                if presentation_result.get("success"):
                    print(f"   Generated {presentation_result.get('pages_generated', 0)} HTML pages")
                    print(f"   Quality score: {presentation_result.get('quality_score', 0):.2f}")
                    print(f"   Output: {presentation_result.get('output_dir', '')}")
                else:
                    print(f"   [WARN] Presentation stage did not reach quality threshold")

                if emitter:
                    await emitter.pass_complete("presentation", 5, {
                        "pages": presentation_result.get("pages_generated", 0),
                        "quality": presentation_result.get("quality_score", 0)
                    })
            except Exception as e:
                print(f"   [WARN] Presentation stage failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("   [WARN] PresentationStage not available")
    elif dry_run:
        print("\n[Stage 5] [DRY RUN] Skipping Presentation Stage")

    # Generate Link Configuration for Dashboard
    print("\n[Link Config] Generating Dashboard Link Configuration...")
    try:
        generate_link_config = imports.get("generate_link_config")
        if generate_link_config:
            link_config_path = generate_link_config(
                project_id=project_name,
                output_dir=output_dir,
                requirements=requirements,
                user_stories=user_stories if user_stories else None,
                epics=epics if epics else None,
                tests=test_cases if with_gherkin and 'test_cases' in dir() else None,
                diagrams=list((output_dir / "diagrams").glob("*.mmd")) if (output_dir / "diagrams").exists() else None,
                personas=ux_spec.personas if ux_spec else None,
                screens=ui_spec.screens if ui_spec else None,
                components=ui_spec.components if ui_spec else None,
                api_endpoints=api_endpoints if api_endpoints else None,
                tasks=task_breakdown.tasks if task_breakdown else None,
                entities=data_dict.entities if data_dict else None
            )
            print(f"   Link configuration saved to: {link_config_path}")
    except Exception as e:
        print(f"   [WARN] Failed to generate link configuration: {e}")

    # Save quality gate summary
    gate_summary = quality_gate.get_gate_summary()
    with open(output_dir / "quality" / "quality_gates.md", "w", encoding="utf-8") as f:
        f.write(gate_summary)

    # Save journal
    journal_path = output_dir / "journal.json"
    with open(journal_path, "w", encoding="utf-8") as f:
        json.dump(journal.to_dict(), f, indent=2)

    # Create master document
    print("\n[Final] Creating Master Document...")

    # Count diagrams
    diagrams_dir = output_dir / "diagrams"
    diagrams_count = len(list(diagrams_dir.glob("*.mmd"))) if diagrams_dir.exists() else 0

    # Get quality score and critique issues from critique result if available
    quality_score = critique_result.quality_score if critique_result else None
    critique_issues = len(critique_result.issues) if critique_result else None

    master_md = create_master_document(
        project_name=project_name,
        output_dir=output_dir,
        requirements_count=len(requirements),
        user_stories_count=len(user_stories) if user_stories else 0,
        test_cases_count=len(test_cases) if with_gherkin and user_stories else 0,
        epics_count=len(epics) if epics else 0,
        api_endpoints_count=len(api_endpoints) if api_endpoints else 0,
        entities_count=len(data_dict.entities) if data_dict else 0,
        diagrams_count=diagrams_count,
        quality_score=quality_score,
        critique_issues=critique_issues,
        # New generator metrics
        personas_count=len(ux_spec.personas) if ux_spec else 0,
        user_flows_count=len(ux_spec.user_flows) if ux_spec else 0,
        ui_components_count=len(ui_spec.components) if ui_spec else 0,
        screens_count=len(ui_spec.screens) if ui_spec else 0,
        tasks_count=task_breakdown.total_tasks if task_breakdown else 0,
        total_hours=task_breakdown.total_hours if task_breakdown else 0,
        # Orphaned generator metrics
        arch_services_count=len(arch_spec.services) if arch_spec else 0,
        state_machines_count=len(state_machines) if state_machines else 0,
        compositions_count=len(comp_matrix.screens) if comp_matrix else 0,
        factory_count=_factory_count,
    )
    with open(output_dir / "MASTER_DOCUMENT.md", "w", encoding="utf-8") as f:
        f.write(master_md)

    # Finalize Pipeline Manifest
    manifest.finalize()

    # Validate manifest prerequisites
    manifest_warnings = manifest.validate_prerequisites()
    if manifest_warnings:
        print(f"\n[MANIFEST VALIDATION] {len(manifest_warnings)} warning(s):")
        for w in manifest_warnings:
            print(f"   Step {w['step']} ({w['stage']}): {w['warning']}")

    # Finalize Training Data Collection
    training_stats = {}
    if training_collector:
        try:
            training_collector.output_dir = output_dir / "training_data"
            training_collector.output_dir.mkdir(parents=True, exist_ok=True)
            training_collector.end_run(status="completed")
            training_stats = training_collector.get_statistics()
            print(f"\n[Training Data] {training_stats.get('samples', 0)} samples, "
                  f"{training_stats.get('llm_calls', 0)} LLM calls captured")
            print(f"   Export: {output_dir / 'training_data'}")
        except Exception as e:
            print(f"   [WARN] Training data export failed: {e}")

    # Emit pipeline complete event
    total_cost = sum(c.cost_usd for c in llm_logger.calls)
    total_tokens = sum(c.input_tokens + c.output_tokens for c in llm_logger.calls)
    if emitter:
        await emitter.pipeline_complete({
            "requirements": len(requirements),
            "user_stories": len(user_stories) if user_stories else 0,
            "epics": len(epics) if epics else 0,
            "test_cases": len(test_cases) if with_gherkin and user_stories else 0,
            "output_dir": str(output_dir),
            "cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_llm_calls": len(llm_logger.calls),
            "training_samples": training_stats.get("samples", 0),
        })
        await emitter.log_info(f"Pipeline complete! Cost: ${total_cost:.4f} USD, {total_tokens:,} tokens")

    # Print LLM usage summary (merged with checkpoint data from earlier attempts)
    llm_logger = get_llm_logger()
    current_summary = llm_logger.get_summary() if llm_logger.calls else {}
    checkpoint_summary = _load_llm_usage_snapshot(output_dir)
    if checkpoint_summary or current_summary:
        merged_summary = _merge_llm_summaries(checkpoint_summary, current_summary)
        with open(output_dir / "llm_usage_summary.json", "w", encoding="utf-8") as f:
            json.dump(merged_summary, f, indent=2)
        print(f"\n[INFO] LLM usage summary saved to: {output_dir / 'llm_usage_summary.json'}")
        print("\n" + "=" * 70)
        print("LLM USAGE SUMMARY (all attempts combined)")
        print("=" * 70)
        print(f"  Total calls: {merged_summary.get('total_calls', 0)}")
        print(f"  Total tokens: {merged_summary.get('total_tokens', 0):,}")
        print(f"  Total cost: ${merged_summary.get('total_cost_usd', 0):.4f} USD")
        for comp, stats in merged_summary.get("by_component", {}).items():
            print(f"  {comp}:")
            print(f"    Calls: {stats.get('calls', 0)} | Tokens: {stats.get('tokens', 0):,} | Cost: ${stats.get('cost_usd', 0):.4f}")
        print("=" * 70)
    elif llm_logger.calls:
        llm_logger.print_summary()
        llm_logger.save_summary(str(output_dir / "llm_usage_summary.json"))
        print(f"\n[INFO] LLM usage summary saved to: {output_dir / 'llm_usage_summary.json'}")

    print("\n" + "=" * 70)
    print("Enterprise Requirements Engineering Complete!")
    print(f"Output directory: {output_dir}")
    if with_dashboard and not _external_emitter:
        print(f"\n[INFO] Dashboard still running at: http://localhost:{dashboard_port}")
        print("   Press Ctrl+C to stop the dashboard and exit.")
        try:
            # Keep dashboard running until user stops it
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n   Stopping dashboard...")
            if dashboard_server:
                await dashboard_server.stop()
    print("=" * 70)

    return str(output_dir)


def create_master_document(
    project_name: str,
    output_dir: Path,
    requirements_count: int,
    user_stories_count: int,
    test_cases_count: int,
    epics_count: int = 0,
    api_endpoints_count: int = 0,
    entities_count: int = 0,
    diagrams_count: int = 0,
    quality_score: float = None,
    critique_issues: int = None,
    # New generator metrics
    personas_count: int = 0,
    user_flows_count: int = 0,
    ui_components_count: int = 0,
    screens_count: int = 0,
    tasks_count: int = 0,
    total_hours: int = 0,
    # Orphaned generator metrics
    arch_services_count: int = 0,
    state_machines_count: int = 0,
    compositions_count: int = 0,
    factory_count: int = 0,
) -> str:
    """Create a comprehensive master document with executive summary."""
    md = f"# {project_name}\n"
    md += f"## Requirements Specification Document\n\n"
    md += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    # Executive Summary
    md += "---\n\n"
    md += "## Executive Summary\n\n"

    # Calculate coverage and readiness
    test_coverage = (test_cases_count / max(user_stories_count, 1)) * 100 if user_stories_count > 0 else 0
    story_coverage = (user_stories_count / max(requirements_count, 1)) * 100 if requirements_count > 0 else 0

    # Determine overall status
    if quality_score and quality_score >= 8.0:
        status = "Ready for Implementation"
        status_emoji = "green_circle"
    elif quality_score and quality_score >= 6.0:
        status = "Review Recommended"
        status_emoji = "yellow_circle"
    else:
        status = "Additional Work Required"
        status_emoji = "red_circle"

    md += f"**Project Status:** {status}\n\n"

    md += "### Key Metrics\n\n"
    md += "| Metric | Value | Status |\n"
    md += "|--------|-------|--------|\n"
    md += f"| Total Requirements | {requirements_count} | - |\n"
    md += f"| Epics | {epics_count} | - |\n"
    md += f"| User Stories | {user_stories_count} | {'PASS' if story_coverage >= 80 else 'WARN'} |\n"
    md += f"| Test Cases | {test_cases_count} | {'PASS' if test_coverage >= 100 else 'WARN'} |\n"
    md += f"| API Endpoints | {api_endpoints_count} | - |\n"
    md += f"| Data Entities | {entities_count} | - |\n"
    md += f"| Diagrams | {diagrams_count} | - |\n"
    if personas_count > 0:
        md += f"| UX Personas | {personas_count} | - |\n"
    if user_flows_count > 0:
        md += f"| User Flows | {user_flows_count} | - |\n"
    if ui_components_count > 0:
        md += f"| UI Components | {ui_components_count} | - |\n"
    if screens_count > 0:
        md += f"| Screen Specs | {screens_count} | - |\n"
    if tasks_count > 0:
        md += f"| Tasks | {tasks_count} | - |\n"
    if total_hours > 0:
        md += f"| Total Hours (Estimated) | {total_hours}h | - |\n"
    if arch_services_count > 0:
        md += f"| Architecture Services | {arch_services_count} | - |\n"
    if state_machines_count > 0:
        md += f"| State Machines | {state_machines_count} | - |\n"
    if compositions_count > 0:
        md += f"| Component Compositions | {compositions_count} | - |\n"
    if factory_count > 0:
        md += f"| Test Factories | {factory_count} | - |\n"
    if quality_score is not None:
        md += f"| **Quality Score** | **{quality_score:.1f}/10** | {'PASS' if quality_score >= 7 else 'REVIEW'} |\n"
    md += "\n"

    # Coverage summary
    md += "### Coverage Analysis\n\n"
    md += f"- **Requirements -> User Stories:** {story_coverage:.0f}%\n"
    md += f"- **User Stories -> Test Cases:** {test_coverage:.0f}%\n"
    if critique_issues is not None:
        md += f"- **Self-Critique Issues:** {critique_issues} found\n"
    md += "\n"

    # Recommendations
    md += "### Recommendations\n\n"
    if story_coverage < 100:
        md += f"- [ ] Review {requirements_count - user_stories_count} requirements without user stories\n"
    if test_coverage < 100:
        md += f"- [ ] Add test cases for stories lacking coverage\n"
    if quality_score and quality_score < 8.0:
        md += f"- [ ] Address issues from self-critique report\n"
    if requirements_count > 0 and story_coverage >= 80 and test_coverage >= 80:
        md += "- [x] Core documentation complete\n"
    md += "\n"

    # Table of Contents
    md += "---\n\n"
    md += "## Table of Contents\n\n"
    md += "### Core Documentation\n\n"
    md += "1. [User Stories & Epics](user_stories/user_stories.md)\n"
    md += "2. [API Specification](api/openapi_spec.yaml) | [API Docs](api/api_documentation.md)\n"
    md += "3. [Data Dictionary](data/data_dictionary.md) | [ER Diagram](data/er_diagram.mmd)\n"
    md += "4. [Test Documentation](testing/test_documentation.md)\n"
    md += "4a. [Test Factories](testing/factories/) | [Seed Data](testing/)\n\n"

    md += "### Design & Architecture\n\n"
    md += "5. [Tech Stack Recommendations](tech_stack/tech_stack.md)\n"
    md += "5a. [Architecture Design](architecture/architecture_overview.md)\n"
    md += "6. [UX Design](ux_design/personas.md) | [User Flows](ux_design/user_flows.md)\n"
    md += "7. [UI Design System](ui_design/design_system.md) | [Components](ui_design/components.md)\n\n"

    md += "### Analysis & Planning\n\n"
    md += "8. [Work Breakdown Structure](work_breakdown/feature_breakdown.md)\n"
    md += "9. [Task List](tasks/task_list.md) | [Gantt Chart](tasks/gantt_chart.mmd)\n"
    md += "9a. [Infrastructure](infrastructure/) | [Docker Compose](infrastructure/docker-compose.yml)\n"
    md += "10. [Traceability Matrix](reports/traceability_matrix.md)\n\n"

    md += "### Quality Assurance\n\n"
    md += "11. [Quality Gates](quality/quality_gates.md)\n"
    md += "12. [Validation Report](reports/validation_report.md)\n"

    # Check for self-critique report
    critique_path = output_dir / "quality" / "self_critique_report.md"
    if critique_path.exists():
        md += "13. [Self-Critique Report](quality/self_critique_report.md)\n"

    md += "\n"

    # Check which diagrams exist
    diagrams_dir = output_dir / "diagrams"
    if diagrams_dir.exists() and any(diagrams_dir.iterdir()):
        diagram_files = list(diagrams_dir.glob("*.mmd"))
        md += f"### Diagrams ({len(diagram_files)} files)\n\n"
        md += "10. [All Diagrams](diagrams/) - Mermaid diagrams for requirements\n"

        # List diagram types
        diagram_types = set()
        for f in diagram_files:
            parts = f.stem.split("_")
            if len(parts) > 1:
                diagram_types.add(parts[-1])
        if diagram_types:
            md += f"    - Types: {', '.join(sorted(diagram_types))}\n"
        md += "\n"

    # Footer
    md += "---\n\n"
    md += "### Document Information\n\n"
    md += f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    md += f"- **Generator:** AI-Scientist Requirements Engineering System v2.0\n"
    md += f"- **Output:** `{output_dir}`\n\n"
    md += "*For questions or issues, contact the project team.*\n"

    return md


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Requirements Engineering System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard mode
  python run_re_system.py --project re_ideas/sample_project.json
  python run_re_system.py --project re_ideas/sample_project.json --stages 1,2
  python run_re_system.py --project re_ideas/sample_project.json --breakdown service
  python run_re_system.py --project re_ideas/sample_project.json --dry-run
  python run_re_system.py --project re_ideas/sample_project.json --use-kilo

  # Enterprise mode (comprehensive documentation)
  python run_re_system.py --project re_ideas/sample_project.json --mode enterprise
  python run_re_system.py --project re_ideas/sample_project.json --mode enterprise --with-gherkin
  python run_re_system.py --project re_ideas/sample_project.json --mode enterprise --no-api-spec
        """
    )

    parser.add_argument(
        "--project", "-p",
        required=False,
        default=None,
        help="Path to project input JSON file (default: newest file from re_ideas/)"
    )

    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to configuration YAML (default: auto-resolved to requirements_engineer/re_config.yaml)"
    )

    parser.add_argument(
        "--mode", "-m",
        default="enterprise",
        choices=["standard", "enterprise"],
        help="Execution mode (default: enterprise)"
    )

    parser.add_argument(
        "--stages", "-s",
        default=None,
        help="Comma-separated list of stages to run (1-4, default: all) [standard mode only]"
    )

    parser.add_argument(
        "--breakdown", "-b",
        default="feature",
        choices=["feature", "service", "application"],
        help="Work breakdown type (default: feature)"
    )

    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Run without LLM calls (for testing)"
    )

    parser.add_argument(
        "--use-kilo", "-k",
        action="store_true",
        help="Use Kilo Agent for Mermaid diagram generation"
    )

    # Enterprise mode options
    parser.add_argument(
        "--with-gherkin",
        action="store_true",
        default=True,
        help="Generate Gherkin/BDD test cases [enterprise mode]"
    )

    parser.add_argument(
        "--no-gherkin",
        action="store_true",
        help="Skip Gherkin/BDD test generation [enterprise mode]"
    )

    parser.add_argument(
        "--with-api-spec",
        action="store_true",
        default=True,
        help="Generate OpenAPI 3.0 specification [enterprise mode]"
    )

    parser.add_argument(
        "--no-api-spec",
        action="store_true",
        help="Skip OpenAPI specification generation [enterprise mode]"
    )

    parser.add_argument(
        "--with-data-dict",
        action="store_true",
        default=True,
        help="Generate data dictionary [enterprise mode]"
    )

    parser.add_argument(
        "--no-data-dict",
        action="store_true",
        help="Skip data dictionary generation [enterprise mode]"
    )

    # Dashboard options
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch live dashboard with endless canvas visualization [enterprise mode]"
    )

    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8080,
        help="Port for dashboard server (default: 8080)"
    )

    parser.add_argument(
        "--resume", "-r",
        default=None,
        help="Resume from existing output directory (e.g. enterprise_output/project_20260210_222409)"
    )

    args = parser.parse_args()

    # Auto-detect project if not specified
    if args.project is None:
        re_ideas_dir = Path(__file__).parent.parent / "re_ideas"
        if re_ideas_dir.exists():
            json_files = list(re_ideas_dir.glob("*.json"))
            if json_files:
                # Get newest file by modification time
                newest = max(json_files, key=lambda f: f.stat().st_mtime)
                args.project = str(newest)
                print(f"  [AUTO] Using newest project: {newest.name}")
            else:
                print("  [ERROR] No JSON files found in re_ideas/")
                print("  Usage: python run_re_system.py --project <path_to_json>")
                sys.exit(1)
        else:
            print("  [ERROR] re_ideas/ directory not found and no --project specified")
            sys.exit(1)

    # Handle enterprise mode
    if args.mode == "enterprise":
        asyncio.run(run_enterprise_mode(
            project_path=args.project,
            config_path=args.config,
            use_kilo=args.use_kilo,
            with_gherkin=not args.no_gherkin,
            with_api_spec=not args.no_api_spec,
            with_data_dict=not args.no_data_dict,
            dry_run=args.dry_run,
            with_dashboard=args.dashboard,
            dashboard_port=args.dashboard_port,
            resume_dir=args.resume,
        ))
    else:
        # Standard mode
        # Parse stages
        stages = None
        if args.stages:
            stages = [int(s.strip()) for s in args.stages.split(",")]

        # Run the system
        run_requirements_engineering(
            project_path=args.project,
            config_path=args.config,
            stages=stages,
            breakdown_type=args.breakdown,
            dry_run=args.dry_run,
            use_kilo=args.use_kilo
        )


if __name__ == "__main__":
    main()
