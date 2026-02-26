"""
Layout Orchestrator - Uses AI-Scientist tree-search patterns for layout generation.

Leverages existing patterns from ai_scientist/treesearch/:
- Node/Journal for variant tracking
- Parallel draft generation
- LLM-based evaluation and selection
- Stage-based progression
"""

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

# Add AI-Scientist path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai_scientist.treesearch.backend import query
from ai_scientist.treesearch.backend.utils import FunctionSpec

logger = logging.getLogger("layout-orchestrator")


# ============================================================================
# Function Specs for Structured LLM Output (AI-Scientist Pattern)
# ============================================================================

LAYOUT_ANALYSIS_SPEC = FunctionSpec(
    name="analyze_project_structure",
    json_schema={
        "type": "object",
        "properties": {
            "domains": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "items": {"type": "array", "items": {"type": "string"}},
                        "color": {"type": "string"}
                    }
                }
            },
            "hierarchies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "parent": {"type": "string"},
                        "children": {"type": "array", "items": {"type": "string"}}
                    }
                }
            },
            "aggregations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group_name": {"type": "string"},
                        "items": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"}
                    }
                }
            },
            "recommended_layout": {"type": "string"},
            "complexity_score": {"type": "number"},
            "notes": {"type": "string"}
        },
        "required": ["domains", "recommended_layout"]
    },
    description="Analyze project structure for optimal layout"
)

LAYOUT_SELECTION_SPEC = FunctionSpec(
    name="select_best_layout",
    json_schema={
        "type": "object",
        "properties": {
            "selected_id": {"type": "string"},
            "reasoning": {"type": "string"},
            "score": {"type": "number"}
        },
        "required": ["selected_id", "reasoning"]
    },
    description="Select best layout variant"
)


# ============================================================================
# Layout Node (Similar to AI-Scientist Node class)
# ============================================================================

@dataclass
class LayoutNode:
    """
    A layout variant node - similar to ai_scientist/treesearch/journal.py Node.

    Tracks:
    - Layout design (plan)
    - Structure definition (code equivalent)
    - Evaluation metrics
    - Parent/child relationships for tree search
    """
    # Identity
    id: str
    name: str
    description: str
    layout_type: str  # hierarchical, matrix, cluster, domain-based, swimlane

    # Layout definition (equivalent to Node.plan and Node.code)
    plan: str = ""  # Natural language description of layout strategy
    structure: Dict = field(default_factory=dict)  # Layout structure (columns, aggregations, positions)

    # Tree relationships (for tree search)
    parent: Optional["LayoutNode"] = None
    children: List["LayoutNode"] = field(default_factory=list)
    step: int = 0
    debug_depth: int = 0

    # Evaluation (similar to Node.metric, is_buggy, analysis)
    score: float = 0.0
    is_valid: bool = True
    analysis: str = ""
    user_feedback: str = ""

    # Generated content
    aggregations: List[Dict] = field(default_factory=list)
    columns: List[Dict] = field(default_factory=list)
    positions: Dict[str, Dict] = field(default_factory=dict)
    html_structure: str = ""

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Serialize for cross-process communication (AI-Scientist pattern)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "layout_type": self.layout_type,
            "plan": self.plan,
            "structure": self.structure,
            "score": self.score,
            "is_valid": self.is_valid,
            "analysis": self.analysis,
            "aggregations": self.aggregations,
            "columns": self.columns,
            "positions": self.positions,
            "step": self.step,
            "debug_depth": self.debug_depth
        }

    @classmethod
    def from_dict(cls, data: Dict, parent: "LayoutNode" = None) -> "LayoutNode":
        """Deserialize from dict (AI-Scientist pattern)."""
        node = cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            layout_type=data["layout_type"],
            plan=data.get("plan", ""),
            structure=data.get("structure", {}),
            score=data.get("score", 0.0),
            is_valid=data.get("is_valid", True),
            analysis=data.get("analysis", ""),
            aggregations=data.get("aggregations", []),
            columns=data.get("columns", []),
            positions=data.get("positions", {}),
            step=data.get("step", 0),
            debug_depth=data.get("debug_depth", 0),
            parent=parent
        )
        return node


