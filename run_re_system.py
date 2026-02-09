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
sys.path.insert(0, str(Path(__file__).parent))

from requirements_engineer.core.re_journal import (
    RequirementNode,
    RequirementJournal
)
from requirements_engineer.core.re_metrics import MetricsManager
from requirements_engineer.core.llm_logger import get_llm_logger, LLMLogger
from requirements_engineer.core.re_agent_manager import REAgentManager
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


def load_config(config_path: str = "re_config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
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
            return json.load(f)


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
    config_path: str = "re_config.yaml",
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
    config_path: str = "re_config.yaml",
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

            print(f"    {req.requirement_id}: {req.title[:30]}... → {req_diagram_types}")
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
        print(f"  Reduction: {would_have_generated} → {total_generated} ({100 * (1 - total_generated / would_have_generated):.0f}% fewer)")
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

    Returns:
        Markdown string with traceability matrix
    """
    api_endpoints = api_endpoints or []
    screens = screens or []
    entity_list = list(entities.values()) if isinstance(entities, dict) else (entities or [])

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

        # Entities linked to this requirement (via API paths)
        ent_names = req_to_entity.get(req_id, set())
        ent_str = ', '.join(sorted(ent_names)[:3]) if ent_names else '-'
        if len(ent_names) > 3:
            ent_str += f" (+{len(ent_names) - 3})"

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
    config_path: str = "re_config.yaml",
    use_kilo: bool = True,
    with_gherkin: bool = True,
    with_api_spec: bool = True,
    with_data_dict: bool = True,
    dry_run: bool = False,
    with_dashboard: bool = False,
    dashboard_port: int = 8080
) -> None:
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

    # Dashboard setup
    dashboard_server = None
    emitter = None

    # Matrix Event Bridge for consistent metadata visualization
    matrix_bridge = None

    if with_dashboard:
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

            # Initialize Matrix Event Bridge for structured visualization
            try:
                from requirements_engineer.dashboard.matrix_event_bridge import MatrixEventBridge
                matrix_bridge = MatrixEventBridge(emitter)
                print("   Matrix Event Bridge initialized")
            except ImportError as e:
                print(f"   [WARN] Matrix Event Bridge not available: {e}")

            # Give browser time to open
            await asyncio.sleep(1)

    print("=" * 70)
    print("Requirements Engineering System - ENTERPRISE MODE")
    if with_dashboard:
        print(f"(Live Dashboard: http://localhost:{dashboard_port})")
    print("=" * 70)

    # Load configuration and project
    print("\n[1/15] Loading configuration...")
    config = load_config(config_path)
    project = await load_project_async(project_path)

    project_name = project.get("Name", "unnamed_project")
    domain = project.get("Domain", "custom")
    context = project.get("Context", {})
    stakeholders = project.get("Stakeholders", [])
    constraints = project.get("Constraints", {})

    # Emit pipeline started event
    if emitter:
        await emitter.pipeline_started(project_name, "enterprise")

    print(f"   Project: {project_name}")
    print(f"   Domain: {domain}")

    # Create output directory with enterprise structure
    output_dir = create_output_directory(project_name, "enterprise_output")
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

    # Initialize components
    print("\n[2/15] Initializing journal and metrics...")
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

    # Create sample requirements (or run discovery stage)
    print("\n[3/15] Running Discovery Pass...")
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

    if emitter:
        await emitter.pass_complete("discovery", 1, {"requirements": len(requirements)})

    # Quality Gate: Discovery → Analysis
    avg_completeness = sum(
        getattr(r, 'completeness_score', 0.85) for r in requirements
    ) / max(len(requirements), 1)
    gate_result = quality_gate.check_discovery_gate(
        requirements_count=len(requirements),
        stakeholder_coverage=0.9,  # No stakeholder data available yet
        completeness=min(avg_completeness, 1.0)
    )
    print(f"   Quality Gate: {gate_result.status.value.upper()}")

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

    # Generate User Stories
    user_stories = []
    epics = []
    if not dry_run:
        print("\n[4/15] Generating User Stories...")
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
        print(f"   Generated {len(epics)} epics, {len(user_stories)} user stories")
    else:
        print("\n[4/15] [DRY RUN] Skipping User Stories generation")

    # Quality Gate: Analysis → Specification
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

    # Per-stage critique: consistency + orphan requirement fix
    if critique_engine and not dry_run and user_stories:
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

    # Generate API Specification
    api_spec_yaml = ""
    api_endpoints = []  # Track API endpoints for metrics
    if with_api_spec and not dry_run:
        print("\n[5/15] Generating API Specification...")
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
    elif dry_run:
        print("\n[5/15] [DRY RUN] Skipping API Specification")
    else:
        print("\n[5/15] Skipping API Specification (disabled)")

    # Generate Realtime/WebSocket Spec (AsyncAPI) - runs after API spec
    realtime_spec_yaml = ""
    rt_config = config.get("generators", {}).get("realtime_spec", {})
    if rt_config.get("enabled", True) and with_api_spec and not dry_run:
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
            else:
                print("   No real-time requirements found, skipping AsyncAPI")
        except Exception as e:
            print(f"   [WARN] Realtime spec generation failed: {e}")

    # Generate Data Dictionary
    data_dict = None  # Track data dictionary for metrics
    if with_data_dict and not dry_run:
        print("\n[6/15] Generating Data Dictionary...")
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

        print(f"   Generated dictionary with {len(data_dict.entities)} entities")

        # Emit to Matrix Dashboard
        if matrix_bridge:
            await matrix_bridge.emit_data_dictionary(data_dict)
    elif dry_run:
        print("\n[6/15] [DRY RUN] Skipping Data Dictionary")
    else:
        print("\n[6/15] Skipping Data Dictionary (disabled)")

    # Generate Tech Stack
    tech_stack = None
    if not dry_run:
        print("\n[7/15] Generating Tech Stack Recommendations...")
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
    elif dry_run:
        print("\n[7/15] [DRY RUN] Skipping Tech Stack generation")

    # Generate Gherkin Test Cases
    test_cases = []
    if with_gherkin and user_stories and not dry_run:
        print("\n[8/15] Generating Gherkin Test Cases...")
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

        print(f"   Generated {len(features)} feature files, {len(test_cases)} test cases")

        if emitter:
            await emitter.pass_complete("testing", 4, {
                "features": len(features),
                "test_cases": len(test_cases)
            })

        # Quality Gate: Testing → Final (real traceability from artifact links)
        from requirements_engineer.gates.quality_gate import QualityGate as QG
        trace = QG.compute_traceability(requirements, user_stories, test_cases)
        gate_result = quality_gate.check_testing_gate(
            test_coverage=min(len(test_cases) / max(len(user_stories), 1), 1.0),
            traceability=trace["overall"],
            test_cases_count=len(test_cases)
        )
        print(f"   Quality Gate: {gate_result.status.value.upper()}")
        print(f"   Traceability: req→story={trace['req_to_story']:.0%}, story→test={trace['story_to_test']:.0%}")

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
                    print(f"   Post-fix traceability: req→story={trace_post['req_to_story']:.0%}, story→test={trace_post['story_to_test']:.0%}")
                elif stage_critique["issues_found"] > 0:
                    print(f"   Critique: {stage_critique['issues_found']} issues found (no auto-fixes applicable)")
            except Exception as e:
                print(f"   [WARN] Validation critique failed: {e}")

    elif dry_run:
        print("\n[8/15] [DRY RUN] Skipping Gherkin Test Cases")
    else:
        print("\n[8/15] Skipping Gherkin Test Cases (disabled or no user stories)")

    # ── Step 8.5: Iterative Trace Refinement ─────────────────────
    treesearch_cfg = config.get("treesearch", {})
    if not dry_run and treesearch_cfg.get("enabled", False) and epics and requirements:
        print("\n[8.5/15] Running Iterative Trace Refinement...")
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
        except Exception as e:
            print(f"   [WARN] Trace refinement failed: {e}")
    elif dry_run and treesearch_cfg.get("enabled", False):
        print("\n[8.5/15] [DRY RUN] Skipping Iterative Trace Refinement")

    # Generate UX Design
    ux_spec = None
    if not dry_run:
        print("\n[9/15] Generating UX Design Artifacts...")
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
    elif dry_run:
        print("\n[9/15] [DRY RUN] Skipping UX Design generation")

    # Generate UI Design
    ui_spec = None
    if not dry_run:
        print("\n[10/15] Generating UI Design Specifications...")
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
    elif dry_run:
        print("\n[10/15] [DRY RUN] Skipping UI Design generation")

    # Generate Mermaid diagrams
    if not dry_run:
        if use_kilo:
            print("\n[11/15] Generating Mermaid Diagrams (Kilo Agent)...")
            await generate_diagrams_with_kilo(journal, config, output_dir)
        else:
            print("\n[11/15] Generating Mermaid Diagrams (LLM)...")
            await generate_diagrams_simple(journal, config, output_dir)

        # Emit to Matrix Dashboard
        if matrix_bridge:
            await matrix_bridge.emit_diagrams(journal)
    elif dry_run:
        print("\n[11/15] [DRY RUN] Skipping Mermaid Diagram generation")

    # Generate Work Breakdown Structure
    breakdown_type = "feature"  # Default to feature breakdown
    breakdown = None
    if not dry_run:
        print(f"\n[12/15] Generating Work Breakdown Structure ({breakdown_type})...")
        breakdown = _create_breakdown(breakdown_type, journal)
        save_work_breakdown(breakdown, output_dir, breakdown_type)
        breakdown_count = len(breakdown.features) if hasattr(breakdown, 'features') else len(breakdown.services) if hasattr(breakdown, 'services') else len(breakdown.applications)
        print(f"   Generated {breakdown_count} work packages")

        # Emit to Matrix Dashboard
        if matrix_bridge:
            await matrix_bridge.emit_work_breakdown(breakdown)
    elif dry_run:
        print("\n[12/15] [DRY RUN] Skipping Work Breakdown generation")

    # Generate Task List from Work Packages
    task_breakdown = None
    if not dry_run and breakdown:
        print("\n[13/15] Generating Task List from Work Packages...")
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
    elif dry_run:
        print("\n[13/15] [DRY RUN] Skipping Task List generation")

    # Generate Reports (Validation + Traceability)
    if not dry_run:
        print("\n[14/15] Generating Reports...")
        reports_dir = output_dir / "reports"

        # Validation Report
        validation_md = create_validation_report(journal, requirements)
        with open(reports_dir / "validation_report.md", "w", encoding="utf-8") as f:
            f.write(validation_md)

        # Traceability Matrix
        traceability_md = create_traceability_matrix(
            requirements,
            user_stories if user_stories else [],
            test_cases if with_gherkin and user_stories else [],
            api_endpoints=api_endpoints if api_endpoints else None,
            screens=ui_spec.screens if ui_spec else None,
            entities=data_dict.entities if data_dict else None,
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
    elif dry_run:
        print("\n[14/15] [DRY RUN] Skipping Reports generation")

    # Self-Critique Pass (final sweep — per-stage critique already caught some issues earlier)
    critique_result = None
    if not dry_run:
        print("\n[15/15] Running Self-Critique Analysis (final sweep)...")
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
        except Exception as e:
            print(f"   [WARN] Self-critique failed: {e}")
    elif dry_run:
        print("\n[15/15] [DRY RUN] Skipping Self-Critique")

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
        total_hours=task_breakdown.total_hours if task_breakdown else 0
    )
    with open(output_dir / "MASTER_DOCUMENT.md", "w", encoding="utf-8") as f:
        f.write(master_md)

    # Emit pipeline complete event
    if emitter:
        await emitter.pipeline_complete({
            "requirements": len(requirements),
            "user_stories": len(user_stories) if user_stories else 0,
            "epics": len(epics) if epics else 0,
            "test_cases": len(test_cases) if with_gherkin and user_stories else 0,
            "output_dir": str(output_dir)
        })
        await emitter.log_info("Pipeline complete!")

    # Print LLM usage summary
    llm_logger = get_llm_logger()
    if llm_logger.calls:
        llm_logger.print_summary()
        # Save summary to file
        llm_logger.save_summary(str(output_dir / "llm_usage_summary.json"))
        print(f"\n[INFO] LLM usage summary saved to: {output_dir / 'llm_usage_summary.json'}")

    print("\n" + "=" * 70)
    print("Enterprise Requirements Engineering Complete!")
    print(f"Output directory: {output_dir}")
    if with_dashboard:
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
    total_hours: int = 0
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
    if quality_score is not None:
        md += f"| **Quality Score** | **{quality_score:.1f}/10** | {'PASS' if quality_score >= 7 else 'REVIEW'} |\n"
    md += "\n"

    # Coverage summary
    md += "### Coverage Analysis\n\n"
    md += f"- **Requirements → User Stories:** {story_coverage:.0f}%\n"
    md += f"- **User Stories → Test Cases:** {test_coverage:.0f}%\n"
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
    md += "4. [Test Documentation](testing/test_documentation.md)\n\n"

    md += "### Design & Architecture\n\n"
    md += "5. [Tech Stack Recommendations](tech_stack/tech_stack.md)\n"
    md += "6. [UX Design](ux_design/personas.md) | [User Flows](ux_design/user_flows.md)\n"
    md += "7. [UI Design System](ui_design/design_system.md) | [Components](ui_design/components.md)\n\n"

    md += "### Analysis & Planning\n\n"
    md += "8. [Work Breakdown Structure](work_breakdown/feature_breakdown.md)\n"
    md += "9. [Task List](tasks/task_list.md) | [Gantt Chart](tasks/gantt_chart.mmd)\n"
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
        default="re_config.yaml",
        help="Path to configuration YAML (default: re_config.yaml)"
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

    args = parser.parse_args()

    # Auto-detect project if not specified
    if args.project is None:
        re_ideas_dir = Path(__file__).parent / "re_ideas"
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
            dashboard_port=args.dashboard_port
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
