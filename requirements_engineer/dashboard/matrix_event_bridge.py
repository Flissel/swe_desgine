"""
Matrix Event Bridge - Transforms pipeline artifacts into matrix-formatted events.

Bridges the RE pipeline (run_re_system.py) with the dashboard's matrix visualization.
Uses the existing callback mechanism in DashboardEventEmitter to emit structured
MatrixNode events for all 15 pipeline steps.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .event_emitter import DashboardEventEmitter, EventType, DashboardEvent
from ..core.matrix_node import MatrixNode, MatrixNodeType, MatrixNodeMetadata


@dataclass
class StepMetrics:
    """Metrics for a single pipeline step."""
    step_number: int
    step_name: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    items_generated: int = 0
    nodes_emitted: List[str] = field(default_factory=list)


class MatrixEventBridge:
    """
    Bridge between RE pipeline and matrix visualization.

    Converts pipeline artifacts (requirements, user stories, diagrams, etc.)
    into standardized MatrixNode format and emits them to the dashboard.

    Usage:
        emitter = DashboardEventEmitter()
        bridge = MatrixEventBridge(emitter)

        # During pipeline execution:
        bridge.begin_step(6, "data_dictionary")
        await bridge.emit_data_dictionary(data_dict)
        bridge.end_step(6)

    The bridge uses the emitter's callback mechanism (add_callback) to hook
    into events without modifying core emission logic.
    """

    def __init__(self, emitter: DashboardEventEmitter):
        """
        Initialize the bridge with a DashboardEventEmitter.

        Args:
            emitter: The event emitter to use for broadcasting
        """
        self.emitter = emitter
        self._matrix_nodes: Dict[str, MatrixNode] = {}
        self._step_metrics: Dict[int, StepMetrics] = {}
        self._callbacks: List[Callable] = []
        self._current_step: Optional[int] = None

        # Register ourselves as a callback to track events
        emitter.add_callback(self._on_event)

    def add_callback(self, callback: Callable[[MatrixNode], None]):
        """Add a callback for local MatrixNode event handling."""
        self._callbacks.append(callback)

    def _on_event(self, event: DashboardEvent):
        """Internal callback for tracking emitted events."""
        # Can be used for logging/metrics
        pass

    async def _emit_matrix_node(self, node: MatrixNode, event_type: EventType = EventType.MATRIX_NODE_ADDED):
        """
        Emit a MatrixNode to the dashboard.

        Args:
            node: The MatrixNode to emit
            event_type: The event type to use (default: MATRIX_NODE_ADDED)
        """
        # Store the node
        self._matrix_nodes[node.id] = node

        # Update step metrics
        if self._current_step is not None and self._current_step in self._step_metrics:
            self._step_metrics[self._current_step].nodes_emitted.append(node.id)
            self._step_metrics[self._current_step].items_generated += 1

        # Emit via emitter
        await self.emitter.emit(event_type, {
            "matrix_node": node.to_dict(),
            "step_number": node.metadata.step_number,
            "pass_name": node.metadata.pass_name
        })

        # Call local callbacks
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(node)
                else:
                    callback(node)
            except Exception as e:
                print(f"[MatrixBridge] Callback error: {e}")

    def begin_step(self, step_number: int, step_name: str):
        """
        Mark the beginning of a pipeline step.

        Args:
            step_number: The step number (1-15)
            step_name: Human-readable step name
        """
        self._current_step = step_number
        self._step_metrics[step_number] = StepMetrics(step_number, step_name)

    def end_step(self, step_number: int) -> StepMetrics:
        """
        Mark the end of a pipeline step.

        Args:
            step_number: The step number (1-15)

        Returns:
            StepMetrics for the completed step
        """
        if step_number in self._step_metrics:
            self._step_metrics[step_number].completed_at = datetime.now().isoformat()
            return self._step_metrics[step_number]
        return StepMetrics(step_number, "unknown")

    def get_all_nodes(self) -> Dict[str, MatrixNode]:
        """Get all emitted MatrixNodes."""
        return self._matrix_nodes.copy()

    def get_step_metrics(self, step_number: int) -> Optional[StepMetrics]:
        """Get metrics for a specific step."""
        return self._step_metrics.get(step_number)

    # ============================================
    # Step 6: Data Dictionary
    # ============================================

    async def emit_data_dictionary(self, data_dict, step: int = 6):
        """
        Emit data dictionary entities as MatrixNodes.

        Args:
            data_dict: DataDictionary object with entities
            step: Step number (default 6)
        """
        self.begin_step(step, "data_dictionary")

        entities = getattr(data_dict, 'entities', [])
        if isinstance(entities, dict):
            entities = list(entities.values())

        for entity in entities:
            node = MatrixNode.from_data_entity(entity, step)
            await self._emit_matrix_node(node)

        # Emit step complete summary
        await self.emitter.data_dictionary_generated(
            entity_count=len(entities),
            relationship_count=len(getattr(data_dict, 'relationships', []))
        )

        self.end_step(step)

    # ============================================
    # Step 7: Tech Stack
    # ============================================

    async def emit_tech_stack(self, tech_stack, step: int = 7):
        """
        Emit tech stack recommendation as MatrixNode.

        Args:
            tech_stack: TechStack object
            step: Step number (default 7)
        """
        self.begin_step(step, "tech_stack")

        node = MatrixNode.from_tech_stack(tech_stack, step)
        await self._emit_matrix_node(node)

        backend = getattr(tech_stack, 'backend_framework', 'Unknown')
        frontend = getattr(tech_stack, 'frontend_framework', 'Unknown')
        database = getattr(tech_stack, 'database', 'Unknown')

        await self.emitter.tech_stack_generated(backend, frontend, database)

        self.end_step(step)

    # ============================================
    # Step 9: UX Design
    # ============================================

    async def emit_ux_design(self, ux_spec, step: int = 9):
        """
        Emit UX design artifacts (personas, user flows) as MatrixNodes.

        Args:
            ux_spec: UXSpec object with personas and user_flows
            step: Step number (default 9)
        """
        self.begin_step(step, "ux_design")

        # Emit personas
        personas = getattr(ux_spec, 'personas', [])
        for persona in personas:
            node = MatrixNode.from_persona(persona, step)
            await self._emit_matrix_node(node)

        # Emit user flows
        flows = getattr(ux_spec, 'user_flows', [])
        for flow in flows:
            node = MatrixNode.from_user_flow(flow, step)
            await self._emit_matrix_node(node, EventType.DIAGRAM_GENERATED)

        await self.emitter.ux_design_generated(
            persona_count=len(personas),
            flow_count=len(flows)
        )

        self.end_step(step)

    # ============================================
    # Step 10: UI Design
    # ============================================

    async def emit_ui_design(self, ui_spec, step: int = 10):
        """
        Emit UI design artifacts (components, screens) as MatrixNodes.

        Args:
            ui_spec: UISpec object with components and screens
            step: Step number (default 10)
        """
        self.begin_step(step, "ui_design")

        # Emit components
        components = getattr(ui_spec, 'components', [])
        for component in components:
            node = MatrixNode.from_component(component, step)
            await self._emit_matrix_node(node)

        # Emit screens
        screens = getattr(ui_spec, 'screens', [])
        for screen in screens:
            node = MatrixNode.from_screen(screen, step)
            await self._emit_matrix_node(node)

        await self.emitter.ui_design_generated(
            component_count=len(components),
            screen_count=len(screens)
        )

        self.end_step(step)

    # ============================================
    # Step 11: Diagrams
    # ============================================

    async def emit_diagrams(self, journal, step: int = 11):
        """
        Emit all Mermaid diagrams from requirements as MatrixNodes.

        Args:
            journal: RequirementJournal with nodes containing mermaid_diagrams
            step: Step number (default 11)
        """
        self.begin_step(step, "diagrams")

        diagram_count = 0
        nodes = getattr(journal, 'nodes', {})

        for req_id, req in nodes.items():
            diagrams = getattr(req, 'mermaid_diagrams', {})
            for diagram_type, mermaid_code in diagrams.items():
                if mermaid_code:
                    node = MatrixNode.from_diagram(
                        req.requirement_id if hasattr(req, 'requirement_id') else req_id,
                        diagram_type,
                        mermaid_code,
                        step
                    )
                    await self._emit_matrix_node(node, EventType.DIAGRAM_GENERATED)
                    diagram_count += 1

        await self.emitter.matrix_step_complete(step, "diagrams", diagram_count)
        self.end_step(step)

    # ============================================
    # Step 12: Work Breakdown
    # ============================================

    async def emit_work_breakdown(self, breakdown, step: int = 12):
        """
        Emit work breakdown structure as MatrixNodes.

        Args:
            breakdown: FeatureBreakdown object with features/work packages
            step: Step number (default 12)
        """
        self.begin_step(step, "work_breakdown")

        # Handle different breakdown structures
        features = getattr(breakdown, 'features', {})
        if not features:
            features = getattr(breakdown, 'work_packages', {})

        if isinstance(features, list):
            features = {str(i): f for i, f in enumerate(features)}

        for feature_id, feature in features.items():
            node = MatrixNode.from_work_package(feature, feature_id, step)
            await self._emit_matrix_node(node)

        await self.emitter.work_breakdown_generated(package_count=len(features))
        self.end_step(step)

    # ============================================
    # Step 13: Task List
    # ============================================

    async def emit_task_list(self, task_breakdown, step: int = 13):
        """
        Emit task list as MatrixNodes.

        Args:
            task_breakdown: TaskBreakdown object with tasks per feature
            step: Step number (default 13)
        """
        self.begin_step(step, "task_list")

        task_count = 0
        total_hours = 0.0

        # Handle different task breakdown structures
        feature_tasks = getattr(task_breakdown, 'feature_tasks', {})
        if not feature_tasks:
            feature_tasks = getattr(task_breakdown, 'tasks', {})

        if isinstance(feature_tasks, list):
            feature_tasks = {"default": feature_tasks}

        for feature_id, tasks in feature_tasks.items():
            if isinstance(tasks, list):
                for task in tasks:
                    node = MatrixNode.from_task(task, feature_id, step)
                    await self._emit_matrix_node(node)
                    task_count += 1
                    total_hours += task.get('hours', 0) if isinstance(task, dict) else getattr(task, 'hours', 0)

        await self.emitter.task_list_generated(task_count, total_hours)
        self.end_step(step)

    # ============================================
    # Step 14: Reports
    # ============================================

    async def emit_reports(self, validation_path: str, traceability_path: str, step: int = 14):
        """
        Emit report generation complete event.

        Args:
            validation_path: Path to validation report
            traceability_path: Path to traceability matrix
            step: Step number (default 14)
        """
        self.begin_step(step, "reports")

        report_paths = [validation_path, traceability_path]

        # Create report nodes
        for path in report_paths:
            report_name = path.split('/')[-1].split('\\')[-1].replace('.md', '')
            node = MatrixNode(
                id=f"REPORT-{report_name}",
                type=MatrixNodeType.REPORT,
                row="reports",
                column="report",
                title=report_name.replace('_', ' ').title(),
                content={"path": path},
                metadata=MatrixNodeMetadata(
                    step_number=step,
                    pass_name="validation"
                )
            )
            await self._emit_matrix_node(node)

        await self.emitter.reports_generated(report_paths)
        self.end_step(step)

    # ============================================
    # Step 15: Self-Critique
    # ============================================

    async def emit_critique(self, critique_result, step: int = 15):
        """
        Emit self-critique results.

        Args:
            critique_result: CritiqueResult object with quality score and issues
            step: Step number (default 15)
        """
        self.begin_step(step, "critique")

        quality_score = getattr(critique_result, 'quality_score', 0.0)
        issues = getattr(critique_result, 'issues', [])
        issue_count = len(issues)

        # Count critical/high issues
        critical_count = sum(
            1 for issue in issues
            if getattr(issue, 'severity', issue.get('severity', '') if isinstance(issue, dict) else '')
            in ['critical', 'high']
        )

        await self.emitter.critique_complete(quality_score, issue_count, critical_count)
        await self.emitter.quality_gate(
            gate_name="self_critique",
            status="pass" if quality_score >= 7.0 else "review" if quality_score >= 4.0 else "fail",
            metrics={
                "quality_score": quality_score,
                "total_issues": issue_count,
                "critical_high_issues": critical_count
            }
        )

        self.end_step(step)

    # ============================================
    # Convenience Methods
    # ============================================

    async def emit_requirement(self, req, step: int = 3):
        """Emit a single requirement as MatrixNode."""
        node = MatrixNode.from_requirement(req, step)
        await self._emit_matrix_node(node)

    async def emit_user_story(self, story, parent_req_id: str, step: int = 4):
        """Emit a single user story as MatrixNode."""
        node = MatrixNode.from_user_story(story, parent_req_id, step)
        await self._emit_matrix_node(node)

    async def emit_epic(self, epic, step: int = 4):
        """Emit a single epic as MatrixNode."""
        node = MatrixNode.from_epic(epic, step)
        await self._emit_matrix_node(node)

    async def emit_test_case(self, test, parent_req_id: str, step: int = 8):
        """Emit a single test case as MatrixNode."""
        node = MatrixNode.from_test_case(test, parent_req_id, step)
        await self._emit_matrix_node(node)

    async def emit_api_endpoint(self, endpoint, parent_req_id: str, step: int = 5):
        """Emit a single API endpoint as MatrixNode."""
        node = MatrixNode.from_api_endpoint(endpoint, parent_req_id, step)
        await self._emit_matrix_node(node)