# ============================================================================
# Layout Journal (Similar to AI-Scientist Journal class)
# ============================================================================

class LayoutJournal:
    """
    Tracks all layout variants - similar to ai_scientist/treesearch/journal.py Journal.

    Properties mirror the AI-Scientist Journal:
    - draft_nodes: Initial layouts (no parent)
    - good_nodes: Valid, usable layouts
    - buggy_nodes: Invalid layouts (renamed to invalid_nodes)
    """

    def __init__(self, project_name: str = ""):
        self.project_name = project_name
        self.nodes: List[LayoutNode] = []
        self._step_counter = 0

    def append(self, node: LayoutNode):
        """Add a node to the journal."""
        node.step = self._step_counter
        self._step_counter += 1
        self.nodes.append(node)
        logger.info(f"[Journal] Added layout: {node.id} (score={node.score:.2f})")

    @property
    def draft_nodes(self) -> List[LayoutNode]:
        """Initial layouts (no parent) - AI-Scientist pattern."""
        return [n for n in self.nodes if n.parent is None]

    @property
    def good_nodes(self) -> List[LayoutNode]:
        """Valid, usable layouts - AI-Scientist pattern."""
        return [n for n in self.nodes if n.is_valid]

    @property
    def invalid_nodes(self) -> List[LayoutNode]:
        """Invalid layouts (equivalent to buggy_nodes)."""
        return [n for n in self.nodes if not n.is_valid]

    def get_best_node(self, use_llm: bool = False, query_func: Callable = None) -> Optional[LayoutNode]:
        """
        Get best layout - AI-Scientist pattern with LLM comparison.

        Args:
            use_llm: Whether to use LLM for comparative evaluation
            query_func: LLM query function

        Returns:
            Best LayoutNode
        """
        good = self.good_nodes
        if not good:
            return None

        if len(good) == 1:
            return good[0]

        if use_llm and query_func:
            return self._llm_select_best(good, query_func)

        # Fallback: highest score
        return max(good, key=lambda n: n.score)

    def _llm_select_best(self, candidates: List[LayoutNode], query_func: Callable) -> LayoutNode:
        """Use LLM to select best layout (AI-Scientist comparative evaluation)."""
        prompt = {
            "Introduction": "You are a UX expert evaluating layout designs.",
            "Task": "Select the best layout from the candidates below.",
            "Criteria": [
                "Clarity: How easy is it to understand the project structure?",
                "Efficiency: How well does it use screen space?",
                "Grouping: Are related items logically grouped?",
                "Navigation: How easy is it to find specific items?"
            ],
            "Candidates": ""
        }

        for node in candidates:
            prompt["Candidates"] += f"""
---
ID: {node.id}
Name: {node.name}
Type: {node.layout_type}
Groups: {len(node.aggregations)}
Columns: {len(node.columns)}
Description: {node.description}
---
"""

        try:
            result = query_func(
                system_message=json.dumps(prompt),
                user_message="Select the best layout variant.",
                func_spec=LAYOUT_SELECTION_SPEC,
                temperature=0.3
            )
            selected_id = result.get("selected_id", candidates[0].id)
            return next((n for n in candidates if n.id == selected_id), candidates[0])
        except Exception as e:
            logger.error(f"LLM selection failed: {e}")
            return max(candidates, key=lambda n: n.score)

    def generate_summary(self) -> str:
        """Generate rolling summary (AI-Scientist memory pattern)."""
        summary = ["# Layout Generation Summary\n"]

        summary.append(f"## Good Layouts ({len(self.good_nodes)})")
        for node in self.good_nodes:
            summary.append(f"- {node.name}: {node.layout_type} (score={node.score:.2f})")

        if self.invalid_nodes:
            summary.append(f"\n## Invalid Layouts ({len(self.invalid_nodes)})")
            for node in self.invalid_nodes:
                summary.append(f"- {node.name}: {node.analysis[:50]}...")

        return "\n".join(summary)


# ============================================================================
# Layout Orchestrator (Similar to AI-Scientist AgentManager + ParallelAgent)
# ============================================================================

