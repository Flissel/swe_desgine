"""
Dashboard Event Emitter - Broadcasts events to connected dashboard clients.

Provides a simple interface for the RE pipeline to emit events
that are displayed in real-time on the dashboard.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EventType(Enum):
    """Types of events that can be emitted."""
    # Pipeline events
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_ERROR = "pipeline_error"
    PIPELINE_PROGRESS = "pipeline_progress"

    # Pass events
    PASS_STARTED = "pass_started"
    PASS_COMPLETE = "pass_complete"

    # Requirement events
    REQUIREMENT_ADDED = "requirement_added"
    REQUIREMENT_PROCESSING = "requirement_processing"
    REQUIREMENT_COMPLETE = "requirement_complete"

    # Artifact events
    USER_STORY_GENERATED = "user_story_generated"
    EPIC_GENERATED = "epic_generated"
    DIAGRAM_GENERATED = "diagram_generated"
    API_SPEC_GENERATED = "api_spec_generated"
    TEST_GENERATED = "test_generated"

    # Quality events
    QUALITY_GATE = "quality_gate"
    VALIDATION_RESULT = "validation_result"

    # Log events
    LOG_INFO = "log_info"
    LOG_WARN = "log_warn"
    LOG_ERROR = "log_error"

    # Canvas events
    NODE_POSITION = "node_position"
    CANVAS_STATE = "canvas_state"

    # Kilo Agent events
    KILO_TASK_REQUESTED = "kilo_task_requested"
    KILO_TASK_PROCESSING = "kilo_task_processing"
    KILO_TASK_COMPLETE = "kilo_task_complete"
    KILO_TASK_ERROR = "kilo_task_error"
    DIAGRAM_UPDATED = "diagram_updated"
    CONTENT_UPDATED = "content_updated"

    # Change Propagation events
    FILE_CHANGED = "file_changed"
    PROPAGATION_INITIALIZED = "propagation_initialized"
    PROPAGATION_SUGGESTION = "propagation_suggestion"
    PROPAGATION_APPLIED = "propagation_applied"
    PROPAGATION_REJECTED = "propagation_rejected"
    PROPAGATION_ERROR = "propagation_error"
    FILE_WATCHING_STARTED = "file_watching_started"
    FILE_WATCHING_STOPPED = "file_watching_stopped"

    # Auto-Link events
    ORPHANS_DETECTED = "orphans_detected"
    LINK_SUGGESTION = "link_suggestion"
    LINK_CREATED = "link_created"
    LINK_REJECTED = "link_rejected"

    # Wizard Validation & Improvement events
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PROGRESS = "validation_progress"
    VALIDATION_REQUIREMENT_RESULT = "validation_requirement_result"
    VALIDATION_COMPLETE = "validation_complete"
    DECISION_MADE = "decision_made"
    REWRITE_STARTED = "rewrite_started"
    REWRITE_PROGRESS = "rewrite_progress"
    REWRITE_COMPLETE = "rewrite_complete"
    CLARIFICATION_NEEDED = "clarification_needed"
    CLARIFICATION_ANSWERED = "clarification_answered"
    REQUIREMENT_SPLIT = "requirement_split"
    IMPROVEMENT_ITERATION = "improvement_iteration"

    # Matrix Event Types (Steps 6-15)
    DATA_DICTIONARY_GENERATED = "data_dictionary_generated"
    TECH_STACK_GENERATED = "tech_stack_generated"
    UX_DESIGN_GENERATED = "ux_design_generated"
    UI_DESIGN_GENERATED = "ui_design_generated"
    WORK_BREAKDOWN_GENERATED = "work_breakdown_generated"
    TASK_LIST_GENERATED = "task_list_generated"
    REPORTS_GENERATED = "reports_generated"
    CRITIQUE_COMPLETE = "critique_complete"
    MATRIX_NODE_ADDED = "matrix_node_added"
    MATRIX_STEP_COMPLETE = "matrix_step_complete"

    # Layout Generation Events (Interactive Selection)
    LAYOUT_ANALYSIS_STARTED = "layout_analysis_started"
    LAYOUT_ANALYSIS_COMPLETE = "layout_analysis_complete"
    LAYOUT_VARIANTS_READY = "layout_variants_ready"
    LAYOUT_SELECTED = "layout_selected"
    LAYOUT_REFINEMENT_READY = "layout_refinement_ready"
    LAYOUT_FINALIZED = "layout_finalized"

    # Edit Modal Events (Kilo Agent Integration)
    EDIT_MODAL_OPENED = "edit_modal_opened"
    EDIT_MODAL_CLOSED = "edit_modal_closed"
    EDIT_KILO_SUBMITTED = "edit_kilo_submitted"
    EDIT_KILO_PROCESSING = "edit_kilo_processing"
    EDIT_KILO_COMPLETE = "edit_kilo_complete"
    EDIT_KILO_ERROR = "edit_kilo_error"
    EDIT_SAVED = "edit_saved"

    # Change Request Notification Events (Domino Effect)
    CHANGE_REQUEST_CREATED = "change_request_created"
    CHANGE_REQUEST_UPDATED = "change_request_updated"
    CHANGE_REQUEST_APPROVED = "change_request_approved"
    CHANGE_REQUEST_REJECTED = "change_request_rejected"
    CHANGE_REQUEST_APPLIED = "change_request_applied"
    IMPACT_ANALYSIS_STARTED = "impact_analysis_started"
    IMPACT_ANALYSIS_COMPLETE = "impact_analysis_complete"

    # Wizard Agent Enrichment Events
    WIZARD_SUGGESTION_PENDING = "wizard_suggestion_pending"
    WIZARD_SUGGESTION_AUTO_APPLIED = "wizard_suggestion_auto_applied"
    WIZARD_SUGGESTION_APPROVED = "wizard_suggestion_approved"
    WIZARD_SUGGESTION_REJECTED = "wizard_suggestion_rejected"
    WIZARD_ENRICHMENT_STARTED = "wizard_enrichment_started"
    WIZARD_ENRICHMENT_COMPLETE = "wizard_enrichment_complete"

    # Pipeline Stage I/O Events
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    STAGE_SKIPPED = "stage_skipped"


@dataclass
class DashboardEvent:
    """A single event to be sent to the dashboard."""
    type: EventType
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        """Convert to JSON for WebSocket transmission."""
        return json.dumps({
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp
        })


class DashboardEventEmitter:
    """
    Broadcasts events to connected dashboard clients.

    Usage:
        emitter = DashboardEventEmitter()

        # In your pipeline code:
        await emitter.emit(EventType.REQUIREMENT_ADDED, {"req_id": "REQ-001", ...})

        # Or use convenience methods:
        await emitter.log_info("Processing started")
        await emitter.requirement_added(requirement)
        await emitter.diagram_generated(req_id, "flowchart", mermaid_code)
    """

    def __init__(self):
        self.clients: List[Any] = []  # WebSocket connections
        self.event_history: List[DashboardEvent] = []
        self.max_history = 1000
        self._callbacks: List[Callable] = []

    def add_client(self, client):
        """Add a WebSocket client."""
        self.clients.append(client)

    def remove_client(self, client):
        """Remove a WebSocket client."""
        if client in self.clients:
            self.clients.remove(client)

    def add_callback(self, callback: Callable):
        """Add a callback for local event handling."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        """Remove a previously added callback."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    async def emit(self, event_type: EventType, data: Dict[str, Any]):
        """
        Emit an event to all connected clients.

        Args:
            event_type: Type of event
            data: Event data
        """
        event = DashboardEvent(type=event_type, data=data)

        # Store in history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)

        # Send to WebSocket clients
        message = event.to_json()
        disconnected = []

        for client in self.clients:
            try:
                # aiohttp WebSocket uses send_str, not send
                await client.send_str(message)
                print(f"[EMIT] Sent {event_type.value} to client")
            except Exception as e:
                print(f"[EMIT] Failed to send to client: {e}")
                disconnected.append(client)

        # Remove disconnected clients
        for client in disconnected:
            self.remove_client(client)

        # Call local callbacks
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                print(f"Callback error: {e}")

    # ============ Convenience Methods ============

    async def log_info(self, message: str):
        """Emit an info log message."""
        await self.emit(EventType.LOG_INFO, {"message": message, "level": "info"})

    async def log_warn(self, message: str):
        """Emit a warning log message."""
        await self.emit(EventType.LOG_WARN, {"message": message, "level": "warn"})

    async def log_error(self, message: str):
        """Emit an error log message."""
        await self.emit(EventType.LOG_ERROR, {"message": message, "level": "error"})

    async def pipeline_started(self, project_name: str, mode: str):
        """Emit pipeline started event."""
        await self.emit(EventType.PIPELINE_STARTED, {
            "project_name": project_name,
            "mode": mode
        })

    async def pipeline_complete(self, summary: Dict[str, Any]):
        """Emit pipeline complete event."""
        await self.emit(EventType.PIPELINE_COMPLETE, {"summary": summary})

    async def pipeline_progress(self, step: int, total: int, description: str,
                                cost_usd: float = 0.0, total_tokens: int = 0):
        """Emit pipeline progress event for step-by-step tracking."""
        await self.emit(EventType.PIPELINE_PROGRESS, {
            "step": step,
            "total": total,
            "description": description,
            "percent": int((step / total) * 100) if total > 0 else 0,
            "cost_usd": round(cost_usd, 4),
            "total_tokens": total_tokens
        })

    async def pass_started(self, pass_name: str, pass_number: int):
        """Emit pass started event."""
        await self.emit(EventType.PASS_STARTED, {
            "pass_name": pass_name,
            "pass_number": pass_number
        })

    async def pass_complete(self, pass_name: str, pass_number: int, metrics: Dict[str, float]):
        """Emit pass complete event."""
        await self.emit(EventType.PASS_COMPLETE, {
            "pass_name": pass_name,
            "pass_number": pass_number,
            "metrics": metrics
        })

    async def requirement_added(self, req_id: str, title: str, req_type: str, priority: str):
        """Emit requirement added event."""
        await self.emit(EventType.REQUIREMENT_ADDED, {
            "req_id": req_id,
            "title": title,
            "type": req_type,
            "priority": priority
        })

    async def requirement_processing(self, req_id: str, stage: str):
        """Emit requirement processing event."""
        await self.emit(EventType.REQUIREMENT_PROCESSING, {
            "req_id": req_id,
            "stage": stage
        })

    async def user_story_generated(self, us_id: str, title: str, persona: str, parent_req: str):
        """Emit user story generated event."""
        await self.emit(EventType.USER_STORY_GENERATED, {
            "us_id": us_id,
            "title": title,
            "persona": persona,
            "parent_req": parent_req
        })

    async def epic_generated(self, epic_id: str, title: str, requirements: List[str]):
        """Emit epic generated event."""
        await self.emit(EventType.EPIC_GENERATED, {
            "epic_id": epic_id,
            "title": title,
            "requirements": requirements
        })

    async def diagram_generated(self, req_id: str, diagram_type: str, mermaid_code: str):
        """Emit diagram generated event."""
        await self.emit(EventType.DIAGRAM_GENERATED, {
            "req_id": req_id,
            "diagram_type": diagram_type,
            "mermaid_code": mermaid_code
        })

    async def api_spec_generated(self, endpoint: str, method: str, path: str):
        """Emit API spec generated event."""
        await self.emit(EventType.API_SPEC_GENERATED, {
            "endpoint": endpoint,
            "method": method,
            "path": path
        })

    async def test_generated(self, test_id: str, title: str, test_type: str, parent_req: str):
        """Emit test generated event."""
        await self.emit(EventType.TEST_GENERATED, {
            "test_id": test_id,
            "title": title,
            "test_type": test_type,
            "parent_req": parent_req
        })

    async def quality_gate(self, gate_name: str, status: str, metrics: Dict[str, float]):
        """Emit quality gate event."""
        await self.emit(EventType.QUALITY_GATE, {
            "gate_name": gate_name,
            "status": status,
            "metrics": metrics
        })

    def get_history(self) -> List[Dict[str, Any]]:
        """Get event history for replay on client connect."""
        return [
            {
                "type": e.type.value,
                "data": e.data,
                "timestamp": e.timestamp
            }
            for e in self.event_history
        ]

    # ============ Kilo Agent Methods ============

    async def kilo_task_processing(self, node_id: str, task: str):
        """Emit Kilo task processing event."""
        await self.emit(EventType.KILO_TASK_PROCESSING, {
            "node_id": node_id,
            "task": task
        })

    async def kilo_task_complete(self, node_id: str, result: Dict[str, Any]):
        """Emit Kilo task complete event."""
        await self.emit(EventType.KILO_TASK_COMPLETE, {
            "node_id": node_id,
            "result": result
        })

    async def kilo_task_error(self, node_id: str, error: str):
        """Emit Kilo task error event."""
        await self.emit(EventType.KILO_TASK_ERROR, {
            "node_id": node_id,
            "error": error
        })

    async def diagram_updated(self, node_id: str, mermaid_code: str, file_path: str):
        """Emit diagram updated event."""
        await self.emit(EventType.DIAGRAM_UPDATED, {
            "node_id": node_id,
            "mermaid_code": mermaid_code,
            "file_path": file_path,
            "success": True
        })

    async def content_updated(self, node_id: str, content: str, content_type: str):
        """Emit content updated event."""
        await self.emit(EventType.CONTENT_UPDATED, {
            "node_id": node_id,
            "content": content,
            "content_type": content_type,
            "success": True
        })

    # ============ Change Propagation Methods ============

    async def file_changed(self, file_path: str, file_type: str, change_type: str, affected_nodes: List[str], diff_summary: str = ""):
        """Emit file changed event."""
        await self.emit(EventType.FILE_CHANGED, {
            "file_path": file_path,
            "file_type": file_type,
            "change_type": change_type,
            "affected_nodes": affected_nodes,
            "diff_summary": diff_summary
        })

    async def propagation_suggestion(self, suggestion_data: Dict[str, Any]):
        """Emit propagation suggestion event."""
        await self.emit(EventType.PROPAGATION_SUGGESTION, suggestion_data)

    async def propagation_applied(self, suggestion_id: str, target_node_id: str):
        """Emit propagation applied event."""
        await self.emit(EventType.PROPAGATION_APPLIED, {
            "id": suggestion_id,
            "target_node_id": target_node_id
        })

    async def propagation_rejected(self, suggestion_id: str, target_node_id: str):
        """Emit propagation rejected event."""
        await self.emit(EventType.PROPAGATION_REJECTED, {
            "id": suggestion_id,
            "target_node_id": target_node_id
        })

    # ============ Auto-Link Methods ============

    async def orphans_detected(self, count: int, orphan_ids: List[str]):
        """Emit orphans detected event."""
        await self.emit(EventType.ORPHANS_DETECTED, {
            "count": count,
            "orphan_ids": orphan_ids
        })

    async def link_suggestion(self, suggestion_data: Dict[str, Any]):
        """Emit link suggestion event."""
        await self.emit(EventType.LINK_SUGGESTION, suggestion_data)

    async def link_created(self, suggestion_id: str, orphan_node_id: str, target_node_id: str, link_type: str):
        """Emit link created event."""
        await self.emit(EventType.LINK_CREATED, {
            "id": suggestion_id,
            "orphan_node_id": orphan_node_id,
            "target_node_id": target_node_id,
            "link_type": link_type
        })

    async def link_rejected(self, suggestion_id: str, orphan_node_id: str):
        """Emit link rejected event."""
        await self.emit(EventType.LINK_REJECTED, {
            "id": suggestion_id,
            "orphan_node_id": orphan_node_id
        })

    # ============ Wizard Validation Methods ============

    async def validation_started(self, total_count: int, mode: str = "AUTO"):
        """Emit validation started event."""
        await self.emit(EventType.VALIDATION_STARTED, {
            "total_count": total_count,
            "mode": mode
        })

    async def validation_progress(self, completed: int, total: int, message: str, stage: str = "validating"):
        """Emit validation progress event."""
        await self.emit(EventType.VALIDATION_PROGRESS, {
            "completed": completed,
            "total": total,
            "message": message,
            "stage": stage,
            "percent": int((completed / total) * 100) if total > 0 else 0
        })

    async def validation_requirement_result(self, req_id: str, score: float, verdict: str, evaluation: list):
        """Emit single requirement validation result."""
        await self.emit(EventType.VALIDATION_REQUIREMENT_RESULT, {
            "req_id": req_id,
            "score": score,
            "verdict": verdict,
            "evaluation": evaluation
        })

    async def validation_complete(self, passed_count: int, failed_count: int, total_time_ms: int):
        """Emit validation complete event."""
        await self.emit(EventType.VALIDATION_COMPLETE, {
            "passed_count": passed_count,
            "failed_count": failed_count,
            "total_time_ms": total_time_ms
        })

    async def decision_made(self, req_id: str, action: str, reason: str, confidence: float = 0.0):
        """Emit decision made event (SPLIT/REWRITE/ACCEPT/CLARIFY/REJECT)."""
        await self.emit(EventType.DECISION_MADE, {
            "req_id": req_id,
            "action": action,
            "reason": reason,
            "confidence": confidence
        })

    async def rewrite_started(self, req_id: str, original_title: str):
        """Emit rewrite started event."""
        await self.emit(EventType.REWRITE_STARTED, {
            "req_id": req_id,
            "original_title": original_title
        })

    async def rewrite_complete(self, req_id: str, original_title: str, new_title: str, score_before: float, score_after: float):
        """Emit rewrite complete event."""
        await self.emit(EventType.REWRITE_COMPLETE, {
            "req_id": req_id,
            "original_title": original_title,
            "new_title": new_title,
            "score_before": score_before,
            "score_after": score_after
        })

    async def clarification_needed(self, req_id: str, questions: list):
        """Emit clarification needed event."""
        await self.emit(EventType.CLARIFICATION_NEEDED, {
            "req_id": req_id,
            "questions": questions
        })

    async def clarification_answered(self, req_id: str, criterion: str, answer: str):
        """Emit clarification answered event."""
        await self.emit(EventType.CLARIFICATION_ANSWERED, {
            "req_id": req_id,
            "criterion": criterion,
            "answer": answer
        })

    async def requirement_split(self, original_req_id: str, new_requirements: list):
        """Emit requirement split event."""
        await self.emit(EventType.REQUIREMENT_SPLIT, {
            "original_req_id": original_req_id,
            "new_requirements": new_requirements
        })

    async def improvement_iteration(self, iteration: int, max_iterations: int, pass_rate: float):
        """Emit improvement iteration event."""
        await self.emit(EventType.IMPROVEMENT_ITERATION, {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "pass_rate": pass_rate
        })

    # ============ Matrix Event Methods (Steps 6-15) ============

    async def data_dictionary_generated(self, entity_count: int, relationship_count: int = 0):
        """Emit data dictionary generated event (Step 6)."""
        await self.emit(EventType.DATA_DICTIONARY_GENERATED, {
            "entity_count": entity_count,
            "relationship_count": relationship_count,
            "step": 6
        })

    async def tech_stack_generated(self, backend: str, frontend: str, database: str):
        """Emit tech stack generated event (Step 7)."""
        await self.emit(EventType.TECH_STACK_GENERATED, {
            "backend": backend,
            "frontend": frontend,
            "database": database,
            "step": 7
        })

    async def ux_design_generated(self, persona_count: int, flow_count: int):
        """Emit UX design generated event (Step 9)."""
        await self.emit(EventType.UX_DESIGN_GENERATED, {
            "persona_count": persona_count,
            "user_flow_count": flow_count,
            "step": 9
        })

    async def ui_design_generated(self, component_count: int, screen_count: int):
        """Emit UI design generated event (Step 10)."""
        await self.emit(EventType.UI_DESIGN_GENERATED, {
            "component_count": component_count,
            "screen_count": screen_count,
            "step": 10
        })

    async def work_breakdown_generated(self, package_count: int):
        """Emit work breakdown generated event (Step 12)."""
        await self.emit(EventType.WORK_BREAKDOWN_GENERATED, {
            "package_count": package_count,
            "step": 12
        })

    async def task_list_generated(self, task_count: int, total_hours: float):
        """Emit task list generated event (Step 13)."""
        await self.emit(EventType.TASK_LIST_GENERATED, {
            "task_count": task_count,
            "total_hours": total_hours,
            "step": 13
        })

    async def reports_generated(self, report_paths: List[str]):
        """Emit reports generated event (Step 14)."""
        await self.emit(EventType.REPORTS_GENERATED, {
            "report_paths": report_paths,
            "step": 14
        })

    async def critique_complete(self, quality_score: float, issue_count: int, critical_count: int = 0):
        """Emit critique complete event (Step 15)."""
        await self.emit(EventType.CRITIQUE_COMPLETE, {
            "quality_score": quality_score,
            "issue_count": issue_count,
            "critical_count": critical_count,
            "step": 15
        })

    async def matrix_node_added(self, node_data: Dict[str, Any]):
        """Emit matrix node added event for real-time visualization."""
        await self.emit(EventType.MATRIX_NODE_ADDED, node_data)

    async def matrix_step_complete(self, step_number: int, step_name: str, node_count: int):
        """Emit matrix step complete event."""
        await self.emit(EventType.MATRIX_STEP_COMPLETE, {
            "step_number": step_number,
            "step_name": step_name,
            "node_count": node_count
        })

    # ============ Layout Generation Methods ============

    async def layout_analysis_started(self, project_name: str):
        """Emit layout analysis started event."""
        await self.emit(EventType.LAYOUT_ANALYSIS_STARTED, {
            "project_name": project_name
        })

    async def layout_analysis_complete(self, recommended_layout: str, domains: List[Dict], complexity: float):
        """Emit layout analysis complete event."""
        await self.emit(EventType.LAYOUT_ANALYSIS_COMPLETE, {
            "recommended_layout": recommended_layout,
            "domains": domains,
            "complexity_score": complexity
        })

    async def layout_variants_ready(self, stage: int, variants: List[Dict]):
        """Emit layout variants ready event - triggers selection modal in dashboard."""
        await self.emit(EventType.LAYOUT_VARIANTS_READY, {
            "stage": stage,
            "variants": variants,
            "selection_required": True
        })

    async def layout_selected(self, variant_id: str, stage: int):
        """Emit layout selected event."""
        await self.emit(EventType.LAYOUT_SELECTED, {
            "variant_id": variant_id,
            "stage": stage
        })

    async def layout_refinement_ready(self, stage: int, base_variant: str, variants: List[Dict]):
        """Emit layout refinement variants ready event."""
        await self.emit(EventType.LAYOUT_REFINEMENT_READY, {
            "stage": stage,
            "base_variant": base_variant,
            "variants": variants,
            "selection_required": True
        })

    async def layout_finalized(self, variant_id: str, layout_type: str, aggregations: List[Dict], columns: List[Dict]):
        """Emit layout finalized event with full layout data."""
        await self.emit(EventType.LAYOUT_FINALIZED, {
            "variant_id": variant_id,
            "layout_type": layout_type,
            "aggregations": aggregations,
            "columns": columns
        })

    # ============ Raw Emit (for dynamic event types) ============

    async def emit_raw(self, event_type_str: str, data: Dict[str, Any]):
        """Emit an event using a string type name (for dynamic/plugin events)."""
        # Try to find matching EventType enum
        try:
            event_type = EventType(event_type_str)
        except ValueError:
            # Not in enum - emit directly as raw string
            event_type = None

        if event_type:
            await self.emit(event_type, data)
        else:
            # Fallback: broadcast raw without enum
            import json as _json
            message = _json.dumps({
                "type": event_type_str,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
            disconnected = []
            for client in self.clients:
                try:
                    await client.send_str(message)
                except Exception:
                    disconnected.append(client)
            for client in disconnected:
                self.remove_client(client)

    # ============ Wizard Agent Enrichment Methods ============

    async def wizard_enrichment_started(self, step: int, team_name: str):
        """Emit wizard enrichment started event."""
        await self.emit(EventType.WIZARD_ENRICHMENT_STARTED, {
            "step": step,
            "team": team_name
        })

    async def wizard_enrichment_complete(self, step: int, auto_applied: int, pending: int):
        """Emit wizard enrichment complete event."""
        await self.emit(EventType.WIZARD_ENRICHMENT_COMPLETE, {
            "step": step,
            "auto_applied": auto_applied,
            "pending": pending
        })

    # ============ Pipeline Stage I/O Methods ============

    async def stage_started(self, step, name: str, description: str,
                            inputs: List[Dict[str, Any]] = None):
        """Emit stage started event with inputs."""
        await self.emit(EventType.STAGE_STARTED, {
            "step": step,
            "name": name,
            "description": description,
            "inputs": inputs or [],
        })

    async def stage_completed(self, step, name: str,
                              outputs: List[Dict[str, Any]] = None,
                              duration_ms: int = 0, cost_usd: float = 0.0):
        """Emit stage completed event with outputs."""
        await self.emit(EventType.STAGE_COMPLETED, {
            "step": step,
            "name": name,
            "outputs": outputs or [],
            "duration_ms": duration_ms,
            "cost_usd": round(cost_usd, 4),
        })

    async def stage_failed(self, step, name: str, error: str):
        """Emit stage failed event."""
        await self.emit(EventType.STAGE_FAILED, {
            "step": step,
            "name": name,
            "error": error,
        })

    async def stage_skipped(self, step, name: str, reason: str = ""):
        """Emit stage skipped event."""
        await self.emit(EventType.STAGE_SKIPPED, {
            "step": step,
            "name": name,
            "reason": reason,
        })
