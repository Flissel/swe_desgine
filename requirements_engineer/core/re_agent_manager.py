"""
Requirements Engineering Agent Manager - Orchestrates the 4 stages of RE.

Based on ai_scientist/treesearch/agent_manager.py
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("re-agent-manager")

from omegaconf import OmegaConf, DictConfig

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_scientist.treesearch.backend import query
from ai_scientist.treesearch.backend.utils import FunctionSpec
from requirements_engineer.tools.mermaid_output_handler import MermaidOutputHandler
from ..prompts.diagram_prompts import (
    DIAGRAM_SELECTION_PROMPT,
    DIAGRAM_SELECTION_SYSTEM_PROMPT
)

from .re_journal import RequirementJournal, RequirementNode
from .re_metrics import RequirementMetrics, StageMetrics, ProjectMetrics
from .re_draft_engine import RequirementDraftEngine
from .re_improver import IterativeImprover
from .token_manager import TokenBudget, RequirementChunker, TokenEstimator


# Stage definitions
STAGE_NAMES = {
    1: "discovery",
    2: "analysis",
    3: "specification",
    4: "validation"
}

STAGE_DESCRIPTIONS = {
    1: "Discovery - Elicit requirements from provided context",
    2: "Analysis - Decompose, classify, and prioritize requirements",
    3: "Specification - Formalize with acceptance criteria and diagrams",
    4: "Validation - Verify completeness, consistency, and feasibility"
}


@dataclass
class REStageConfig:
    """Configuration for a single RE stage."""
    stage_number: int
    name: str
    description: str
    max_iterations: int
    goals: List[str]
    required_diagrams: List[str] = field(default_factory=list)
    validation_threshold: float = 0.8


class REAgentManager:
    """
    Manager for Requirements Engineering stages.
    Orchestrates the 4 stages: Discovery, Analysis, Specification, Validation.
    """

    def __init__(
        self,
        config: DictConfig,
        project_input: Dict[str, Any],
        journal: RequirementJournal = None,
        output_dir: str = None,
        metrics: Any = None  # For backwards compatibility
    ):
        """
        Initialize the RE Agent Manager.

        Args:
            config: Configuration from re_config.yaml
            project_input: Project input JSON data
            journal: RequirementJournal instance (created if not provided)
            output_dir: Directory for output files (optional)
            metrics: MetricsManager instance (for backwards compatibility)
        """
        self.config = config
        self.project_input = project_input

        # Set output directory if provided
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.output_dir = None

        # Use provided journal or create a new one
        if journal is not None:
            self.journal = journal
        else:
            self.journal = RequirementJournal(
                project_name=project_input.get("Name", "Unknown Project")
            )

        # Initialize project metrics
        self.project_metrics = ProjectMetrics(
            project_name=project_input.get("Name", "Unknown Project")
        )

        # Stage configuration
        self.stages = self._create_stage_configs()
        self.current_stage = 1

        # Mermaid handler
        self.mermaid_handler = MermaidOutputHandler()

        # LLM settings
        self.llm_config = config.agent.code
        self.feedback_config = config.agent.feedback

        # Initialize tree-search components (from AI-Scientist pattern)
        config_dict = OmegaConf.to_container(config, resolve=True)
        self.draft_engine = RequirementDraftEngine(
            config=config_dict,
            journal=self.journal,
            query_func=query
        )
        self.improver = IterativeImprover(
            config=config_dict,
            journal=self.journal,
            query_func=query
        )

        # Search settings
        search_config = config.agent.get("search", {})
        self.num_drafts = search_config.get("num_drafts", 3)
        self.max_debug_depth = search_config.get("max_debug_depth", 2)
        self.use_tree_search = True  # Enable tree-search mode

        # PERFORMANCE: Token management for large requirement sets
        self.token_budget = TokenBudget(max_context=100000)
        self.chunker = RequirementChunker(self.token_budget)

    def _create_stage_configs(self) -> Dict[int, REStageConfig]:
        """Create stage configurations from config."""
        stages = {}

        stage_goals = self.config.get("stage_goals", {})
        diagram_types = self.config.diagrams.get("types", [])

        # Stage 1: Discovery
        stages[1] = REStageConfig(
            stage_number=1,
            name="discovery",
            description=STAGE_DESCRIPTIONS[1],
            max_iterations=self.config.stages.get("stage1_max_iters", 10),
            goals=self._parse_goals(stage_goals.get(1, "")),
            required_diagrams=[]
        )

        # Stage 2: Analysis
        stages[2] = REStageConfig(
            stage_number=2,
            name="analysis",
            description=STAGE_DESCRIPTIONS[2],
            max_iterations=self.config.stages.get("stage2_max_iters", 8),
            goals=self._parse_goals(stage_goals.get(2, "")),
            required_diagrams=[]
        )

        # Stage 3: Specification
        stages[3] = REStageConfig(
            stage_number=3,
            name="specification",
            description=STAGE_DESCRIPTIONS[3],
            max_iterations=self.config.stages.get("stage3_max_iters", 12),
            goals=self._parse_goals(stage_goals.get(3, "")),
            required_diagrams=diagram_types
        )

        # Stage 4: Validation
        stages[4] = REStageConfig(
            stage_number=4,
            name="validation",
            description=STAGE_DESCRIPTIONS[4],
            max_iterations=self.config.stages.get("stage4_max_iters", 6),
            goals=self._parse_goals(stage_goals.get(4, "")),
            required_diagrams=[],
            validation_threshold=0.9
        )

        return stages

    def _parse_goals(self, goals_str: str) -> List[str]:
        """Parse goals from string to list."""
        if not goals_str:
            return []
        return [g.strip().lstrip("- ") for g in goals_str.strip().split("\n") if g.strip()]

    def run(
        self,
        step_callback: Optional[Callable[[int, int, RequirementJournal], None]] = None
    ):
        """
        Run all stages of requirements engineering.

        Args:
            step_callback: Optional callback after each step
        """
        print(f"\n{'='*60}")
        print(f"Starting Requirements Engineering for: {self.journal.project_name}")
        print(f"{'='*60}\n")

        for stage_num in range(1, 5):
            self._run_stage(stage_num, step_callback)

        # Generate final outputs
        self._generate_final_outputs()

        print(f"\n{'='*60}")
        print(f"Requirements Engineering Complete!")
        print(f"Output directory: {self.output_dir}")
        print(f"{'='*60}\n")

    def _run_stage(
        self,
        stage_num: int,
        step_callback: Optional[Callable] = None
    ):
        """Run a single stage."""
        stage_config = self.stages[stage_num]
        self.current_stage = stage_num
        self.journal.current_stage = stage_num

        print(f"\n{'='*40}")
        print(f"Stage {stage_num}: {stage_config.description}")
        print(f"{'='*40}\n")

        # Initialize stage metrics
        stage_metrics = StageMetrics(
            stage_number=stage_num,
            stage_name=stage_config.name,
            max_iterations=stage_config.max_iterations
        )

        # Get metric weights from config (used for weighted aggregate scoring)
        config_dict = OmegaConf.to_container(self.config, resolve=True) if hasattr(self.config, '_metadata') else dict(self.config)
        metric_weights = config_dict.get("metric_weights", None)

        # Get initial score
        if self.journal.get_good_nodes():
            best_node = self.journal.get_best_node(metric_weights)
            stage_metrics.initial_aggregate_score = best_node.aggregate_score(metric_weights) if best_node else 0.0

        # Run iterations
        for iteration in range(stage_config.max_iterations):
            print(f"  Iteration {iteration + 1}/{stage_config.max_iterations}")

            # Execute stage-specific logic
            if stage_num == 1:
                self._run_discovery_iteration(iteration)
            elif stage_num == 2:
                self._run_analysis_iteration(iteration)
            elif stage_num == 3:
                self._run_specification_iteration(iteration)
            elif stage_num == 4:
                self._run_validation_iteration(iteration)

            stage_metrics.iterations_completed = iteration + 1

            # Check for stage completion
            if self._check_stage_completion(stage_config):
                print(f"  Stage {stage_num} completed early at iteration {iteration + 1}")
                break

            if step_callback:
                step_callback(stage_num, iteration, self.journal)

        # Get final score
        if self.journal.get_good_nodes():
            best_node = self.journal.get_best_node(metric_weights)
            stage_metrics.final_aggregate_score = best_node.aggregate_score(metric_weights) if best_node else 0.0
            stage_metrics.calculate_improvement()

        stage_metrics.requirements_processed = len(self.journal.get_nodes_by_stage(stage_num))
        self.project_metrics.stage_metrics.append(stage_metrics)

        # Save stage checkpoint
        self._save_stage_checkpoint(stage_num)

    def _run_discovery_iteration(self, iteration: int):
        """Run a discovery iteration with tree-search pattern.

        Uses parallel drafting from different perspectives (technical, business, user)
        followed by debug/improve loop.
        """
        from ..prompts.elicitation_prompts import get_elicitation_prompt

        base_prompt = get_elicitation_prompt(
            self.project_input,
            self.journal.get_all_requirements(),
            iteration
        )

        if self.use_tree_search and iteration == 0:
            # PHASE 1: Parallel Drafting (only on first iteration or when needed)
            print(f"    Generating {self.num_drafts} parallel drafts...")

            drafts = self.draft_engine.generate_drafts(
                context={
                    "name": self.project_input.get("Name", ""),
                    "domain": self.project_input.get("Domain", ""),
                    "description": self.project_input.get("Description", ""),
                },
                stage=1,
                base_prompt=base_prompt,
                existing_requirements=self.journal.get_all_requirements()
            )

            # Evaluate all drafts
            for draft_result in drafts:
                if draft_result.success and draft_result.node:
                    draft_result.node = self.draft_engine.evaluate_draft(draft_result.node)
                    self.journal.add_node(draft_result.node)
                    print(f"      Draft ({draft_result.perspective}): score={draft_result.node.aggregate_score():.2f}")

            # Select best draft
            best = self.draft_engine.select_best_draft(drafts)
            if best:
                print(f"    Selected best draft: {best.title[:50]}...")

        else:
            # PHASE 2: Debug/Improve existing nodes
            best_node = self.journal.get_best_node()

            if best_node:
                # Diagnose current state
                diagnosis = self.improver.diagnose(best_node)

                if diagnosis.is_buggy:
                    # Debug: Fix quality issues
                    print(f"    Debugging: {len(diagnosis.quality_issues)} issues found")
                    fixed_node = self.improver.debug_node(best_node, diagnosis)
                    self.journal.add_node(fixed_node)
                    print(f"      Fixed score: {fixed_node.aggregate_score():.2f}")
                else:
                    # Improve: Enhance quality
                    print(f"    Improving: {len(diagnosis.improvement_hints)} hints")
                    improved_node = self.improver.improve_node(best_node, diagnosis.improvement_hints)
                    self.journal.add_node(improved_node)
                    print(f"      Improved score: {improved_node.aggregate_score():.2f}")
            else:
                # Fallback: Use standard generation if no nodes exist
                self._run_standard_discovery(base_prompt)

    def _run_standard_discovery(self, prompt: str):
        """Standard discovery without tree-search (fallback)."""
        response = query(
            system_message={"role": "Requirements Engineer", "task": "Elicit requirements"},
            user_message=prompt,
            model=self.llm_config.model,
            temperature=self.llm_config.temp,
            max_tokens=self.llm_config.max_tokens
        )

        requirements = self._parse_requirements_response(response)
        for req_data in requirements:
            node = RequirementNode(
                title=req_data.get("title", ""),
                description=req_data.get("description", ""),
                type=req_data.get("type", "functional"),
                priority=req_data.get("priority", "should"),
                rationale=req_data.get("rationale", ""),
                source=req_data.get("source", "Discovery Stage"),
                acceptance_criteria=req_data.get("acceptance_criteria", []),
                stage=1,
                stage_name="draft"
            )
            self.journal.add_node(node)

    def _run_analysis_iteration(self, iteration: int):
        """Run an analysis iteration with tree-search debug/improve loop.

        PERFORMANCE: Uses token-aware chunking for large requirement sets.
        """
        from ..prompts.analysis_prompts import get_analysis_prompt

        requirements = self.journal.get_good_nodes()
        if not requirements:
            return

        # Apply debug/improve to best node
        best_node = self.journal.get_best_node()
        if best_node and self.use_tree_search:
            diagnosis = self.improver.diagnose(best_node)

            if diagnosis.is_buggy:
                print(f"    Debugging requirement: {best_node.requirement_id}")
                fixed = self.improver.debug_node(best_node, diagnosis)
                self.journal.add_node(fixed)
            elif diagnosis.can_improve:
                print(f"    Improving requirement: {best_node.requirement_id}")
                improved = self.improver.improve_node(best_node, diagnosis.improvement_hints)
                self.journal.add_node(improved)

        # PERFORMANCE: Use chunking if many requirements
        batch_info = self.chunker.get_batch_info(requirements)
        num_batches = batch_info["num_batches"]

        if num_batches > 1:
            print(f"    Processing {len(requirements)} requirements in {num_batches} batches...")

        all_results = []
        for batch_idx, req_batch in enumerate(self.chunker.chunk_requirements(requirements, prompt_template_tokens=2000)):
            if num_batches > 1:
                print(f"      Batch {batch_idx + 1}/{num_batches}: {len(req_batch)} requirements")

            prompt = get_analysis_prompt(req_batch, iteration)

            response = query(
                system_message={"role": "Requirements Analyst", "task": "Analyze requirements"},
                user_message=prompt,
                model=self.llm_config.model,
                temperature=self.llm_config.temp,
                max_tokens=self.llm_config.max_tokens
            )

            # Parse analysis and collect results
            batch_results = self._parse_analysis_response(response)
            all_results.append(batch_results)

        # Apply aggregated results
        self._apply_analysis_results(self._aggregate_analysis_results(all_results))

    def _aggregate_analysis_results(self, batch_results: List[Dict]) -> Dict:
        """Aggregate analysis results from multiple batches."""
        if len(batch_results) == 1:
            return batch_results[0]

        # Merge results from all batches
        aggregated = {}
        for result in batch_results:
            if result:
                for key, value in result.items():
                    if key not in aggregated:
                        aggregated[key] = value
                    elif isinstance(value, list):
                        aggregated[key].extend(value)
                    elif isinstance(value, dict):
                        aggregated[key].update(value)

        return aggregated

    def _run_specification_iteration(self, iteration: int):
        """Run a specification iteration - formalize and generate diagrams.

        PERFORMANCE: Uses parallel diagram generation for ~5x speedup.
        SMART SELECTION: LLM decides which diagram types are relevant per requirement.
        """
        from ..prompts.specification_prompts import get_specification_prompt
        from ..prompts.diagram_prompts import get_diagram_prompt

        requirements = self.journal.get_good_nodes()
        if not requirements:
            return

        # Formalize requirements
        prompt = get_specification_prompt(requirements, iteration)

        response = query(
            system_message={"role": "Requirements Specifier", "task": "Formalize requirements"},
            user_message=prompt,
            model=self.llm_config.model,
            temperature=self.llm_config.temp,
            max_tokens=self.llm_config.max_tokens
        )

        self._apply_specification_results(response)

        # Get available diagram types from config
        available_diagram_types = self.config.diagrams.types
        use_smart_selection = self.config.diagrams.get("smart_selection", True)

        if use_smart_selection and len(requirements) > 0:
            # SMART SELECTION: Let LLM decide which diagrams are relevant per requirement
            print(f"    Smart diagram selection for {len(requirements)} requirements...")

            # Collect diagram tasks: (requirement, diagram_type) pairs
            diagram_tasks = []

            for req in requirements:
                # Select relevant diagram types for this requirement
                selected_types = self._select_diagram_types(req, available_diagram_types)
                print(f"      {req.requirement_id}: {selected_types}")

                for dtype in selected_types:
                    diagram_tasks.append((req, dtype))

            total_diagrams = len(diagram_tasks)
            print(f"    Generating {total_diagrams} diagrams (reduced from {len(requirements) * len(available_diagram_types)})...")

            # Generate selected diagrams in parallel
            max_workers = min(5, total_diagrams) if total_diagrams > 0 else 1

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for req, dtype in diagram_tasks:
                    future = executor.submit(
                        self._generate_single_diagram,
                        [req],  # Single requirement for targeted diagram
                        dtype,
                        iteration
                    )
                    futures[future] = (req.requirement_id, dtype)

                for future in as_completed(futures):
                    req_id, dtype = futures[future]
                    try:
                        mermaid_code = future.result()
                        if mermaid_code:
                            # Save with requirement ID prefix for dashboard linking
                            self._save_diagram(f"{req_id}_{dtype}", mermaid_code, iteration)
                    except Exception as e:
                        logger.error(f"Diagram {req_id}_{dtype} generation failed: {e}")
        else:
            # Fallback: Generate all diagram types (original behavior)
            max_workers = min(5, len(available_diagram_types))

            print(f"    Generating {len(available_diagram_types)} diagrams in parallel...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._generate_single_diagram,
                        requirements,
                        dtype,
                        iteration
                    ): dtype
                    for dtype in available_diagram_types
                }

                for future in as_completed(futures):
                    dtype = futures[future]
                    try:
                        mermaid_code = future.result()
                        if mermaid_code:
                            self._save_diagram(dtype, mermaid_code, iteration)
                    except Exception as e:
                        logger.error(f"Diagram {dtype} generation failed: {e}")

    def _select_diagram_types(
        self,
        requirement: RequirementNode,
        available_types: List[str]
    ) -> List[str]:
        """Use LLM to select which diagram types are most relevant for a requirement.

        Args:
            requirement: The requirement to analyze
            available_types: List of available diagram types

        Returns:
            List of 2-3 selected diagram types
        """
        # Build prompt with requirement details
        prompt = DIAGRAM_SELECTION_PROMPT.format(
            requirement_id=requirement.requirement_id,
            requirement_title=requirement.title,
            requirement_type=requirement.type,
            requirement_description=requirement.description
        )

        try:
            response = query(
                system_message=DIAGRAM_SELECTION_SYSTEM_PROMPT,
                user_message=prompt,
                model=self.llm_config.model,
                temperature=0.2,  # Low temperature for consistent selection
                max_tokens=100
            )

            # Parse JSON response
            import re
            # Extract JSON array from response
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                selected = json.loads(json_match.group())
                # Validate: only keep types that exist in available_types
                valid_selected = [t for t in selected if t in available_types]
                if len(valid_selected) >= 2:
                    return valid_selected[:3]  # Max 3 types

            logger.warning(f"Could not parse diagram selection for {requirement.requirement_id}, using fallback")

        except Exception as e:
            logger.error(f"Diagram selection failed for {requirement.requirement_id}: {e}")

        # Fallback: return first 2 types
        return available_types[:2] if len(available_types) >= 2 else available_types

    def _generate_single_diagram(
        self,
        requirements: List[RequirementNode],
        diagram_type: str,
        iteration: int
    ) -> Optional[str]:
        """Generate a single diagram (thread-safe).

        Args:
            requirements: List of requirements to include
            diagram_type: Type of Mermaid diagram
            iteration: Current iteration number

        Returns:
            Mermaid code string or None
        """
        from ..prompts.diagram_prompts import get_diagram_prompt

        diagram_prompt = get_diagram_prompt(requirements, diagram_type)

        diagram_response = query(
            system_message={"role": "Diagram Generator", "task": f"Generate {diagram_type}"},
            user_message=diagram_prompt,
            model=self.llm_config.model,
            temperature=0.3,  # Lower temperature for consistent diagrams
            max_tokens=self.llm_config.max_tokens
        )

        return self.mermaid_handler.extract_mermaid_block(diagram_response)

    def _run_validation_iteration(self, iteration: int):
        """Run a validation iteration - verify quality."""
        from ..prompts.validation_prompts import get_validation_prompt

        requirements = self.journal.get_good_nodes()
        if not requirements:
            return

        prompt = get_validation_prompt(
            requirements,
            self.config.validation,
            iteration
        )

        response = query(
            system_message={"role": "Requirements Validator", "task": "Validate requirements"},
            user_message=prompt,
            model=self.feedback_config.model,
            temperature=self.feedback_config.temp,
            max_tokens=self.feedback_config.max_tokens
        )

        # Parse validation results and update metrics
        validation_results = self._parse_validation_response(response)
        self._apply_validation_results(validation_results)

    def _get_tree_search_summary(self) -> str:
        """Get a summary of the tree-search state."""
        draft_nodes = self.journal.get_draft_nodes()
        buggy_nodes = self.journal.get_buggy_nodes()
        good_nodes = self.journal.get_good_nodes()
        best = self.journal.get_best_node()

        return (
            f"Tree-search state: "
            f"drafts={len(draft_nodes)}, "
            f"buggy={len(buggy_nodes)}, "
            f"good={len(good_nodes)}, "
            f"best_score={best.aggregate_score():.2f if best else 0.0}"
        )

    def _check_stage_completion(self, stage_config: REStageConfig) -> bool:
        """Check if a stage is complete based on quality thresholds."""
        good_nodes = self.journal.get_good_nodes()
        if not good_nodes:
            return False

        # For validation stage, check against thresholds
        if stage_config.stage_number == 4:
            best_node = self.journal.get_best_node()
            if best_node:
                thresholds = self.config.validation
                metrics = RequirementMetrics(
                    completeness_score=best_node.completeness_score,
                    consistency_score=best_node.consistency_score,
                    testability_score=best_node.testability_score,
                    clarity_score=best_node.clarity_score,
                    feasibility_score=best_node.feasibility_score,
                    traceability_score=best_node.traceability_score
                )
                passes, _ = metrics.passes_thresholds(thresholds)
                return passes

        return False

    def _parse_requirements_response(self, response: str) -> List[Dict]:
        """Parse requirements from LLM response."""
        # Try to extract JSON
        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON from requirements response: {e}")

        # Fallback: simple parsing
        requirements = []
        # Basic parsing logic - would be enhanced with FunctionSpec in production
        return requirements

    def _parse_analysis_response(self, response: str) -> Dict:
        """Parse analysis results from LLM response."""
        return {}

    def _apply_analysis_results(self, results: Dict):
        """Apply analysis results to requirements."""
        pass

    def _apply_specification_results(self, response: str):
        """Apply specification results to requirements."""
        pass

    def _parse_validation_response(self, response: str) -> Dict:
        """Parse validation results from LLM response."""
        return {}

    def _apply_validation_results(self, results: Dict):
        """Apply validation results and update metrics."""
        pass

    def _save_diagram(self, diagram_type: str, mermaid_code: str, iteration: int):
        """Save a Mermaid diagram to node and optionally to file.

        Stores the diagram in the first good node's mermaid_diagrams dict
        so that save_diagrams() in run_re_system.py can find it.
        Also saves to file if output_dir is set.
        """
        # Store diagram in node for later retrieval by save_diagrams()
        good_nodes = self.journal.get_good_nodes()
        if good_nodes:
            # Store in first good node (or could store in all)
            node = good_nodes[0]
            node.mermaid_diagrams[diagram_type] = mermaid_code

        # Also save to file if output_dir is set
        if self.output_dir:
            diagrams_dir = self.output_dir / "diagrams"
            diagrams_dir.mkdir(exist_ok=True)

            filename = f"{diagram_type}_{iteration}.mmd"
            filepath = diagrams_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(mermaid_code)

            print(f"    Saved diagram: {filename}")

    def _save_stage_checkpoint(self, stage_num: int):
        """Save checkpoint after stage completion."""
        if not self.output_dir:
            return  # Skip if no output directory

        checkpoint_dir = self.output_dir / "checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)

        # Save journal
        journal_path = checkpoint_dir / f"journal_stage{stage_num}.json"
        self.journal.save(str(journal_path))

        # Save stage summary
        summary_path = checkpoint_dir / f"stage{stage_num}_summary.md"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"# Stage {stage_num}: {STAGE_NAMES[stage_num].title()}\n\n")
            f.write(f"Completed: {datetime.now().isoformat()}\n")
            f.write(f"Requirements: {len(self.journal.get_nodes_by_stage(stage_num))}\n")

    def _generate_final_outputs(self):
        """Generate all final output documents."""
        if not self.output_dir:
            print("\nSkipping final outputs (no output directory set)")
            return

        print("\nGenerating final outputs...")

        # Requirements specification
        spec_path = self.output_dir / "requirements_specification.md"
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(self.journal.to_markdown())
        print(f"  Created: requirements_specification.md")

        # Traceability matrix
        matrix = self.journal.generate_traceability_matrix()
        matrix_path = self.output_dir / "traceability_matrix.json"
        with open(matrix_path, "w", encoding="utf-8") as f:
            json.dump(matrix, f, indent=2)
        print(f"  Created: traceability_matrix.json")

        # Project metrics
        metrics_path = self.output_dir / "project_metrics.md"
        with open(metrics_path, "w", encoding="utf-8") as f:
            f.write(self.project_metrics.summary())
        print(f"  Created: project_metrics.md")

        # Save final journal
        journal_path = self.output_dir / "final_journal.json"
        self.journal.save(str(journal_path))
        print(f"  Created: final_journal.json")


def load_config(config_path: str = None) -> DictConfig:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "re_config.yaml")
    return OmegaConf.load(config_path)


def load_project_input(input_path: str) -> Dict[str, Any]:
    """Load project input from JSON file."""
    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)