class LayoutOrchestrator:
    """
    Orchestrates layout generation using AI-Scientist patterns.

    Combines:
    - AgentManager: Stage-based progression
    - ParallelAgent: Parallel draft generation, tree search
    - Journal: Variant tracking and evaluation
    """

    def __init__(
        self,
        config: Dict,
        emitter: Any = None,
        num_workers: int = 3
    ):
        """
        Initialize orchestrator.

        Args:
            config: Configuration dict
            emitter: WebSocket event emitter
            num_workers: Number of parallel workers (like AI-Scientist)
        """
        self.config = config
        self.emitter = emitter
        self.num_workers = num_workers

        # Journal for tracking variants (AI-Scientist pattern)
        self.journal = LayoutJournal()

        # Stage tracking (AI-Scientist AgentManager pattern)
        self.current_stage = 0
        self.max_stages = 3

        # Search parameters (AI-Scientist search config pattern)
        search_cfg = config.get("agent", {}).get("search", {})
        self.num_drafts = search_cfg.get("num_drafts", 3)
        self.debug_prob = search_cfg.get("debug_prob", 0.3)
        self.improve_prob = search_cfg.get("improve_prob", 0.5)

        # LLM config - check generators.layout first, then fallback to agent.code
        gen_cfg = config.get("generators", {}).get("layout", {})
        llm_cfg = config.get("agent", {}).get("code", {})
        self.model = gen_cfg.get("model") or llm_cfg.get("model", "anthropic/claude-sonnet-4")
        self.temperature = gen_cfg.get("temperature", 0.5)
        self.max_tokens = gen_cfg.get("max_tokens", 16000)
        self.temperature = 0.4

        # User selection state
        self._selection_event = asyncio.Event()
        self._selected_id: Optional[str] = None

    # ========================================================================
    # DRAFT GENERATION (AI-Scientist ParallelAgent._draft pattern)
    # ========================================================================

    def _generate_draft(
        self,
        project_data: Dict,
        analysis: Dict,
        style: str,
        style_name: str,
        style_desc: str
    ) -> LayoutNode:
        """
        Generate a single layout draft.

        Similar to ParallelAgent._draft() - uses structured prompt and LLM query.
        """
        # Build prompt (AI-Scientist hierarchical prompt pattern)
        prompt = {
            "Introduction": "You are a UX/Visualization Expert creating dashboard layouts.",
            "Project Summary": self._build_project_summary(project_data),
            "Analysis": json.dumps(analysis, indent=2),
            "Layout Style": f"{style_name}: {style_desc}",
            "Instructions": {
                "aggregation_rules": [
                    "Group requirements with common prefixes",
                    "Cluster related API endpoints",
                    "Keep diagrams with their parent requirements"
                ],
                "output_format": "JSON with columns, aggregations, positions"
            }
        }

        # Generate layout structure
        try:
            response = query(
                system_message=json.dumps(prompt),
                user_message=f"Generate a {style} layout for this project.",
                model=self.model,
                temperature=self.temperature,
                max_tokens=3000
            )

            # Parse structure from response
            structure = self._parse_layout_response(response, style)

        except Exception as e:
            logger.error(f"Draft generation failed: {e}")
            structure = self._fallback_structure(project_data, style)

        # Create node
        node = LayoutNode(
            id=f"layout-{style}-{len(self.journal.nodes)}",
            name=style_name,
            description=style_desc,
            layout_type=style,
            plan=f"Layout using {style} approach for {len(project_data.get('requirements', []))} requirements",
            structure=structure,
            aggregations=structure.get("aggregations", []),
            columns=structure.get("columns", []),
            positions=structure.get("positions", {})
        )

        return node

    def _parse_layout_response(self, response: str, style: str) -> Dict:
        """Parse LLM response to extract layout structure."""
        import re

        # Try to find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Fallback structure
        return self._fallback_structure({}, style)

    def _fallback_structure(self, project_data: Dict, style: str) -> Dict:
        """Generate fallback structure without LLM."""
        return {
            "layout_type": style,
            "columns": [
                {"id": "requirements", "name": "Requirements", "width": 320},
                {"id": "stories", "name": "User Stories", "width": 320},
                {"id": "diagrams", "name": "Diagrams", "width": 480}
            ],
            "aggregations": [],
            "positions": {}
        }

    # ========================================================================
    # PARALLEL GENERATION (AI-Scientist ParallelAgent.step pattern)
    # ========================================================================

    async def generate_drafts(
        self,
        project_data: Dict,
        analysis: Dict
    ) -> List[LayoutNode]:
        """
        Generate multiple layout drafts in parallel.

        Similar to ParallelAgent.step() with ProcessPoolExecutor.
        """
        self.current_stage = 1
        logger.info(f"[Stage {self.current_stage}] Generating {self.num_drafts} layout drafts...")

        # Layout styles to generate
        styles = [
            ("domain-based", "Domain-basiert", "Gruppiert nach funktionalen Domains"),
            ("hierarchical", "Hierarchisch", "Epic → Story → Task Baumstruktur"),
            ("matrix", "Matrix", "Spalten nach Typ, Zeilen nach Work Package"),
            ("swimlane", "Swimlane", "Horizontale Bahnen nach Persona"),
            ("cluster", "Cluster", "Verbundene Komponenten als Gruppen")
        ]

        # Select styles based on analysis recommendation
        recommended = analysis.get("recommended_layout", "matrix")
        selected = [s for s in styles if s[0] == recommended]
        for s in styles:
            if s[0] != recommended and len(selected) < self.num_drafts:
                selected.append(s)

        # Generate in parallel (ThreadPoolExecutor like AI-Scientist)
        nodes = []
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {
                executor.submit(
                    self._generate_draft,
                    project_data, analysis, style[0], style[1], style[2]
                ): style[0]
                for style in selected[:self.num_drafts]
            }

            for future in as_completed(futures):
                style = futures[future]
                try:
                    node = future.result()
                    self.journal.append(node)
                    nodes.append(node)
                    logger.info(f"Generated draft: {node.id}")
                except Exception as e:
                    logger.error(f"Draft {style} failed: {e}")

        # Emit to dashboard
        if self.emitter:
            await self.emitter.emit("layout_variants_ready", {
                "stage": self.current_stage,
                "variants": [n.to_dict() for n in nodes]
            })

        return nodes

    # ========================================================================
    # NODE SELECTION (AI-Scientist _select_parallel_nodes pattern)
    # ========================================================================

    def _select_nodes_for_refinement(self) -> List[LayoutNode]:
        """
        Select nodes for next iteration.

        Similar to ParallelAgent._select_parallel_nodes with debug/improve logic.
        """
        nodes = []

        # Generate new drafts if needed
        if len(self.journal.draft_nodes) < self.num_drafts:
            return []  # Signal to generate more drafts

        good = self.journal.good_nodes
        if not good:
            return []

        # Debug phase (explore invalid branches)
        if random.random() < self.debug_prob:
            invalid = self.journal.invalid_nodes
            debuggable = [n for n in invalid if n.debug_depth < 2]
            if debuggable:
                nodes.append(random.choice(debuggable))

        # Improve phase (refine good nodes)
        if random.random() < self.improve_prob:
            best = self.journal.get_best_node()
            if best:
                nodes.append(best)

        return nodes

    # ========================================================================
    # MAIN WORKFLOW
    # ========================================================================

    async def run(
        self,
        project_data: Dict,
        interactive: bool = True
    ) -> LayoutNode:
        """
        Run full layout generation workflow.

        Args:
            project_data: Project data to visualize
            interactive: Whether to wait for user selection

        Returns:
            Final selected LayoutNode
        """
        logger.info("Starting layout generation...")

        # Stage 0: Analyze project
        analysis = await self.analyze_project(project_data)

        # Stage 1: Generate initial drafts
        drafts = await self.generate_drafts(project_data, analysis)

        if interactive:
            # Wait for user selection
            selected_id = await self.wait_for_selection(timeout=300)
            if selected_id:
                selected = next((n for n in drafts if n.id == selected_id), drafts[0])
            else:
                selected = self.journal.get_best_node()

            # Stage 2: Refine based on selection
            refined = await self.refine_layout(selected, project_data)

            # Stage 3: Final selection
            final_id = await self.wait_for_selection(timeout=300)
            if final_id:
                final = next((n for n in refined if n.id == final_id), refined[0])
            else:
                final = self.journal.get_best_node()
        else:
            # Auto-select best
            final = self.journal.get_best_node()

        return final

    async def analyze_project(self, project_data: Dict) -> Dict:
        """Analyze project structure using LLM."""
        logger.info("Analyzing project structure...")

        summary = self._build_project_summary(project_data)

        try:
            result = query(
                system_message="You are a software architecture analyst.",
                user_message=f"Analyze this project for optimal visualization:\n\n{summary}",
                func_spec=LAYOUT_ANALYSIS_SPEC,
                model=self.model,
                temperature=0.3
            )
            return result
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {"recommended_layout": "matrix", "domains": [], "complexity_score": 0.5}

    async def refine_layout(
        self,
        base_node: LayoutNode,
        project_data: Dict
    ) -> List[LayoutNode]:
        """
        Refine a layout based on user selection.

        Creates child nodes (AI-Scientist tree structure).
        """
        self.current_stage = 2
        logger.info(f"[Stage {self.current_stage}] Refining {base_node.id}...")

        refinements = [
            ("compact", "Kompakt", "Weniger Abstände"),
            ("detailed", "Ausführlich", "Mehr Details sichtbar"),
            ("minimal", "Minimal", "Nur essenzielle Infos")
        ]

        nodes = []
        for style, name, desc in refinements:
            child = LayoutNode(
                id=f"{base_node.id}-{style}",
                name=f"{base_node.name} ({name})",
                description=desc,
                layout_type=base_node.layout_type,
                parent=base_node,
                aggregations=base_node.aggregations.copy(),
                columns=base_node.columns.copy(),
                positions=self._adjust_positions(base_node.positions, style)
            )
            base_node.children.append(child)
            self.journal.append(child)
            nodes.append(child)

        if self.emitter:
            await self.emitter.emit("layout_refinement_ready", {
                "stage": self.current_stage,
                "base": base_node.id,
                "variants": [n.to_dict() for n in nodes]
            })

        return nodes

    def _adjust_positions(self, positions: Dict, style: str) -> Dict:
        """Adjust positions based on refinement style."""
        scale = {"compact": 0.7, "detailed": 1.2, "minimal": 0.5}.get(style, 1.0)
        adjusted = {}
        for node_id, pos in positions.items():
            adjusted[node_id] = {
                "x": pos.get("x", 0),
                "y": int(pos.get("y", 0) * scale),
                "width": pos.get("width", 300),
                "height": int(pos.get("height", 150) * scale)
            }
        return adjusted

    async def wait_for_selection(self, timeout: int = 300) -> Optional[str]:
        """Wait for user selection via WebSocket."""
        try:
            await asyncio.wait_for(self._selection_event.wait(), timeout=timeout)
            self._selection_event.clear()
            return self._selected_id
        except asyncio.TimeoutError:
            logger.warning(f"Selection timeout after {timeout}s")
            return None

    def on_user_selection(self, variant_id: str):
        """Handle user selection (called from WebSocket handler)."""
        self._selected_id = variant_id
        self._selection_event.set()
        logger.info(f"User selected: {variant_id}")

    def _build_project_summary(self, project_data: Dict) -> str:
        """Build text summary for LLM."""
        lines = []

        reqs = project_data.get("requirements", [])
        if reqs:
            lines.append(f"Requirements: {len(reqs)}")
            for r in reqs[:5]:
                lines.append(f"  - {r.get('id', '?')}: {r.get('title', '')[:40]}")

        stories = project_data.get("user_stories", [])
        if stories:
            lines.append(f"User Stories: {len(stories)}")

        diagrams = project_data.get("diagrams", [])
        if diagrams:
            lines.append(f"Diagrams: {len(diagrams)}")

        return "\n".join(lines)

    def save(self, output_dir: Path):
        """Save final layout to file."""
        best = self.journal.get_best_node()
        if not best:
            return

        layouts_dir = output_dir / "layouts"
        layouts_dir.mkdir(parents=True, exist_ok=True)

        with open(layouts_dir / "layout.json", "w") as f:
            json.dump(best.to_dict(), f, indent=2, default=str)

        logger.info(f"Layout saved to {layouts_dir}")
