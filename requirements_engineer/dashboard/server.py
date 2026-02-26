"""
Dashboard Server - HTTP and WebSocket server for the live dashboard.

Provides:
- Static file serving for the dashboard HTML/CSS/JS
- WebSocket endpoint for real-time updates
- REST API for data queries
"""

import asyncio
import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
import webbrowser

# Load .env file for API keys
try:
    from dotenv import load_dotenv
    # Load from project root
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[SERVER] Loaded .env from {env_path}")
except ImportError:
    pass  # dotenv not installed, rely on environment variables

try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from .event_emitter import DashboardEventEmitter, EventType
from .markdown_parser import (
    parse_user_stories_md,
    parse_traceability_matrix_md,
    parse_data_dictionary_md,
    parse_work_breakdown_md,
    parse_api_documentation_md,
    parse_screen_markdown_files,
    parse_state_machines_json,
    parse_infrastructure_json,
    parse_ui_compositions_json,
    parse_test_factories_json,
    parse_architecture_json,
    extract_project_name,
    extract_timestamp
)

# Import propagation module
try:
    from ..propagation import (
        PropagationEngine,
        AutoLinker,
        LinkGraph,
        LLMAnalyzer,
    )
    HAS_PROPAGATION = True
except ImportError:
    HAS_PROPAGATION = False
    print("[SERVER] Propagation module not available")


class DashboardServer:
    """
    HTTP/WebSocket server for the RE System dashboard.

    Usage:
        server = DashboardServer(port=8080)
        await server.start()

        # Access emitter for sending events
        await server.emitter.log_info("Hello from pipeline!")

        # Stop when done
        await server.stop()
    """

    def __init__(self, port: int = 8080, open_browser: bool = True):
        """
        Initialize the dashboard server.

        Args:
            port: Port to run the server on
            open_browser: Whether to open browser automatically
        """
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp required for dashboard. Install with: pip install aiohttp")

        self.port = port
        self.open_browser = open_browser
        self.emitter = DashboardEventEmitter()
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self._static_path = Path(__file__).parent / "static"

        # Shared state for canvas
        self.canvas_state: Dict[str, Any] = {
            "nodes": {},
            "connections": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1.0}
        }

        # Change Propagation & Auto-Link components
        self.propagation_engine: Optional['PropagationEngine'] = None
        self.auto_linker: Optional['AutoLinker'] = None
        self._current_project_path: Optional[Path] = None
        self._current_project_id: Optional[str] = None

        # KiloAgent Cascade Edit state
        self._cascade_results: Dict[str, Any] = {}

        # Wizard Suggestion Queue (lazy-init on first use)
        self._wizard_suggestion_queue = None

        # Pipeline execution state
        self._pipeline_task: Optional[asyncio.Task] = None
        self._pipeline_status: Dict[str, Any] = {
            "running": False, "step": 0, "total": 15,
            "description": "", "error": None, "output_dir": None,
            "project_index": 0, "project_total": 1, "project_name": ""
        }
        self._pipeline_queue: list = []  # list of {"project_path": ..., "config_path": ...}

    async def start(self):
        """Start the dashboard server."""
        self.app = web.Application()

        # Setup routes
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/wizard", self._handle_wizard)
        self.app.router.add_get("/ws", self._handle_websocket)
        self.app.router.add_get("/api/state", self._handle_get_state)
        self.app.router.add_get("/api/history", self._handle_get_history)
        self.app.router.add_get("/api/projects", self._handle_list_projects)
        self.app.router.add_get("/api/projects/{project_id}", self._handle_load_project)
        # Wizard API endpoints
        self.app.router.add_post("/api/wizard/extract", self._handle_wizard_extract)
        self.app.router.add_post("/api/wizard/generate-json", self._handle_wizard_generate_json)

        # Wizard Validation API endpoints
        self.app.router.add_post("/api/wizard/validate-batch", self._handle_wizard_validate_batch)
        self.app.router.add_post("/api/wizard/decide", self._handle_wizard_decide)
        self.app.router.add_post("/api/wizard/improve", self._handle_wizard_improve)
        self.app.router.add_post("/api/wizard/clarify", self._handle_wizard_clarify)
        self.app.router.add_post("/api/wizard/split", self._handle_wizard_split)
        self.app.router.add_post("/api/wizard/answer-clarification", self._handle_wizard_answer_clarification)

        # Wizard Auto-Enrich API endpoints (AutoGen agents)
        self.app.router.add_post("/api/wizard/auto-enrich", self._handle_wizard_auto_enrich)
        self.app.router.add_get("/api/wizard/suggestions", self._handle_wizard_get_suggestions)
        self.app.router.add_post("/api/wizard/suggestions/{suggestion_id}/approve", self._handle_wizard_approve_suggestion)
        self.app.router.add_post("/api/wizard/suggestions/{suggestion_id}/reject", self._handle_wizard_reject_suggestion)

        # Pipeline Execution API endpoints
        self.app.router.add_post("/api/pipeline/run", self._handle_pipeline_run)
        self.app.router.add_post("/api/pipeline/batch", self._handle_pipeline_batch)
        self.app.router.add_get("/api/pipeline/status", self._handle_pipeline_status)
        self.app.router.add_post("/api/pipeline/stop", self._handle_pipeline_stop)
        self.app.router.add_get("/api/pipeline/manifest", self._handle_pipeline_manifest)
        self.app.router.add_get("/api/config/validate", self._handle_config_validate)

        # Change Propagation API endpoints
        self.app.router.add_get("/api/propagation/pending", self._handle_get_pending_propagations)
        self.app.router.add_post("/api/propagation/approve/{suggestion_id}", self._handle_approve_propagation)
        self.app.router.add_post("/api/propagation/reject/{suggestion_id}", self._handle_reject_propagation)
        self.app.router.add_post("/api/propagation/start-watching", self._handle_start_watching)
        self.app.router.add_post("/api/propagation/stop-watching", self._handle_stop_watching)

        # Auto-Link API endpoints
        self.app.router.add_get("/api/links/orphans", self._handle_get_orphans)
        self.app.router.add_post("/api/links/discover", self._handle_discover_links)
        self.app.router.add_get("/api/links/pending", self._handle_get_pending_links)
        self.app.router.add_post("/api/links/approve/{suggestion_id}", self._handle_approve_link)
        self.app.router.add_post("/api/links/reject/{suggestion_id}", self._handle_reject_link)

        self.app.router.add_static("/static", self._static_path)

        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "localhost", self.port)
        await site.start()

        print(f"\n  [DASHBOARD] Running at: http://localhost:{self.port}")

        # Open browser
        if self.open_browser:
            webbrowser.open(f"http://localhost:{self.port}")

    async def stop(self):
        """Stop the dashboard server."""
        if self.runner:
            await self.runner.cleanup()

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the main dashboard HTML."""
        index_path = self._static_path / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)
        else:
            return web.Response(text="Dashboard HTML not found", status=404)

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Add client
        self.emitter.add_client(ws)
        print(f"  [WS] Dashboard client connected")

        # Send current state and history
        await ws.send_json({
            "type": "init",
            "data": {
                "canvas_state": self.canvas_state,
                "history": self.emitter.get_history()
            }
        })

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_client_message(data, ws)
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"  WebSocket error: {ws.exception()}")
        finally:
            self.emitter.remove_client(ws)
            print(f"  [WS] Dashboard client disconnected")

        return ws

    async def _handle_client_message(self, data: Dict[str, Any], ws: web.WebSocketResponse):
        """Handle messages from the dashboard client."""
        msg_type = data.get("type", "")

        if msg_type == "update_node_position":
            # Update node position in canvas state
            node_id = data.get("node_id")
            x = data.get("x", 0)
            y = data.get("y", 0)

            if node_id:
                if node_id not in self.canvas_state["nodes"]:
                    self.canvas_state["nodes"][node_id] = {}
                self.canvas_state["nodes"][node_id]["x"] = x
                self.canvas_state["nodes"][node_id]["y"] = y

                # Broadcast to other clients
                await self.emitter.emit(
                    EventType.NODE_POSITION,
                    {"node_id": node_id, "x": x, "y": y}
                )

        elif msg_type == "update_viewport":
            # Update viewport state
            self.canvas_state["viewport"] = {
                "x": data.get("x", 0),
                "y": data.get("y", 0),
                "zoom": data.get("zoom", 1.0)
            }

        elif msg_type == "kilo_task":
            # Handle Kilo Agent task request from UI
            await self._handle_kilo_task(ws, data)

        # Change Propagation WebSocket messages
        elif msg_type == "start_watching":
            project_id = data.get("project_id")
            if project_id:
                await self._init_propagation_for_project(project_id)
                await self._start_file_watching()

        elif msg_type == "stop_watching":
            await self._stop_file_watching()

        elif msg_type == "approve_propagation":
            suggestion_id = data.get("suggestion_id")
            if suggestion_id and self.propagation_engine:
                await self.propagation_engine.apply_suggestion(suggestion_id)

        elif msg_type == "reject_propagation":
            suggestion_id = data.get("suggestion_id")
            if suggestion_id and self.propagation_engine:
                await self.propagation_engine.reject_suggestion(suggestion_id)

        # Auto-Link WebSocket messages
        elif msg_type == "discover_links":
            if self.auto_linker:
                await self.auto_linker.discover_all()

        elif msg_type == "approve_link":
            suggestion_id = data.get("suggestion_id")
            if suggestion_id and self.auto_linker:
                await self.auto_linker.approve_link(suggestion_id)

        elif msg_type == "reject_link":
            suggestion_id = data.get("suggestion_id")
            if suggestion_id and self.auto_linker:
                await self.auto_linker.reject_link(suggestion_id)

        # Edit Modal WebSocket messages (Kilo Agent Integration)
        elif msg_type == "edit_node":
            # Handle node edit from modal
            await self._handle_edit_node(ws, data)

        elif msg_type == "kilo_edit_request":
            # Handle Kilo Agent request from edit modal
            await self._handle_kilo_edit_request(ws, data)

        elif msg_type == "approve_change_request":
            # Handle change request approval from notification
            await self._handle_approve_change_request(ws, data)

        elif msg_type == "reject_change_request":
            # Handle change request rejection from notification
            await self._handle_reject_change_request(ws, data)

        # KiloAgent Diagram Cascade Edit
        elif msg_type == "kilo_diagram_cascade_request":
            await self._handle_kilo_diagram_cascade(ws, data)

        elif msg_type == "approve_cascade_node":
            await self._handle_approve_cascade_node(ws, data)

        elif msg_type == "reject_cascade_node":
            await self._handle_reject_cascade_node(ws, data)

        # Wizard Suggestion WebSocket messages
        elif msg_type == "approve_wizard_suggestion":
            suggestion_id = data.get("suggestion_id")
            if suggestion_id and self._wizard_suggestion_queue:
                suggestion = await self._wizard_suggestion_queue.approve(suggestion_id)
                if suggestion:
                    await ws.send_json({
                        "type": "wizard_suggestion_approved",
                        "data": suggestion.to_dict()
                    })

        elif msg_type == "reject_wizard_suggestion":
            suggestion_id = data.get("suggestion_id")
            reason = data.get("reason", "")
            if suggestion_id and self._wizard_suggestion_queue:
                suggestion = await self._wizard_suggestion_queue.reject(suggestion_id, reason)
                if suggestion:
                    await ws.send_json({
                        "type": "wizard_suggestion_rejected",
                        "data": suggestion.to_dict()
                    })

    async def _handle_edit_node(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Handle node edit from modal."""
        node_id = data.get("node_id")
        updates = data.get("updates", {})

        if not node_id:
            return

        print(f"[SERVER] Edit node: {node_id}")

        # Update canvas state
        if node_id in self.canvas_state["nodes"]:
            if "data" not in self.canvas_state["nodes"][node_id]:
                self.canvas_state["nodes"][node_id]["data"] = {}
            self.canvas_state["nodes"][node_id]["data"].update(updates)

        # Emit event
        await self.emitter.emit(
            EventType.EDIT_SAVED,
            {"node_id": node_id, "updates": updates}
        )

    async def _handle_kilo_edit_request(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Handle Kilo Agent request from edit modal."""
        node_id = data.get("node_id")
        node_type = data.get("node_type")
        kilo_prompt = data.get("kilo_prompt")
        current_content = data.get("current_content", {})
        original_content = data.get("original_content", {})

        if not node_id or not kilo_prompt:
            return

        print(f"[SERVER] Kilo edit request: {node_id} - {kilo_prompt[:50]}...")

        # Emit processing event
        await self.emitter.emit(
            EventType.EDIT_KILO_PROCESSING,
            {"node_id": node_id, "prompt": kilo_prompt}
        )

        try:
            # Try to use gRPC client if available
            from .grpc_client import get_propagation_client

            client = get_propagation_client()
            await client.connect()

            # Process change via gRPC
            response = await client.process_change(
                project_id=self._current_project_id or "default",
                node_id=node_id,
                node_type=node_type or "unknown",
                old_content=json.dumps(original_content),
                new_content=json.dumps(current_content),
                kilo_prompt=kilo_prompt,
                max_depth=2,
            )

            if response.get("success"):
                # Send response to client
                await ws.send_json({
                    "type": "kilo_edit_response",
                    "success": True,
                    "change_id": response.get("change_id"),
                    "affected_node_ids": response.get("affected_node_ids", []),
                    "kilo_response": response.get("kilo_response", ""),
                })

                # Stream suggestions as change request notifications
                async for suggestion in client.get_suggestions(response.get("change_id")):
                    await self.emitter.emit(
                        EventType.CHANGE_REQUEST_CREATED,
                        suggestion
                    )

                # Emit complete event
                await self.emitter.emit(
                    EventType.EDIT_KILO_COMPLETE,
                    {"node_id": node_id, "change_id": response.get("change_id")}
                )
            else:
                await ws.send_json({
                    "type": "kilo_edit_response",
                    "success": False,
                    "error": response.get("error", "Unknown error"),
                })

        except ImportError:
            # gRPC not available - fall back to simple response
            print("[SERVER] gRPC client not available, using fallback")
            await ws.send_json({
                "type": "kilo_edit_response",
                "success": True,
                "affected_node_ids": [],
                "kilo_response": f"Kilo Agent nicht verfügbar. Änderung wurde lokal gespeichert.",
            })

        except Exception as e:
            print(f"[SERVER] Kilo edit error: {e}")
            await self.emitter.emit(
                EventType.EDIT_KILO_ERROR,
                {"node_id": node_id, "error": str(e)}
            )
            await ws.send_json({
                "type": "kilo_edit_response",
                "success": False,
                "error": str(e),
            })

    async def _handle_approve_change_request(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Handle change request approval."""
        suggestion_id = data.get("suggestion_id")
        if not suggestion_id:
            return

        print(f"[SERVER] Approving change request: {suggestion_id}")

        try:
            from .grpc_client import get_propagation_client

            client = get_propagation_client()
            await client.connect()

            response = await client.apply_suggestion(suggestion_id)

            if response.get("success"):
                await self.emitter.emit(
                    EventType.CHANGE_REQUEST_APPROVED,
                    {"suggestion_id": suggestion_id}
                )
            else:
                print(f"[SERVER] Failed to apply suggestion: {response.get('error')}")

        except Exception as e:
            print(f"[SERVER] Approve change request error: {e}")

    async def _handle_reject_change_request(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Handle change request rejection."""
        suggestion_id = data.get("suggestion_id")
        reason = data.get("reason", "")

        if not suggestion_id:
            return

        print(f"[SERVER] Rejecting change request: {suggestion_id}")

        try:
            from .grpc_client import get_propagation_client

            client = get_propagation_client()
            await client.connect()

            response = await client.reject_suggestion(suggestion_id, reason)

            if response.get("success"):
                await self.emitter.emit(
                    EventType.CHANGE_REQUEST_REJECTED,
                    {"suggestion_id": suggestion_id, "reason": reason}
                )

        except Exception as e:
            print(f"[SERVER] Reject change request error: {e}")

    # ============ KiloAgent Diagram Cascade Edit ============

    async def _handle_kilo_diagram_cascade(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """
        Handle cascade diagram edit via KiloAgent.

        Sequentially processes each node in the cascade, calling the LLM for each.
        Streams progress events back to the client for real-time feedback.
        """
        diagram_id = data.get("diagram_id")
        parent_node_id = data.get("parent_node_id")
        parent_node_type = data.get("parent_node_type")
        cascade_node_ids = data.get("cascade_node_ids", [])
        kilo_prompt = data.get("kilo_prompt")
        current_mermaid = data.get("current_mermaid_code", "")

        if not diagram_id or not kilo_prompt:
            print("[CASCADE] ERROR: Missing diagram_id or kilo_prompt")
            return

        change_id = str(uuid.uuid4())[:8]

        # Build full node list: root first, then cascade nodes
        all_nodes = [parent_node_id] + [n for n in cascade_node_ids if n != parent_node_id]
        total = len(all_nodes)

        print(f"\n[CASCADE] Starting cascade edit for {diagram_id}")
        print(f"[CASCADE] Parent: {parent_node_id} ({parent_node_type})")
        print(f"[CASCADE] Cascade nodes: {cascade_node_ids}")
        print(f"[CASCADE] Total LLM calls: {total}")
        print(f"[CASCADE] Change ID: {change_id}")

        # Track results
        self._cascade_results[change_id] = {
            "nodes": {},
            "status": "processing",
        }

        for idx, node_id in enumerate(all_nodes):
            # Send progress (wrapped in {type, data} for frontend handleMessage)
            await ws.send_json({
                "type": "kilo_diagram_cascade_progress",
                "data": {
                    "change_id": change_id,
                    "current_node_id": node_id,
                    "current_index": idx,
                    "total": total,
                    "status": "processing",
                }
            })

            try:
                # Get mermaid code for this node
                if idx == 0:
                    node_mermaid = current_mermaid
                else:
                    node_mermaid = self._get_node_mermaid(node_id) or ""

                # Build prompt
                prompt = self._build_cascade_prompt(
                    node_id=node_id,
                    node_mermaid=node_mermaid,
                    parent_change=kilo_prompt,
                    parent_node_id=parent_node_id,
                    is_root=(idx == 0),
                    original_mermaid=current_mermaid,
                )

                print(f"[CASCADE] Processing node {idx + 1}/{total}: {node_id}")

                # Execute LLM call
                result = await self._execute_kilo_agent(prompt)

                if result.get("success"):
                    new_mermaid = self._extract_mermaid(result["response"])

                    if new_mermaid:
                        self._cascade_results[change_id]["nodes"][node_id] = {
                            "success": True,
                            "suggested_mermaid": new_mermaid,
                            "reasoning": result["response"][:500],
                        }

                        await ws.send_json({
                            "type": "kilo_diagram_cascade_node_result",
                            "data": {
                                "change_id": change_id,
                                "node_id": node_id,
                                "success": True,
                                "suggested_mermaid": new_mermaid,
                                "reasoning": result["response"][:500],
                                "current_index": idx,
                                "total": total,
                            }
                        })
                        print(f"[CASCADE] Node {node_id}: OK (mermaid extracted)")
                    else:
                        error_msg = "Kein Mermaid-Block in LLM-Antwort gefunden"
                        self._cascade_results[change_id]["nodes"][node_id] = {
                            "success": False,
                            "error": error_msg,
                        }
                        await ws.send_json({
                            "type": "kilo_diagram_cascade_node_result",
                            "data": {
                                "change_id": change_id,
                                "node_id": node_id,
                                "success": False,
                                "error": error_msg,
                                "current_index": idx,
                                "total": total,
                            }
                        })
                        print(f"[CASCADE] Node {node_id}: FAILED (no mermaid block)")
                else:
                    error_msg = result.get("error", "Unknown error")
                    self._cascade_results[change_id]["nodes"][node_id] = {
                        "success": False,
                        "error": error_msg,
                    }
                    await ws.send_json({
                        "type": "kilo_diagram_cascade_node_result",
                        "data": {
                            "change_id": change_id,
                            "node_id": node_id,
                            "success": False,
                            "error": error_msg,
                            "current_index": idx,
                            "total": total,
                        }
                    })
                    print(f"[CASCADE] Node {node_id}: ERROR ({error_msg[:100]})")

            except Exception as e:
                print(f"[CASCADE] Node {node_id}: EXCEPTION ({e})")
                await ws.send_json({
                    "type": "kilo_diagram_cascade_node_result",
                    "data": {
                        "change_id": change_id,
                        "node_id": node_id,
                        "success": False,
                        "error": str(e),
                        "current_index": idx,
                        "total": total,
                    }
                })

        # Cascade complete
        success_count = sum(
            1 for n in self._cascade_results[change_id]["nodes"].values()
            if n.get("success")
        )
        self._cascade_results[change_id]["status"] = "complete"

        await ws.send_json({
            "type": "kilo_diagram_cascade_complete",
            "data": {
                "change_id": change_id,
                "total_processed": total,
                "success_count": success_count,
            }
        })
        print(f"[CASCADE] Complete: {success_count}/{total} successful")

    def _build_cascade_prompt(self, node_id: str, node_mermaid: str,
                              parent_change: str, parent_node_id: str,
                              is_root: bool, original_mermaid: str) -> str:
        """Build LLM prompt for cascade edit."""
        if is_root:
            return self._build_kilo_prompt(original_mermaid, parent_change, 'diagram')
        else:
            return f"""Ein uebergeordnetes Artefakt ({parent_node_id}) wurde geaendert.
Die Aenderung war: {parent_change}

Aktualisiere das Mermaid-Diagramm fuer den Knoten {node_id} entsprechend:

```mermaid
{node_mermaid}
```

WICHTIG:
- Passe das Diagramm an die uebergeordnete Aenderung an
- Behalte die spezifischen Details dieses Knotens bei
- Gib das aktualisierte Diagramm in einem ```mermaid Block zurueck
- Wenn keine Aenderung notwendig ist, gib das Diagramm unveraendert zurueck"""

    def _get_node_mermaid(self, node_id: str) -> Optional[str]:
        """Get mermaid code for a node from canvas_state."""
        nodes = self.canvas_state.get("nodes", {})

        # Direct lookup
        node_data = nodes.get(node_id, {})
        data = node_data.get("data", {})
        if data.get("mermaid_code"):
            return data["mermaid_code"]
        if data.get("content") and isinstance(data["content"], str):
            return data["content"]

        # Check diagram sub-nodes
        suffixes = ["_flowchart", "_sequence", "_class", "_er", "_state", "_c4",
                     "-flowchart", "-sequence", "-class", "-er", "-state", "-c4"]
        for suffix in suffixes:
            diagram_id = node_id + suffix
            diagram_data = nodes.get(diagram_id, {})
            d = diagram_data.get("data", {})
            mermaid = d.get("mermaid_code") or d.get("content")
            if mermaid and isinstance(mermaid, str):
                return mermaid

        return None

    async def _handle_approve_cascade_node(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Apply approved cascade node change."""
        change_id = data.get("change_id")
        node_id = data.get("node_id")

        if not change_id or not node_id:
            return

        cascade_data = self._cascade_results.get(change_id, {})
        node_result = cascade_data.get("nodes", {}).get(node_id, {})

        if node_result.get("suggested_mermaid"):
            new_mermaid = node_result["suggested_mermaid"]

            # Update canvas_state
            nodes = self.canvas_state.get("nodes", {})
            if node_id in nodes:
                if "data" not in nodes[node_id]:
                    nodes[node_id]["data"] = {}
                nodes[node_id]["data"]["mermaid_code"] = new_mermaid
                print(f"[CASCADE] Approved: {node_id} updated in canvas_state")
            else:
                # Check diagram sub-nodes
                suffixes = ["_flowchart", "_sequence", "_class", "_er", "_state", "_c4",
                             "-flowchart", "-sequence", "-class", "-er", "-state", "-c4"]
                for suffix in suffixes:
                    diagram_id = node_id + suffix
                    if diagram_id in nodes:
                        if "data" not in nodes[diagram_id]:
                            nodes[diagram_id]["data"] = {}
                        nodes[diagram_id]["data"]["mermaid_code"] = new_mermaid
                        print(f"[CASCADE] Approved: {diagram_id} updated in canvas_state")
                        break

            # Emit diagram_updated event
            await self.emitter.diagram_updated(node_id, new_mermaid, "")

        await ws.send_json({
            "type": "cascade_node_approved",
            "data": {
                "change_id": change_id,
                "node_id": node_id,
            }
        })

    async def _handle_reject_cascade_node(self, ws: web.WebSocketResponse, data: Dict[str, Any]):
        """Reject a cascade node suggestion."""
        change_id = data.get("change_id")
        node_id = data.get("node_id")

        print(f"[CASCADE] Rejected: {node_id}")

        await ws.send_json({
            "type": "cascade_node_rejected",
            "data": {
                "change_id": change_id,
                "node_id": node_id,
            }
        })

    async def _handle_get_state(self, request: web.Request) -> web.Response:
        """Return current canvas state."""
        return web.json_response(self.canvas_state)

    async def _handle_get_history(self, request: web.Request) -> web.Response:
        """Return event history."""
        return web.json_response(self.emitter.get_history())

    async def _handle_list_projects(self, request: web.Request) -> web.Response:
        """List all projects from enterprise_output folder (both formats)."""
        projects = []
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"

        if output_dir.exists():
            for project_dir in sorted(output_dir.iterdir(), reverse=True):
                if not project_dir.is_dir():
                    continue

                # Check for content indicators
                has_journal = (project_dir / "journal.json").exists()
                has_user_stories = (project_dir / "user_stories" / "user_stories.md").exists()
                diagrams_dir = project_dir / "diagrams"
                has_diagrams = diagrams_dir.exists() and any(diagrams_dir.glob("*.mmd"))
                testing_dir = project_dir / "testing"
                has_tests = testing_dir.exists() and any(testing_dir.glob("*.feature"))

                # Skip empty projects
                if not (has_journal or has_user_stories or has_diagrams):
                    continue

                # Count items based on format
                node_count = 0
                epic_count = 0
                us_count = 0
                diagram_count = 0
                test_count = 0

                if has_journal:
                    try:
                        with open(project_dir / "journal.json", encoding="utf-8") as f:
                            journal = json.load(f)
                        node_count = len(journal.get("nodes", {}))
                    except (json.JSONDecodeError, IOError):
                        pass

                if has_user_stories:
                    try:
                        epics, stories = parse_user_stories_md(project_dir / "user_stories" / "user_stories.md")
                        epic_count = len(epics)
                        us_count = len(stories)
                    except Exception:
                        pass

                if has_diagrams:
                    diagram_count = len(list(diagrams_dir.glob("*.mmd")))

                if has_tests:
                    test_count = len(list(testing_dir.glob("*.feature")))

                projects.append({
                    "id": project_dir.name,
                    "name": extract_project_name(project_dir),
                    "path": str(project_dir),
                    "format": "journal" if has_journal else "folder",
                    "has_journal": has_journal,
                    "has_user_stories": has_user_stories,
                    "has_diagrams": has_diagrams,
                    "has_tests": has_tests,
                    "node_count": node_count,
                    "epic_count": epic_count,
                    "us_count": us_count,
                    "diagram_count": diagram_count,
                    "test_count": test_count,
                    "created": extract_timestamp(project_dir.name)
                })

        return web.json_response({"projects": projects})

    async def _handle_load_project(self, request: web.Request) -> web.Response:
        """Load a specific project's data (supports both formats)."""
        project_id = request.match_info["project_id"]
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        project_dir = output_dir / project_id

        if not project_dir.exists():
            return web.json_response({"error": "Project not found"}, status=404)

        # Track the currently loaded project for auto-linker
        self._current_project_path = project_dir
        self._current_project_id = project_id
        print(f"[SERVER] Loaded project: {project_id}")

        try:
            journal_path = project_dir / "journal.json"

            # Always load folder-based data first (epics, user_stories, tests, etc.)
            result = self._load_folder_format(project_dir)

            # If journal.json exists, merge its nodes with the folder data
            if journal_path.exists():
                with open(journal_path, encoding="utf-8") as f:
                    journal = json.load(f)
                # Merge journal nodes into result
                if "nodes" in journal:
                    result["nodes"] = journal.get("nodes", {})
                if "project_name" in journal:
                    result["project_name"] = journal["project_name"]
                result["format"] = "hybrid"  # Indicates both sources were used
                print(f"  [INFO] Merged journal.json with folder data for {project_id}")

            return web.json_response(result)

        except (json.JSONDecodeError, IOError) as e:
            return web.json_response({"error": str(e)}, status=500)

    def _load_folder_format(self, project_dir: Path) -> dict:
        """Load project data from folder-based format."""
        result = {
            "project_name": extract_project_name(project_dir),
            "format": "folder",
            "nodes": {},
            "requirements": [],  # NEW: Requirements from journal.json
            "epics": [],
            "user_stories": [],
            "diagrams": [],
            "tests": [],
            "traceability": [],
            "data_dictionary": {"entities": [], "relationships": [], "glossary": []},
            "features": [],
            "api_endpoints": [],
            # New artifact types
            "tech_stack": None,
            "personas": [],
            "user_flows": [],
            "ui_components": [],
            "screens": [],
            "design_tokens": {},
            "tasks": {},
            "task_summary": {"total_tasks": 0, "total_hours": 0},
            "state_machines": [],
            "infrastructure": None,
            "ui_compositions": [],
            "test_factories": [],
            "architecture": None
        }

        # ========== LOAD REQUIREMENTS FROM JOURNAL.JSON ==========
        journal_file = project_dir / "journal.json"
        if journal_file.exists():
            try:
                with open(journal_file, encoding="utf-8") as f:
                    journal_data = json.load(f)
                    nodes = journal_data.get("nodes", {})
                    result["nodes"] = nodes

                    # Extract requirements from nodes
                    for node_id, node in nodes.items():
                        req_id = node.get("requirement_id", "")
                        if req_id:
                            result["requirements"].append({
                                "id": req_id,
                                "title": node.get("title", ""),
                                "description": node.get("description", ""),
                                "type": node.get("type", "functional"),
                                "priority": node.get("priority", "should"),
                                "source": node.get("source", ""),
                                "mermaid_diagrams": node.get("mermaid_diagrams", {})
                            })
                print(f"  [INFO] Loaded {len(result['requirements'])} requirements from journal.json")
            except Exception as e:
                print(f"  [WARN] Could not parse journal.json: {e}")

        # ========== LOAD TESTS FROM .feature FILES ==========
        testing_dir = project_dir / "testing"
        if testing_dir.exists():
            feature_files = list(testing_dir.glob("*.feature"))
            for feature_file in sorted(feature_files):
                try:
                    content = feature_file.read_text(encoding="utf-8")
                    # Parse feature name from file
                    feature_match = re.search(r'Feature:\s*(.+)', content)
                    feature_name = feature_match.group(1).strip() if feature_match else feature_file.stem

                    # Count scenarios
                    scenario_count = len(re.findall(r'Scenario:', content))

                    # Extract tags
                    tags = re.findall(r'@(\w+)', content)

                    test_id = feature_file.stem.upper().replace("_", "-")  # us_001 -> US-001

                    result["tests"].append({
                        "id": f"TC-{test_id}",
                        "title": feature_name,
                        "feature_file": feature_file.name,
                        "scenario_count": scenario_count,
                        "tags": tags,
                        "gherkin_content": content,
                        "linked_user_story": test_id  # e.g., US-001
                    })
                except Exception as e:
                    print(f"  [WARN] Could not parse {feature_file.name}: {e}")

            print(f"  [INFO] Loaded {len(result['tests'])} test cases from .feature files")

        # Parse user_stories.md for Epics and User Stories
        us_file = project_dir / "user_stories" / "user_stories.md"
        if us_file.exists():
            try:
                epics, stories = parse_user_stories_md(us_file)
                result["epics"] = epics
                result["user_stories"] = stories
            except Exception as e:
                print(f"  [WARN] Could not parse user_stories.md: {e}")

        # Parse traceability_matrix.md for linkages
        trace_file = project_dir / "reports" / "traceability_matrix.md"
        if trace_file.exists():
            try:
                result["traceability"] = parse_traceability_matrix_md(trace_file)
                print(f"  [INFO] Loaded {len(result['traceability'])} traceability entries")
            except Exception as e:
                print(f"  [WARN] Could not parse traceability_matrix.md: {e}")

        # Parse data_dictionary.md for entities
        dd_file = project_dir / "data" / "data_dictionary.md"
        if dd_file.exists():
            try:
                result["data_dictionary"] = parse_data_dictionary_md(dd_file)
                print(f"  [INFO] Loaded {len(result['data_dictionary']['entities'])} entities")
            except Exception as e:
                print(f"  [WARN] Could not parse data_dictionary.md: {e}")

        # Load ER diagram from data folder
        er_diagram_path = project_dir / "data" / "er_diagram.mmd"
        if er_diagram_path.exists():
            try:
                er_code = er_diagram_path.read_text(encoding="utf-8")
                if "diagrams" not in result:
                    result["diagrams"] = []
                result["diagrams"].append({
                    "id": "ER-DIAGRAM",
                    "type": "er",
                    "title": "Entity Relationship Diagram",
                    "mermaid_code": er_code,
                    "parent_type": "database"
                })
                print(f"  [INFO] Loaded ER diagram from data/er_diagram.mmd")
            except Exception as e:
                print(f"  [WARN] Could not load er_diagram.mmd: {e}")

        # Parse feature_breakdown.md for work packages
        wb_file = project_dir / "work_breakdown" / "feature_breakdown.md"
        if wb_file.exists():
            try:
                result["features"] = parse_work_breakdown_md(wb_file)
                print(f"  [INFO] Loaded {len(result['features'])} features")
            except Exception as e:
                print(f"  [WARN] Could not parse feature_breakdown.md: {e}")

        # Parse api_documentation.md for endpoints
        api_file = project_dir / "api" / "api_documentation.md"
        if api_file.exists():
            try:
                result["api_endpoints"] = parse_api_documentation_md(api_file)
                print(f"  [INFO] Loaded {len(result['api_endpoints'])} API endpoints")
            except Exception as e:
                print(f"  [WARN] Could not parse api_documentation.md: {e}")

        # ========== NEW ARTIFACT TYPES ==========

        # Load tech_stack.json
        tech_stack_file = project_dir / "tech_stack" / "tech_stack.json"
        if tech_stack_file.exists():
            try:
                with open(tech_stack_file, encoding="utf-8") as f:
                    result["tech_stack"] = json.load(f)
                print(f"  [INFO] Loaded tech stack: {result['tech_stack'].get('backend_framework', 'N/A')} / {result['tech_stack'].get('frontend_framework', 'N/A')}")
            except Exception as e:
                print(f"  [WARN] Could not parse tech_stack.json: {e}")

        # Load architecture diagram from tech_stack folder
        arch_diagram_path = project_dir / "tech_stack" / "architecture_diagram.mmd"
        if arch_diagram_path.exists():
            try:
                arch_code = arch_diagram_path.read_text(encoding="utf-8")
                if "diagrams" not in result:
                    result["diagrams"] = []
                result["diagrams"].append({
                    "id": "ARCH-DIAGRAM",
                    "type": "c4",
                    "title": "System Architecture",
                    "mermaid_code": arch_code,
                    "parent_type": "tech-stack"
                })
                print(f"  [INFO] Loaded architecture diagram from tech_stack/architecture_diagram.mmd")
            except Exception as e:
                print(f"  [WARN] Could not load architecture_diagram.mmd: {e}")

        # Load task dependency diagram from tasks folder
        dep_diagram_path = project_dir / "tasks" / "dependency_graph.mmd"
        if dep_diagram_path.exists():
            try:
                dep_code = dep_diagram_path.read_text(encoding="utf-8")
                if "diagrams" not in result:
                    result["diagrams"] = []
                result["diagrams"].append({
                    "id": "DEP-DIAGRAM",
                    "type": "flowchart",
                    "title": "Task Dependencies",
                    "mermaid_code": dep_code,
                    "parent_type": "tasks"
                })
                print(f"  [INFO] Loaded dependency diagram from tasks/dependency_graph.mmd")
            except Exception as e:
                print(f"  [WARN] Could not load dependency_graph.mmd: {e}")

        # Load Gantt chart from tasks folder
        gantt_path = project_dir / "tasks" / "gantt_chart.mmd"
        if gantt_path.exists():
            try:
                gantt_code = gantt_path.read_text(encoding="utf-8")
                if "diagrams" not in result:
                    result["diagrams"] = []
                result["diagrams"].append({
                    "id": "GANTT-DIAGRAM",
                    "type": "gantt",
                    "title": "Project Timeline (Gantt)",
                    "mermaid_code": gantt_code,
                    "parent_type": "tasks"
                })
                print(f"  [INFO] Loaded Gantt chart from tasks/gantt_chart.mmd")
            except Exception as e:
                print(f"  [WARN] Could not load gantt_chart.mmd: {e}")

        # Load ux_spec.json (Personas, User Flows)
        ux_spec_file = project_dir / "ux_design" / "ux_spec.json"
        if ux_spec_file.exists():
            try:
                with open(ux_spec_file, encoding="utf-8") as f:
                    ux_data = json.load(f)
                    result["personas"] = ux_data.get("personas", [])
                    result["user_flows"] = ux_data.get("user_flows", [])
                print(f"  [INFO] Loaded {len(result['personas'])} personas, {len(result['user_flows'])} user flows")
            except Exception as e:
                print(f"  [WARN] Could not parse ux_spec.json: {e}")

        # Load User Flow Mermaid diagrams from ux_design/user_flows/*.mmd
        ux_flows_dir = project_dir / "ux_design" / "user_flows"
        if ux_flows_dir.exists():
            for mmd_file in sorted(ux_flows_dir.glob("*.mmd")):
                try:
                    mermaid_code = mmd_file.read_text(encoding="utf-8")
                    flow_id = mmd_file.stem.upper()  # flow-001 -> FLOW-001

                    # Try to match with existing user_flow by ID
                    matched = False
                    for flow in result["user_flows"]:
                        if flow.get("id", "").upper() == flow_id:
                            flow["mermaid_code"] = mermaid_code
                            flow["file_path"] = str(mmd_file)
                            matched = True
                            break

                    # If no match, add as standalone diagram
                    if not matched:
                        result["user_flows"].append({
                            "id": flow_id,
                            "name": mmd_file.stem.replace("-", " ").replace("_", " ").title(),
                            "mermaid_code": mermaid_code,
                            "file_path": str(mmd_file)
                        })
                except Exception as e:
                    print(f"  [WARN] Could not read {mmd_file.name}: {e}")
            print(f"  [INFO] Loaded {len(list(ux_flows_dir.glob('*.mmd')))} user flow diagrams")

        # Load ui_spec.json (Components, Screens, Design Tokens)
        ui_spec_file = project_dir / "ui_design" / "ui_spec.json"
        if ui_spec_file.exists():
            try:
                with open(ui_spec_file, encoding="utf-8") as f:
                    ui_data = json.load(f)
                    result["ui_components"] = ui_data.get("components", [])
                    result["screens"] = ui_data.get("screens", [])
                    result["design_tokens"] = ui_data.get("design_tokens", {})
                print(f"  [INFO] Loaded {len(result['ui_components'])} components, {len(result['screens'])} screens from JSON")
            except Exception as e:
                print(f"  [WARN] Could not parse ui_spec.json: {e}")

        # Load individual screen markdown files from ui_design/screens/
        screens_dir = project_dir / "ui_design" / "screens"
        if screens_dir.exists():
            try:
                parsed_screens = parse_screen_markdown_files(screens_dir)

                # Merge with JSON screens (JSON has priority)
                json_screen_ids = {s.get('id') for s in result["screens"]}
                for parsed_screen in parsed_screens:
                    if parsed_screen.get('id') not in json_screen_ids:
                        result["screens"].append(parsed_screen)

                print(f"  [INFO] Loaded {len(parsed_screens)} screens from markdown files (total: {len(result['screens'])})")
            except Exception as e:
                print(f"  [WARN] Could not parse screen markdown files: {e}")

        # Load task_list.json
        tasks_file = project_dir / "tasks" / "task_list.json"
        if tasks_file.exists():
            try:
                with open(tasks_file, encoding="utf-8") as f:
                    tasks_data = json.load(f)
                    result["tasks"] = tasks_data.get("features", {})
                    result["task_summary"] = {
                        "total_tasks": tasks_data.get("total_tasks", 0),
                        "total_hours": tasks_data.get("total_hours", 0),
                        "total_story_points": tasks_data.get("total_story_points", 0)
                    }
                print(f"  [INFO] Loaded {result['task_summary']['total_tasks']} tasks ({result['task_summary']['total_hours']}h)")
            except Exception as e:
                print(f"  [WARN] Could not parse task_list.json: {e}")

        # ========== LOAD STATE MACHINES ==========
        state_machines_file = project_dir / "state_machines" / "state_machines.json"
        if state_machines_file.exists():
            try:
                state_machines = parse_state_machines_json(state_machines_file)
                result["state_machines"] = state_machines
                print(f"  [INFO] Loaded {len(state_machines)} state machines")
            except Exception as e:
                print(f"  [WARN] Could not parse state_machines.json: {e}")

        # Also load individual state machine .mmd files
        sm_dir = project_dir / "state_machines"
        if sm_dir.exists():
            for mmd_file in sorted(sm_dir.glob("*.mmd")):
                try:
                    mermaid_code = mmd_file.read_text(encoding="utf-8")
                    sm_id = mmd_file.stem.upper().replace("_", "-")

                    # Try to match with existing state machine
                    matched = False
                    for sm in result.get("state_machines", []):
                        if sm.get("entity", "").replace("_", "-") == mmd_file.stem:
                            sm["mermaid_file"] = str(mmd_file)
                            matched = True
                            break

                    # If no match, add as standalone diagram
                    if not matched:
                        result["diagrams"].append({
                            "id": f"SM-{sm_id}",
                            "type": "stateDiagram",
                            "mermaid_code": mermaid_code,
                            "title": mmd_file.stem.replace("_", " ").title()
                        })
                except Exception as e:
                    print(f"  [WARN] Could not read {mmd_file.name}: {e}")

        # ========== LOAD INFRASTRUCTURE ==========
        infra_file = project_dir / "infrastructure" / "infrastructure.json"
        if infra_file.exists():
            try:
                infra = parse_infrastructure_json(infra_file)
                if infra:
                    result["infrastructure"] = infra
                    print(f"  [INFO] Loaded infrastructure with {infra.get('service_count', 0)} services")
            except Exception as e:
                print(f"  [WARN] Could not parse infrastructure.json: {e}")

        # ========== LOAD UI COMPOSITIONS ==========
        compositions_dir = project_dir / "ui_design" / "compositions"
        if compositions_dir.exists():
            try:
                compositions = parse_ui_compositions_json(compositions_dir)
                result["ui_compositions"] = compositions
                print(f"  [INFO] Loaded {len(compositions)} UI compositions")
            except Exception as e:
                print(f"  [WARN] Could not parse UI compositions: {e}")

        # ========== LOAD TEST FACTORIES ==========
        factories_file = project_dir / "testing" / "factories" / "factories.json"
        if factories_file.exists():
            try:
                factories = parse_test_factories_json(factories_file)
                result["test_factories"] = factories
                print(f"  [INFO] Loaded {len(factories)} test factories")
            except Exception as e:
                print(f"  [WARN] Could not parse factories.json: {e}")

        # ========== LOAD ARCHITECTURE ==========
        arch_file = project_dir / "architecture" / "architecture.json"
        if arch_file.exists():
            try:
                arch = parse_architecture_json(arch_file)
                if arch:
                    result["architecture"] = arch
                    print(f"  [INFO] Loaded architecture with {arch.get('service_count', 0)} services ({arch.get('architecture_pattern', 'unknown')} pattern)")

                    # Add architecture diagrams to main diagrams list
                    for diagram in arch.get("diagrams", []):
                        result["diagrams"].append(diagram)
            except Exception as e:
                print(f"  [WARN] Could not parse architecture.json: {e}")

        # ========================================

        # Load diagrams from .mmd files
        diagrams_dir = project_dir / "diagrams"
        print(f"  [DEBUG] Checking diagrams directory: {diagrams_dir}")
        if diagrams_dir.exists():
            mmd_files = list(diagrams_dir.glob("*.mmd"))
            print(f"  [DEBUG] Found {len(mmd_files)} .mmd files")
            for mmd_file in sorted(mmd_files):
                try:
                    mermaid_code = mmd_file.read_text(encoding="utf-8")
                    # Extract requirement ID and type from filename (e.g., "REQ-001_flowchart.mmd")
                    parts = mmd_file.stem.rsplit("_", 1)
                    req_id = parts[0] if len(parts) > 1 else mmd_file.stem
                    diagram_type = parts[1] if len(parts) > 1 else "flowchart"
                    result["diagrams"].append({
                        "id": mmd_file.stem,
                        "requirement_id": req_id,
                        "type": diagram_type,
                        "mermaid_code": mermaid_code
                    })
                    print(f"  [DEBUG] Loaded diagram: {mmd_file.stem} (code length: {len(mermaid_code)})")
                except Exception as e:
                    print(f"  [WARN] Could not read {mmd_file.name}: {e}")
            print(f"  [INFO] Loaded {len(result['diagrams'])} diagrams from .mmd files")
        else:
            print(f"  [DEBUG] Diagrams directory does not exist: {diagrams_dir}")

        # NOTE: Tests are loaded earlier (lines 357-388) with better format
        # This duplicate block is removed to avoid loading tests twice

        # ========== ADDITIONAL DATA SOURCES ==========

        # Load quality/self_critique_report.json
        critique_file = project_dir / "quality" / "self_critique_report.json"
        if critique_file.exists():
            try:
                with open(critique_file, encoding="utf-8") as f:
                    result["quality_critique"] = json.load(f)
                issues = result["quality_critique"].get("issues", [])
                print(f"  [INFO] Loaded quality critique: {len(issues)} issues")
            except Exception as e:
                print(f"  [WARN] Could not parse self_critique_report.json: {e}")

        # Load quality/quality_gates.md
        gates_file = project_dir / "quality" / "quality_gates.md"
        if gates_file.exists():
            try:
                result["quality_gates"] = gates_file.read_text(encoding="utf-8")
                print(f"  [INFO] Loaded quality gates ({len(result['quality_gates'])} chars)")
            except Exception as e:
                print(f"  [WARN] Could not load quality_gates.md: {e}")

        # Load reports/validation_report.md
        validation_file = project_dir / "reports" / "validation_report.md"
        if validation_file.exists():
            try:
                result["validation_report"] = validation_file.read_text(encoding="utf-8")
                print(f"  [INFO] Loaded validation report ({len(result['validation_report'])} chars)")
            except Exception as e:
                print(f"  [WARN] Could not load validation_report.md: {e}")

        # Load MASTER_DOCUMENT.md (executive summary)
        master_doc = project_dir / "MASTER_DOCUMENT.md"
        if master_doc.exists():
            try:
                result["master_document"] = master_doc.read_text(encoding="utf-8")
                print(f"  [INFO] Loaded MASTER_DOCUMENT.md ({len(result['master_document'])} chars)")
            except Exception as e:
                print(f"  [WARN] Could not load MASTER_DOCUMENT.md: {e}")

        # Load presentation_ledger.json (project metadata)
        ledger_file = project_dir / "presentation_ledger.json"
        if ledger_file.exists():
            try:
                with open(ledger_file, encoding="utf-8") as f:
                    result["presentation_ledger"] = json.load(f)
                print(f"  [INFO] Loaded presentation ledger")
            except Exception as e:
                print(f"  [WARN] Could not parse presentation_ledger.json: {e}")

        # Load api/openapi_spec.yaml (structured API spec)
        openapi_file = project_dir / "api" / "openapi_spec.yaml"
        if openapi_file.exists():
            try:
                result["openapi_spec"] = openapi_file.read_text(encoding="utf-8")
                print(f"  [INFO] Loaded OpenAPI spec ({len(result['openapi_spec'])} chars)")
            except Exception as e:
                print(f"  [WARN] Could not load openapi_spec.yaml: {e}")

        # Load api/asyncapi_spec.yaml (WebSocket channels)
        asyncapi_file = project_dir / "api" / "asyncapi_spec.yaml"
        if asyncapi_file.exists():
            try:
                import yaml
                spec = yaml.safe_load(asyncapi_file.read_text(encoding="utf-8"))
                channels = []
                for ch_name, ch_data in (spec.get("channels", {}) or {}).items():
                    channel = {
                        "id": f"ws-{ch_name.replace('/', '-')}",
                        "name": ch_name,
                        "type": "api",
                        "method": "WS",
                        "path": f"ws://{ch_name}",
                        "description": (ch_data or {}).get("description", ""),
                        "subscribe": (ch_data or {}).get("subscribe", {}),
                        "publish": (ch_data or {}).get("publish", {}),
                    }
                    channels.append(channel)
                if channels:
                    if not result.get("api_endpoints"):
                        result["api_endpoints"] = []
                    result["api_endpoints"].extend(channels)
                    print(f"  [INFO] Loaded {len(channels)} WebSocket channels from AsyncAPI")
            except Exception as e:
                print(f"  [WARN] Could not load asyncapi_spec.yaml: {e}")

        # Load user_stories.json (structured format - richer than MD)
        us_json_file = project_dir / "user_stories.json"
        if us_json_file.exists():
            try:
                with open(us_json_file, encoding="utf-8") as f:
                    us_data = json.load(f)
                # Enrich existing user stories with JSON data
                if isinstance(us_data, list) and us_data:
                    for us in us_data:
                        us_id = us.get("id", "")
                        # Find and enrich matching story
                        for existing in result.get("user_stories", []):
                            if existing.get("id") == us_id:
                                existing.update({
                                    k: v for k, v in us.items()
                                    if k not in existing or not existing[k]
                                })
                                break
                    print(f"  [INFO] Enriched user stories from JSON ({len(us_data)} stories)")
            except Exception as e:
                print(f"  [WARN] Could not parse user_stories.json: {e}")

        # ========== GROUP API ENDPOINTS BY RESOURCE ==========
        COMMON_PREFIXES = {"api", "v1", "v2", "v3", "rest", "graphql"}
        MIN_PACKAGE_SIZE = 5  # merge smaller groups into "misc"
        raw_packages: dict = {}
        for ep in result.get("api_endpoints", []):
            path = ep.get("path", "/")
            segments = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
            # Skip common API prefixes to get the actual resource name
            while segments and segments[0].lower() in COMMON_PREFIXES:
                segments = segments[1:]
            resource = segments[0] if segments else "root"
            # Normalize ws:// paths
            if resource.startswith("ws:"):
                resource = "websocket"
            if resource not in raw_packages:
                raw_packages[resource] = {"tag": resource, "endpoints": [], "method_counts": {}}
            raw_packages[resource]["endpoints"].append(ep)
            m = ep.get("method", "GET").upper()
            raw_packages[resource]["method_counts"][m] = raw_packages[resource]["method_counts"].get(m, 0) + 1

        # Merge small packages into "misc"
        api_packages = {}
        misc_pkg = {"tag": "misc", "endpoints": [], "method_counts": {}}
        for tag, pkg in raw_packages.items():
            if len(pkg["endpoints"]) >= MIN_PACKAGE_SIZE:
                api_packages[tag] = pkg
            else:
                misc_pkg["endpoints"].extend(pkg["endpoints"])
                for m, c in pkg["method_counts"].items():
                    misc_pkg["method_counts"][m] = misc_pkg["method_counts"].get(m, 0) + c
        if misc_pkg["endpoints"]:
            api_packages["misc"] = misc_pkg

        result["api_packages"] = api_packages
        if api_packages:
            print(f"  [INFO] Grouped {len(result.get('api_endpoints', []))} API endpoints into {len(api_packages)} packages")

        # ========== MERGE COMPOSITIONS INTO SCREENS ==========
        for comp in result.get("ui_compositions", []):
            route = comp.get("route", "")
            if not route:
                continue
            for screen in result.get("screens", []):
                if screen.get("route") == route:
                    screen["composition"] = comp
                    break

        # ========== LOAD MISSING DATA FILES ==========
        # llm_usage_summary.json
        llm_usage_file = project_dir / "llm_usage_summary.json"
        if llm_usage_file.exists():
            try:
                with open(llm_usage_file, encoding="utf-8") as f:
                    result["llm_usage"] = json.load(f)
                print(f"  [INFO] Loaded LLM usage: {result['llm_usage'].get('total_calls', 0)} calls, ${result['llm_usage'].get('total_cost_usd', 0):.2f}")
            except Exception as e:
                print(f"  [WARN] Could not parse llm_usage_summary.json: {e}")

        # pipeline_manifest.json
        manifest_file = project_dir / "pipeline_manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, encoding="utf-8") as f:
                    result["pipeline_manifest"] = json.load(f)
                print(f"  [INFO] Loaded pipeline manifest: {len(result['pipeline_manifest'].get('stages', []))} stages")
            except Exception as e:
                print(f"  [WARN] Could not parse pipeline_manifest.json: {e}")

        # content_analysis.json
        content_analysis_file = project_dir / "content_analysis.json"
        if content_analysis_file.exists():
            try:
                with open(content_analysis_file, encoding="utf-8") as f:
                    result["content_analysis"] = json.load(f)
                print(f"  [INFO] Loaded content analysis")
            except Exception as e:
                print(f"  [WARN] Could not parse content_analysis.json: {e}")

        # html_review_report.json
        review_file = project_dir / "html_review_report.json"
        if review_file.exists():
            try:
                with open(review_file, encoding="utf-8") as f:
                    result["html_review_report"] = json.load(f)
                print(f"  [INFO] Loaded HTML review report")
            except Exception as e:
                print(f"  [WARN] Could not parse html_review_report.json: {e}")

        # Load ux_design/accessibility_checklist.md
        a11y_file = project_dir / "ux_design" / "accessibility_checklist.md"
        if a11y_file.exists():
            try:
                result["accessibility_checklist"] = a11y_file.read_text(encoding="utf-8")
                print(f"  [INFO] Loaded accessibility checklist")
            except Exception as e:
                print(f"  [WARN] Could not load accessibility_checklist.md: {e}")

        # Load ux_design/information_architecture.md
        ia_file = project_dir / "ux_design" / "information_architecture.md"
        if ia_file.exists():
            try:
                result["information_architecture"] = ia_file.read_text(encoding="utf-8")
                print(f"  [INFO] Loaded information architecture")
            except Exception as e:
                print(f"  [WARN] Could not load information_architecture.md: {e}")

        # Compute project summary stats
        arch_services = result.get("architecture", {}).get("services", []) if isinstance(result.get("architecture"), dict) else []
        result["project_stats"] = {
            "total_requirements": len(result.get("nodes", {})) or len(result.get("requirements", [])),
            "total_epics": len(result.get("epics", [])),
            "total_user_stories": len(result.get("user_stories", [])),
            "total_tests": len(result.get("tests", [])),
            "total_diagrams": len(result.get("diagrams", [])),
            "total_api_endpoints": len(result.get("api_endpoints", [])),
            "total_api_packages": len(result.get("api_packages", {})),
            "total_features": len(result.get("features", [])),
            "total_personas": len(result.get("personas", [])),
            "total_screens": len(result.get("screens", [])),
            "total_components": len(result.get("ui_components", [])),
            "total_entities": len(result.get("data_dictionary", {}).get("entities", [])),
            "total_services": len(arch_services),
            "total_state_machines": len(result.get("state_machines", [])),
        }
        # Enrich with LLM usage if available
        llm = result.get("llm_usage")
        if llm:
            result["project_stats"]["llm_total_calls"] = llm.get("total_calls", 0)
            result["project_stats"]["llm_total_cost"] = llm.get("total_cost_usd", 0)
            result["project_stats"]["llm_total_tokens"] = llm.get("total_input_tokens", 0) + llm.get("total_output_tokens", 0)
        manifest = result.get("pipeline_manifest")
        if manifest:
            result["project_stats"]["pipeline_duration_ms"] = manifest.get("total_duration_ms", 0)
            result["project_stats"]["pipeline_stages"] = len(manifest.get("stages", []))
        print(f"  [INFO] Project stats: {result['project_stats']}")

        # Build requirements from traceability data (if no journal.json)
        if result["traceability"] and not result["nodes"]:
            for trace in result["traceability"]:
                req_id = trace["req_id"]
                result["nodes"][f"node-{req_id}"] = {
                    "id": f"node-{req_id}",
                    "requirement_id": req_id,
                    "title": req_id,  # Will be enriched from other sources
                    "type": trace.get("type", "functional"),
                    "priority": trace.get("priority", "should"),
                    "linked_user_stories": trace.get("user_stories", []),
                    "linked_test_cases": trace.get("test_cases", [])
                }

        return result

    # ============ Kilo Agent Integration ============

    async def _handle_kilo_task(self, ws, data: Dict[str, Any]):
        """
        Handle Kilo Agent task request from UI.

        Expected data:
            - node_id: ID of the node to modify
            - content: Current content (e.g., mermaid code)
            - file_path: Path to the file (for saving)
            - task: User's task description
            - content_type: Type of content (diagram, requirement, etc.)
        """
        print(f"\n[KILO] Received task request: {data.get('task', '')[:50]}...")
        content = data.get('content', '')
        file_path = data.get('file_path', '')
        task = data.get('task', '')
        node_id = data.get('node_id', '')
        content_type = data.get('content_type', 'diagram')

        print(f"[KILO] Node: {node_id}, Type: {content_type}")

        if not task:
            print("[KILO] ERROR: No task provided")
            await self.emitter.kilo_task_error(node_id, "No task provided")
            return

        # Emit processing event
        print(f"[KILO] Processing task...")
        await self.emitter.kilo_task_processing(node_id, task)

        try:
            # Build prompt for Kilo Agent
            prompt = self._build_kilo_prompt(content, task, content_type)

            # Execute via Kilo Agent (subprocess)
            result = await self._execute_kilo_agent(prompt)

            if result.get('success'):
                response = result.get('response', '')
                print(f"[KILO] Response length: {len(response)}")
                print(f"[KILO] Response preview: {response[:300]}...")

                # Extract new content based on type
                if content_type == 'diagram':
                    new_content = self._extract_mermaid(response)
                    print(f"[KILO] Extracted mermaid: {bool(new_content)}")
                    if new_content:
                        print(f"[KILO] Mermaid preview: {new_content[:100]}...")
                        # Save to file if path provided
                        if file_path:
                            await self._save_content(file_path, new_content)
                            print(f"[KILO] Saved to: {file_path}")

                        # Emit success event
                        print(f"[KILO] Emitting diagram_updated for {node_id}")
                        await self.emitter.diagram_updated(node_id, new_content, file_path)
                        print(f"[KILO] Event emitted successfully!")
                    else:
                        print(f"[KILO] ERROR: No mermaid block found in response!")
                        await self.emitter.kilo_task_error(
                            node_id, "No valid Mermaid diagram found in response"
                        )
                else:
                    # Generic content update
                    await self.emitter.content_updated(node_id, response, content_type)
            else:
                await self.emitter.kilo_task_error(
                    node_id, result.get('error', 'Unknown error')
                )

        except Exception as e:
            await self.emitter.kilo_task_error(node_id, str(e))

    def _build_kilo_prompt(self, content: str, task: str, content_type: str = 'diagram') -> str:
        """Build the prompt for Kilo Agent."""
        if content_type == 'diagram':
            return f"""Passe dieses Mermaid-Diagramm an:

```mermaid
{content}
```

Aenderung: {task}

WICHTIG:
- Gib das aktualisierte Mermaid-Diagramm in einem ```mermaid Code-Block zurueck
- Behalte die Grundstruktur bei, es sei denn, die Aenderung erfordert eine andere Struktur
- Stelle sicher, dass die Mermaid-Syntax korrekt ist"""
        else:
            return f"""Aktueller Inhalt:

{content}

Aufgabe: {task}

Bitte fuehre die angeforderte Aenderung durch und gib den aktualisierten Inhalt zurueck."""

    async def _execute_kilo_agent(self, prompt: str) -> Dict[str, Any]:
        """
        Execute Kilo Agent with the given prompt.

        Priority (geaendert per User-Anfrage):
        1. user_kilo_agent.py (ERSTE Prioritaet)
        2. Direct OpenRouter API call
        3. Subprocess call to claude CLI
        """
        try:
            # Try user_kilo_agent.py FIRST (per User-Anfrage)
            print("[KILO] Trying user_kilo_agent.py first...")
            result = await self._execute_via_fallback(prompt)
            if result.get('success'):
                print("[KILO] user_kilo_agent.py succeeded!")
                return result
            else:
                print(f"[KILO] user_kilo_agent.py failed: {result.get('error', 'unknown')[:100]}")

            # Try OpenRouter API as second option
            api_key = os.environ.get("OPENROUTER_API_KEY")
            print(f"[KILO] API Key available: {bool(api_key)}")
            if api_key:
                print("[KILO] Calling OpenRouter API...")
                result = await self._execute_via_api(prompt, api_key)
                print(f"[KILO] API result success: {result.get('success')}")
                if result.get('success'):
                    return result
                else:
                    print(f"[KILO] API error: {result.get('error', 'unknown')[:100]}")

            # Try subprocess to claude CLI as last resort
            print("[KILO] Trying claude CLI subprocess...")
            result = await self._execute_via_subprocess_cli_only(prompt)
            print(f"[KILO] CLI result: {result.get('success')}")
            return result
        except Exception as e:
            print(f"[KILO] Exception: {str(e)}")
            return {
                'success': False,
                'error': f"Kilo Agent execution failed: {str(e)}"
            }

    async def _execute_via_api(self, prompt: str, api_key: str) -> Dict[str, Any]:
        """Execute via direct OpenRouter API call using httpx."""
        try:
            import httpx

            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8085",
                "X-Title": "RE System Dashboard"
            }
            # Get model from config or environment
            dashboard_model = getattr(self, 'config', {}).get("dashboard", {}).get("model")
            model = dashboard_model or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Du bist ein hilfreicher Assistent für Software-Engineering. Beantworte auf Deutsch."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 4000,
                "temperature": 0.7
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {
                        'success': True,
                        'response': content
                    }
                else:
                    return {
                        'success': False,
                        'error': f"API error {response.status_code}: {response.text[:200]}"
                    }
        except ImportError:
            return {
                'success': False,
                'error': 'httpx not installed - trying fallback'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"API call failed: {str(e)}"
            }

    async def _execute_via_subprocess(self, prompt: str) -> Dict[str, Any]:
        """Execute via subprocess (claude CLI or python script)."""
        try:
            # Option 1: Use claude CLI if available
            process = await asyncio.create_subprocess_exec(
                'claude', '-p', prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120  # 2 minute timeout
            )

            if process.returncode == 0:
                return {
                    'success': True,
                    'response': stdout.decode('utf-8')
                }
            else:
                return {
                    'success': False,
                    'error': stderr.decode('utf-8') or 'Claude CLI returned non-zero exit code'
                }
        except FileNotFoundError:
            # Claude CLI not found, try fallback
            return await self._execute_via_fallback(prompt)
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'Kilo Agent request timed out after 120 seconds'
            }

    async def _execute_via_subprocess_cli_only(self, prompt: str) -> Dict[str, Any]:
        """Execute via claude CLI only (no fallback - used when fallback was already tried)."""
        try:
            process = await asyncio.create_subprocess_exec(
                'claude', '-p', prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120  # 2 minute timeout
            )

            if process.returncode == 0:
                return {
                    'success': True,
                    'response': stdout.decode('utf-8')
                }
            else:
                return {
                    'success': False,
                    'error': stderr.decode('utf-8') or 'Claude CLI returned non-zero exit code'
                }
        except FileNotFoundError:
            return {
                'success': False,
                'error': 'Claude CLI not found and all other methods failed'
            }
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'Claude CLI request timed out after 120 seconds'
            }

    async def _execute_via_fallback(self, prompt: str) -> Dict[str, Any]:
        """Fallback execution method using user_kilo_agent.py if available."""
        try:
            # Try to use the local user_kilo_agent.py
            script_path = Path(__file__).parent.parent.parent / "user_kilo_agent.py"

            if script_path.exists():
                process = await asyncio.create_subprocess_exec(
                    'python', str(script_path), '--prompt', prompt,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=120
                )

                if process.returncode == 0:
                    return {
                        'success': True,
                        'response': stdout.decode('utf-8')
                    }
                else:
                    return {
                        'success': False,
                        'error': stderr.decode('utf-8') or 'Script returned non-zero exit code'
                    }
            else:
                return {
                    'success': False,
                    'error': 'Neither Claude CLI nor user_kilo_agent.py found. Please install Claude Code CLI.'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _extract_mermaid(self, response: str) -> Optional[str]:
        """Extract Mermaid code block from response."""
        # Pattern for ```mermaid ... ``` blocks
        pattern = r'```mermaid\s*([\s\S]*?)\s*```'
        match = re.search(pattern, response, re.IGNORECASE)

        if match:
            return match.group(1).strip()

        # Fallback: try to find any code block that looks like Mermaid
        fallback_pattern = r'```\s*((?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey)[\s\S]*?)\s*```'
        match = re.search(fallback_pattern, response, re.IGNORECASE)

        if match:
            return match.group(1).strip()

        return None

    async def _save_content(self, file_path: str, content: str):
        """Save content to file."""
        path = Path(file_path)

        # Security: only allow saving to enterprise_output directory
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        try:
            path.relative_to(output_dir)
        except ValueError:
            # Path is outside output_dir, construct safe path
            path = output_dir / path.name

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        print(f"  [KILO] Saved updated content to: {path}")

    # =====================================================================
    # Wizard Endpoints - Requirements Input Wizard
    # =====================================================================

    async def _handle_wizard(self, request: web.Request) -> web.Response:
        """Serve the wizard HTML page."""
        wizard_path = self._static_path / "wizard.html"
        if wizard_path.exists():
            return web.FileResponse(wizard_path)
        else:
            # Fallback: redirect to main dashboard with wizard tab
            return web.HTTPFound("/")

    # ============ Pipeline Execution Endpoints ============

    async def _handle_config_validate(self, request: web.Request) -> web.Response:
        """Validate configuration: API keys, config file, dependencies."""
        issues = []
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        api_key_set = bool(api_key and len(api_key) > 10)

        if not api_key_set:
            issues.append("OPENROUTER_API_KEY not set or too short")

        config_path = Path(__file__).parent.parent / "re_config.yaml"
        if not config_path.exists():
            issues.append("re_config.yaml not found")

        return web.json_response({
            "valid": len(issues) == 0,
            "issues": issues,
            "api_key_set": api_key_set
        })

    async def _handle_pipeline_run(self, request: web.Request) -> web.Response:
        """Start the enterprise pipeline as a background task (single project)."""
        if self._pipeline_task and not self._pipeline_task.done():
            return web.json_response(
                {"error": "Pipeline already running"}, status=409
            )

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        project_path = data.get("project_path", "")
        config_path = data.get("config_path") or str(Path(__file__).parent.parent / "re_config.yaml")

        if not project_path or not Path(project_path).exists():
            return web.json_response(
                {"error": f"Project file not found: {project_path}"}, status=400
            )

        if not os.environ.get("OPENROUTER_API_KEY"):
            return web.json_response(
                {"error": "OPENROUTER_API_KEY not set"}, status=400
            )

        self._start_batch_pipeline([{"project_path": project_path, "config_path": config_path}])
        return web.json_response({"status": "started", "projects": 1})

    async def _handle_pipeline_batch(self, request: web.Request) -> web.Response:
        """Start the enterprise pipeline for multiple projects sequentially."""
        if self._pipeline_task and not self._pipeline_task.done():
            return web.json_response(
                {"error": "Pipeline already running"}, status=409
            )

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        projects = data.get("projects", [])
        config_path = data.get("config_path") or str(Path(__file__).parent.parent / "re_config.yaml")

        if not projects:
            return web.json_response({"error": "No projects provided"}, status=400)

        if not os.environ.get("OPENROUTER_API_KEY"):
            return web.json_response(
                {"error": "OPENROUTER_API_KEY not set"}, status=400
            )

        # Validate all project files exist
        missing = [p for p in projects if not Path(p).exists()]
        if missing:
            return web.json_response(
                {"error": f"Files not found: {', '.join(missing)}"}, status=400
            )

        queue = [{"project_path": p, "config_path": config_path} for p in projects]
        self._start_batch_pipeline(queue)
        return web.json_response({"status": "started", "projects": len(queue)})

    def _start_batch_pipeline(self, queue: list):
        """Initialize status and launch the batch runner task."""
        self._pipeline_queue = list(queue)
        first_name = Path(queue[0]["project_path"]).stem
        self._pipeline_status = {
            "running": True, "step": 0, "total": 15,
            "description": "Starting...", "error": None, "output_dir": None,
            "project_index": 1, "project_total": len(queue),
            "project_name": first_name
        }

        # Register progress tracker (idempotent — old callback replaced)
        if hasattr(self, '_progress_cb'):
            self.emitter.remove_callback(self._progress_cb)

        async def _track_progress(event):
            if event.type == EventType.PIPELINE_PROGRESS:
                self._pipeline_status["step"] = event.data.get("step", 0)
                self._pipeline_status["description"] = event.data.get("description", "")
            elif event.type == EventType.PIPELINE_COMPLETE:
                # Will be handled per-project in the batch loop
                pass
            elif event.type == EventType.PIPELINE_ERROR:
                self._pipeline_status["error"] = event.data.get("error", "Unknown error")

        self._progress_cb = _track_progress
        self.emitter.add_callback(_track_progress)

        self._pipeline_task = asyncio.create_task(self._run_batch_pipeline())

    async def _run_batch_pipeline(self):
        """Run all queued projects sequentially."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from requirements_engineer.run_re_system import run_enterprise_mode

        total_projects = len(self._pipeline_queue)
        results = []

        for idx, item in enumerate(self._pipeline_queue):
            project_path = item["project_path"]
            config_path = item["config_path"]
            project_name = Path(project_path).stem

            # Update status for this project
            self._pipeline_status.update({
                "running": True, "step": 0, "error": None,
                "project_index": idx + 1, "project_total": total_projects,
                "project_name": project_name
            })

            # Emit a batch progress event so the UI knows which project
            await self.emitter.emit(EventType.PIPELINE_PROGRESS, {
                "step": 0, "total": 15,
                "description": f"Starting {project_name}...",
                "percent": 0, "cost_usd": 0, "total_tokens": 0,
                "project_index": idx + 1, "project_total": total_projects,
                "project_name": project_name
            })

            try:
                output_dir = await run_enterprise_mode(
                    project_path=project_path,
                    config_path=config_path,
                    emitter=self.emitter,
                )
                results.append({
                    "project": project_name, "status": "complete",
                    "output_dir": str(output_dir) if output_dir else None
                })
            except asyncio.CancelledError:
                results.append({"project": project_name, "status": "cancelled"})
                break
            except Exception as e:
                import traceback
                error_msg = f"{type(e).__name__}: {e}"
                print(f"[PIPELINE ERROR] {project_name}: {error_msg}")
                traceback.print_exc()
                results.append({"project": project_name, "status": "error", "error": error_msg})
                # Continue to next project — don't abort the batch
                await self.emitter.emit(EventType.PIPELINE_ERROR, {
                    "error": f"{project_name}: {error_msg}",
                    "project_index": idx + 1, "project_total": total_projects,
                    "continues": idx + 1 < total_projects
                })

        # All done
        self._pipeline_status["running"] = False
        self._pipeline_status["step"] = 15
        self._pipeline_status["description"] = "All projects complete"
        self._pipeline_queue = []

        completed = [r for r in results if r["status"] == "complete"]
        failed = [r for r in results if r["status"] == "error"]

        await self.emitter.emit(EventType.PIPELINE_COMPLETE, {
            "summary": {
                "projects_total": total_projects,
                "projects_completed": len(completed),
                "projects_failed": len(failed),
                "results": results,
                "output_dir": completed[-1]["output_dir"] if completed else None
            }
        })

    async def _handle_pipeline_status(self, request: web.Request) -> web.Response:
        """Get current pipeline execution status."""
        return web.json_response(self._pipeline_status)

    async def _handle_pipeline_stop(self, request: web.Request) -> web.Response:
        """Stop a running pipeline (cancels current project and remaining queue)."""
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_queue = []  # Clear remaining queue
            self._pipeline_task.cancel()
            self._pipeline_status["running"] = False
            self._pipeline_status["error"] = "Cancelled by user"
            await self.emitter.emit(EventType.PIPELINE_ERROR, {"error": "Cancelled by user"})
            return web.json_response({"status": "cancelled"})
        return web.json_response({"status": "not_running"})

    async def _handle_pipeline_manifest(self, request: web.Request) -> web.Response:
        """Load pipeline_manifest.json from the most recent (or specified) output directory."""
        import json as _json
        # Allow specifying a custom output_dir via query param
        output_dir = request.query.get("output_dir", "")
        if not output_dir:
            # Try to get from current pipeline status
            output_dir = self._pipeline_status.get("output_dir", "")
        if not output_dir:
            # Fall back: find most recent enterprise_output folder
            enterprise_root = Path("enterprise_output")
            if enterprise_root.exists():
                subdirs = sorted(enterprise_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
                for d in subdirs:
                    if d.is_dir() and (d / "pipeline_manifest.json").exists():
                        output_dir = str(d)
                        break
        if not output_dir:
            return web.json_response({"error": "No pipeline output found"}, status=404)

        manifest_path = Path(output_dir) / "pipeline_manifest.json"
        if not manifest_path.exists():
            return web.json_response({"error": "pipeline_manifest.json not found"}, status=404)

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            return web.json_response(data)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # ============ Wizard Endpoints ============

    async def _handle_wizard_extract(self, request: web.Request) -> web.Response:
        """
        Extract requirements from uploaded documents using arch_team.

        Accepts multipart form data with 'documents' field containing files.
        Returns extracted requirements in JSON format.
        """
        try:
            # 1. CHECK API KEY FIRST - ChunkMiner needs OPENROUTER_API_KEY
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                print("  [WIZARD] ERROR: OPENROUTER_API_KEY not set!")
                return web.json_response({
                    "success": False,
                    "error": "OPENROUTER_API_KEY nicht gesetzt. Bitte .env Datei prüfen und Server neu starten."
                }, status=500)
            print(f"  [WIZARD] API Key found: {api_key[:8]}...{api_key[-4:]}")

            reader = await request.multipart()
            all_items = []
            extraction_errors = []

            # Try to import arch_team
            try:
                from requirements_engineer.importers.arch_team_importer import (
                    _find_arch_team_path,
                    _ensure_arch_team_in_path
                )

                if not _find_arch_team_path():
                    return web.json_response({
                        "success": False,
                        "error": "arch_team not found. Please install it as a git submodule in external/arch_team"
                    }, status=500)

                _ensure_arch_team_in_path()
                from arch_team.agents.chunk_miner import ChunkMinerAgent

                # Initialize ChunkMiner with model from config or default
                print("  [WIZARD] Initializing ChunkMinerAgent...")
                importer_model = self.config.get("importers", {}).get("arch_team", {}).get("model", "anthropic/claude-haiku-4.5")
                agent = ChunkMinerAgent(
                    source="wizard",
                    default_model=importer_model
                )
                print("  [WIZARD] ChunkMinerAgent initialized successfully")

                # Process each uploaded file
                files_processed = 0
                async for field in reader:
                    print(f"  [WIZARD] Field: name={field.name}, filename={field.filename}")
                    if field.name == 'documents':
                        filename = field.filename
                        file_bytes = await field.read()
                        files_processed += 1

                        # Get content_type from headers (BodyPartReader doesn't have content_type attribute)
                        content_type = ""
                        if hasattr(field, 'headers') and field.headers:
                            content_type = field.headers.get('Content-Type', '')
                        # Infer content_type from filename if empty
                        if not content_type and filename:
                            ext = filename.lower().split('.')[-1] if '.' in filename else ''
                            content_type_map = {
                                'md': 'text/markdown',
                                'txt': 'text/plain',
                                'pdf': 'application/pdf',
                                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                'json': 'application/json'
                            }
                            content_type = content_type_map.get(ext, '')
                            print(f"  [WIZARD] Inferred content_type from extension: {content_type}")

                        print(f"  [WIZARD] Processing file {files_processed}: {filename} ({len(file_bytes)} bytes, type={content_type})")

                        # Extract requirements - pass filename and content_type for proper parsing!
                        try:
                            print(f"  [WIZARD] Calling ChunkMiner.mine_files_or_texts_collect for {filename}...")
                            items = agent.mine_files_or_texts_collect(
                                files_or_texts=[{
                                    "filename": filename,
                                    "data": file_bytes,
                                    "content_type": content_type
                                }],
                                neighbor_refs=True,
                                chunk_options={"max_tokens": 1200, "overlap_tokens": 300}
                            )
                            print(f"  [WIZARD] ChunkMiner returned {len(items)} items from {filename}")

                            if len(items) == 0:
                                extraction_errors.append(f"{filename}: 0 Requirements extrahiert (Datei möglicherweise leer oder LLM-Fehler)")

                        except Exception as mine_err:
                            error_msg = f"{filename}: {str(mine_err)}"
                            print(f"  [WIZARD] ChunkMiner error for {filename}: {mine_err}")
                            import traceback
                            traceback.print_exc()
                            extraction_errors.append(error_msg)
                            items = []

                        # Add source info to each item
                        for item in items:
                            item['source_file'] = filename

                        all_items.extend(items)
                        print(f"  [WIZARD] Extracted {len(items)} requirements from {filename}")

                print(f"  [WIZARD] Total files processed: {files_processed}, total items: {len(all_items)}")
                if extraction_errors:
                    print(f"  [WIZARD] Extraction errors: {extraction_errors}")

                if files_processed == 0:
                    return web.json_response({
                        "success": False,
                        "error": "Keine Dateien empfangen. Bitte laden Sie mindestens eine Datei hoch."
                    }, status=400)

                # If all files failed extraction, return error
                if len(all_items) == 0 and files_processed > 0:
                    error_detail = "; ".join(extraction_errors) if extraction_errors else "Unbekannter Fehler bei der LLM-Extraktion"
                    print(f"  [WIZARD] CRITICAL: 0 items extracted from {files_processed} files!")
                    return web.json_response({
                        "success": False,
                        "error": f"Keine Requirements extrahiert aus {files_processed} Datei(en). Mögliche Ursachen: LLM-API Fehler, leere Dateien oder ungültiges Format. Details: {error_detail}"
                    }, status=500)

            except ImportError as e:
                return web.json_response({
                    "success": False,
                    "error": f"arch_team import failed: {str(e)}"
                }, status=500)

            # Convert to consistent format
            print(f"  [WIZARD] Converting {len(all_items)} extracted items to requirements")
            requirements = []
            for idx, item in enumerate(all_items):
                req = {
                    "id": item.get("req_id", f"REQ-{idx+1:03d}"),
                    "title": item.get("title", ""),
                    "description": item.get("title", ""),
                    "category": self._map_tag_to_category(item.get("tag", "functional")),
                    "priority": item.get("priority", "should"),
                    "acceptance_criteria": [item.get("measurable_criteria")] if item.get("measurable_criteria") else [],
                    "tags": [item.get("tag")] if item.get("tag") else [],
                    "evidence": item.get("evidence", ""),
                    "source_file": item.get("source_file", "unknown")
                }
                title_preview = req['title'][:50] + "..." if len(req['title']) > 50 else req['title']
                print(f"  [WIZARD] Requirement {idx+1}: {req['id']} - {title_preview}")
                requirements.append(req)

            print(f"  [WIZARD] Returning {len(requirements)} requirements to frontend")

            # Include warnings about partial failures
            response_data = {
                "success": True,
                "count": len(requirements),
                "requirements": requirements,
                "files_processed": files_processed
            }
            if extraction_errors:
                response_data["warnings"] = extraction_errors

            return web.json_response(response_data)

        except Exception as e:
            print(f"  [WIZARD] Error: {str(e)}")
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _handle_wizard_generate_json(self, request: web.Request) -> web.Response:
        """
        Generate RE-System input JSON from wizard data.

        Accepts two formats:
        1. RE-System format (has "Name" key) - passed through directly
        2. Legacy arch_team format (has "extracted_requirements") - converted

        Saves to re_ideas/ directory for use with run_re_system.py.
        """
        try:
            data = await request.json()

            # Check if already in RE-System format (from updated wizard)
            if "Name" in data:
                # New format: already RE-System compatible
                output = {k: v for k, v in data.items() if k != "save_path"}
                save_requested = data.get("save_path", False)
            else:
                # Legacy format: arch_team extracted or old wizard format
                extracted_reqs = data.get("extracted_requirements", [])
                manual_reqs = data.get("manual_requirements", [])
                direct_reqs = data.get("requirements", [])

                if extracted_reqs:
                    from requirements_engineer.importers.arch_team_converter import (
                        convert_arch_team_to_v2,
                        merge_requirements,
                        validate_v2_output
                    )
                    all_arch_team_reqs = merge_requirements(extracted_reqs, manual_reqs)
                    output = convert_arch_team_to_v2(
                        items=all_arch_team_reqs,
                        project_name=data.get("project_name", "Unnamed Project"),
                        project_domain=data.get("domain", "custom"),
                        project_description=data.get("description", ""),
                        autonomy_level=data.get("autonomy_level", "medium"),
                        target_users=data.get("target_users", []),
                        constraints={
                            "technical": data.get("technical_constraints", []),
                            "regulatory": data.get("regulatory_constraints", []),
                            "timeline": data.get("timeline", "")
                        },
                        agents=data.get("agents", []),
                        integrations=data.get("integrations", []),
                        renumber_ids=True,
                        preserve_metadata=True
                    )
                    validation_errors = validate_v2_output(output)
                    if validation_errors:
                        print(f"  [WIZARD] Validation warnings: {validation_errors}")
                else:
                    # Convert old wizard format to RE-System format
                    project_name = data.get("project_name", data.get("name", "Unnamed Project"))
                    output = {
                        "Name": project_name.replace(' ', '_').lower(),
                        "Title": project_name,
                        "Domain": data.get("domain", "custom"),
                        "Context": {"summary": data.get("description", "")},
                        "Stakeholders": [],
                        "Initial Requirements": [
                            r if isinstance(r, str) else r.get("title", "")
                            for r in (direct_reqs or manual_reqs)
                        ],
                        "Constraints": {
                            "technical": data.get("technical_constraints", []),
                            "regulatory": data.get("regulatory_constraints", []),
                            "timeline": data.get("timeline", "")
                        },
                        "Work Division": "per_feature",
                        "Enterprise Options": {
                            "generate_user_stories": True,
                            "generate_api_spec": True,
                            "generate_data_dictionary": True,
                            "generate_gherkin": True,
                            "enable_self_critique": True,
                            "max_passes": 5,
                            "output_format": "markdown"
                        }
                    }
                save_requested = data.get("save_path", False)

            # Save to re_ideas/ directory
            file_path_str = None
            if save_requested:
                output_dir = Path(__file__).parent.parent.parent / "re_ideas"
                output_dir.mkdir(parents=True, exist_ok=True)
                safe_name = output.get("Name", output.get("Title", "unnamed")).replace(' ', '_').replace('/', '_')
                file_path = output_dir / f"{safe_name}_input.json"
                file_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
                file_path_str = str(file_path)
                print(f"  [WIZARD] Saved RE-System input to: {file_path}")

            req_count = len(output.get("Initial Requirements", output.get("requirements", [])))

            return web.json_response({
                "success": True,
                "json": output,
                "requirement_count": req_count,
                "file_path": file_path_str
            })

        except Exception as e:
            import traceback
            print(f"  [WIZARD] Error generating JSON: {str(e)}")
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    def _map_tag_to_category(self, tag: str) -> str:
        """Map arch_team tags to RE System categories."""
        mapping = {
            "functional": "functional",
            "security": "security",
            "performance": "performance",
            "usability": "frontend",
            "reliability": "non_functional",
            "compliance": "non_functional",
            "interface": "integration",
            "data": "backend",
            "constraint": "non_functional"
        }
        return mapping.get(tag, "functional")

    def _map_category_to_tag(self, category: str) -> str:
        """Map RE System category to arch_team tag."""
        mapping = {
            "functional": "functional",
            "non_functional": "performance",
            "security": "security",
            "performance": "performance",
            "frontend": "usability",
            "backend": "data",
            "integration": "interface",
            "constraint": "constraint"
        }
        return mapping.get(category, "functional")

    # ============ Wizard Validation Methods ============

    async def _handle_wizard_validate_batch(self, request: web.Request) -> web.Response:
        """
        Validate all requirements in parallel using arch_team ValidationDelegator.
        """
        try:
            data = await request.json()
            requirements = data.get("requirements", [])
            threshold = data.get("threshold", 0.7)
            correlation_id = data.get("correlation_id")

            if not requirements:
                return web.json_response({
                    "success": True,
                    "total_count": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "results": []
                })

            # Emit start event
            await self.emitter.validation_started(len(requirements), "AUTO")

            # Try to import arch_team ValidationDelegator
            try:
                from requirements_engineer.importers.arch_team_importer import (
                    _find_arch_team_path,
                    _ensure_arch_team_in_path
                )

                if not _find_arch_team_path():
                    return web.json_response({
                        "success": False,
                        "error": "arch_team not found. Please install it as a git submodule."
                    }, status=500)

                _ensure_arch_team_in_path()
                from arch_team.agents.validation_delegator import ValidationDelegatorAgent

                # Convert requirements to arch_team format
                arch_team_reqs = [
                    {
                        "req_id": r.get("id", f"REQ-{idx:03d}"),
                        "title": r.get("title", r.get("description", "")),
                        "tag": self._map_category_to_tag(r.get("category", "functional"))
                    }
                    for idx, r in enumerate(requirements)
                ]

                # Run parallel validation
                delegator = ValidationDelegatorAgent(max_concurrent=5)
                batch_result = await delegator.validate_batch(
                    requirements=arch_team_reqs,
                    correlation_id=correlation_id,
                    threshold=threshold
                )

                # Convert results
                results = delegator.to_dict_results(batch_result)

                # Emit complete event
                await self.emitter.validation_complete(
                    batch_result.passed_count,
                    batch_result.failed_count,
                    batch_result.total_time_ms
                )

                return web.json_response({
                    "success": True,
                    "total_count": batch_result.total_count,
                    "passed_count": batch_result.passed_count,
                    "failed_count": batch_result.failed_count,
                    "error_count": batch_result.error_count,
                    "total_time_ms": batch_result.total_time_ms,
                    "avg_time_per_item_ms": batch_result.avg_time_per_item_ms,
                    "results": results
                })

            except ImportError as e:
                print(f"[WIZARD] arch_team import failed: {e}")
                return web.json_response({
                    "success": False,
                    "error": f"arch_team import failed: {str(e)}"
                }, status=500)

        except Exception as e:
            import traceback
            print(f"[WIZARD] Validation error: {e}")
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _handle_wizard_decide(self, request: web.Request) -> web.Response:
        """
        Use DecisionMaker to decide actions for failed requirements.
        Actions: SPLIT, REWRITE, ACCEPT, CLARIFY, REJECT
        """
        try:
            data = await request.json()
            requirements = data.get("requirements", [])
            mode = data.get("mode", "AUTO")

            if not requirements:
                return web.json_response({
                    "success": True,
                    "decisions": [],
                    "statistics": {}
                })

            try:
                from requirements_engineer.importers.arch_team_importer import (
                    _find_arch_team_path,
                    _ensure_arch_team_in_path
                )

                if not _find_arch_team_path():
                    return web.json_response({
                        "success": False,
                        "error": "arch_team not found"
                    }, status=500)

                _ensure_arch_team_in_path()
                from arch_team.agents.decision_maker_agent import DecisionMakerAgent

                # Initialize decision maker
                agent = DecisionMakerAgent()

                # Process each requirement
                decisions = []
                stats = {"split": 0, "rewrite": 0, "accept": 0, "clarify": 0, "reject": 0}

                for req in requirements:
                    decision = await agent.decide_single(req)
                    decisions.append(decision)

                    action = decision.get("action", "").lower()
                    if action in stats:
                        stats[action] += 1

                    # Emit decision event
                    await self.emitter.decision_made(
                        req.get("req_id", ""),
                        decision.get("action", ""),
                        decision.get("reason", ""),
                        decision.get("confidence", 0.0)
                    )

                return web.json_response({
                    "success": True,
                    "decisions": decisions,
                    "statistics": {
                        "split_count": stats["split"],
                        "rewrite_count": stats["rewrite"],
                        "accept_count": stats["accept"],
                        "clarify_count": stats["clarify"],
                        "reject_count": stats["reject"]
                    }
                })

            except ImportError as e:
                # Fallback: simple heuristic-based decisions
                print(f"[WIZARD] DecisionMaker not available, using heuristics: {e}")
                decisions = []
                stats = {"split": 0, "rewrite": 0, "accept": 0, "clarify": 0, "reject": 0}

                for req in requirements:
                    score = req.get("score", 0.5)
                    evaluation = req.get("evaluation", [])

                    # Simple heuristics
                    if score >= 0.65:
                        action = "ACCEPT"
                        reason = "Score is close to threshold"
                    elif any(e.get("criterion") == "atomic" and not e.get("passed") for e in evaluation):
                        action = "SPLIT"
                        reason = "Requirement is not atomic"
                    elif any(e.get("criterion") in ["measurability", "testability"] and not e.get("passed") for e in evaluation):
                        action = "CLARIFY"
                        reason = "Missing measurable criteria"
                    elif score < 0.3:
                        action = "REJECT"
                        reason = "Score too low for improvement"
                    else:
                        action = "REWRITE"
                        reason = "Automatic improvement needed"

                    decisions.append({
                        "req_id": req.get("req_id"),
                        "action": action,
                        "reason": reason,
                        "confidence": 0.7
                    })
                    stats[action.lower()] += 1

                return web.json_response({
                    "success": True,
                    "decisions": decisions,
                    "statistics": {
                        "split_count": stats["split"],
                        "rewrite_count": stats["rewrite"],
                        "accept_count": stats["accept"],
                        "clarify_count": stats["clarify"],
                        "reject_count": stats["reject"]
                    },
                    "_fallback": True
                })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _handle_wizard_improve(self, request: web.Request) -> web.Response:
        """
        Run the complete improvement workflow using RequirementsOrchestrator.
        """
        try:
            data = await request.json()
            requirements = data.get("requirements", [])
            config = data.get("config", {})
            correlation_id = data.get("correlation_id")

            if not requirements:
                return web.json_response({
                    "success": True,
                    "requirements": [],
                    "improved_count": 0
                })

            try:
                from requirements_engineer.importers.arch_team_importer import (
                    _find_arch_team_path,
                    _ensure_arch_team_in_path
                )

                if not _find_arch_team_path():
                    return web.json_response({
                        "success": False,
                        "error": "arch_team not found"
                    }, status=500)

                _ensure_arch_team_in_path()
                from arch_team.agents.requirements_orchestrator import (
                    RequirementsOrchestrator,
                    OrchestratorConfig,
                    WorkflowMode
                )

                # Configure orchestrator
                mode = WorkflowMode.AUTO if config.get("mode") == "AUTO" else WorkflowMode.MANUAL

                orch_config = OrchestratorConfig(
                    quality_threshold=config.get("quality_threshold", 0.7),
                    max_iterations=config.get("max_iterations", 3),
                    mode=mode
                )

                # Convert requirements to arch_team format
                arch_team_reqs = [
                    {
                        "req_id": r.get("id", f"REQ-{idx:03d}"),
                        "title": r.get("title", r.get("description", "")),
                        "tag": self._map_category_to_tag(r.get("category", "functional"))
                    }
                    for idx, r in enumerate(requirements)
                ]

                # Progress callback
                async def progress_callback(stage, completed, total, message):
                    await self.emitter.validation_progress(completed, total, message, stage)

                # Run orchestrator
                orchestrator = RequirementsOrchestrator(
                    config=orch_config,
                    progress_callback=progress_callback
                )

                result = await orchestrator.run(
                    requirements=arch_team_reqs,
                    correlation_id=correlation_id
                )

                # Convert results back to wizard format
                improved_reqs = [
                    {
                        "id": r.get("req_id"),
                        "title": r.get("title"),
                        "description": r.get("title"),
                        "category": "functional",
                        "priority": r.get("priority", "should"),
                        "_validated": True,
                        "_score": r.get("_validation_score"),
                        "_rewritten": r.get("_rewritten", False)
                    }
                    for r in result.requirements
                ]

                return web.json_response({
                    "success": result.success,
                    "workflow_id": result.workflow_id,
                    "initial_pass_rate": result.initial_pass_rate,
                    "final_pass_rate": result.final_pass_rate,
                    "total_iterations": result.total_iterations,
                    "requirements": improved_reqs,
                    "improved_count": sum(1 for r in result.requirements if r.get("_rewritten")),
                    "total_time_ms": result.total_time_ms
                })

            except ImportError as e:
                print(f"[WIZARD] Orchestrator not available: {e}")
                # Return original requirements as fallback
                return web.json_response({
                    "success": True,
                    "requirements": requirements,
                    "improved_count": 0,
                    "_fallback": True,
                    "message": "Orchestrator not available, returning original requirements"
                })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _handle_wizard_clarify(self, request: web.Request) -> web.Response:
        """
        Generate clarification questions using ClarificationAgent.
        """
        try:
            data = await request.json()
            req_id = data.get("req_id")
            requirement_text = data.get("requirement_text", "")
            evaluation = data.get("evaluation", [])

            try:
                from requirements_engineer.importers.arch_team_importer import (
                    _find_arch_team_path,
                    _ensure_arch_team_in_path
                )

                if not _find_arch_team_path():
                    return web.json_response({
                        "success": False,
                        "error": "arch_team not found"
                    }, status=500)

                _ensure_arch_team_in_path()
                from arch_team.agents.clarification_agent import (
                    ClarificationAgent,
                    ClarificationTask
                )

                task = ClarificationTask(
                    req_id=req_id,
                    requirement_text=requirement_text,
                    validation_results=evaluation,
                    overall_score=data.get("score", 0.0)
                )

                agent = ClarificationAgent()
                result = await agent.analyze(task)

                # Emit event
                if result.needs_clarification:
                    await self.emitter.clarification_needed(req_id, [q.to_dict() for q in result.questions])

                return web.json_response({
                    "success": True,
                    "needs_clarification": result.needs_clarification,
                    "questions": [q.to_dict() for q in result.questions],
                    "auto_fixable_criteria": result.auto_fixable_criteria,
                    "unfixable_criteria": result.unfixable_criteria
                })

            except ImportError as e:
                # Fallback: generate simple questions based on failed criteria
                print(f"[WIZARD] ClarificationAgent not available: {e}")
                questions = []

                for eval_item in evaluation:
                    if not eval_item.get("passed"):
                        criterion = eval_item.get("criterion", "")
                        questions.append({
                            "criterion": criterion,
                            "question_text": f"Was fehlt bei '{criterion}' für '{requirement_text[:50]}...'?",
                            "suggested_answers": ["Bitte spezifizieren"],
                            "priority": "HIGH"
                        })

                return web.json_response({
                    "success": True,
                    "needs_clarification": len(questions) > 0,
                    "questions": questions,
                    "_fallback": True
                })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _handle_wizard_split(self, request: web.Request) -> web.Response:
        """
        Apply SPLIT decision to create new requirements from a complex one.
        """
        try:
            data = await request.json()
            original_req = data.get("original_requirement", {})
            split_suggestions = data.get("split_suggestions", [])

            if not split_suggestions:
                return web.json_response({
                    "success": False,
                    "error": "No split suggestions provided"
                }, status=400)

            # Generate new requirement IDs
            base_id = original_req.get("id", "REQ-000")
            new_requirements = []

            for idx, suggestion in enumerate(split_suggestions):
                new_req = {
                    "id": f"{base_id}-{chr(65 + idx)}",  # REQ-001-A, REQ-001-B, etc.
                    "title": suggestion,
                    "description": suggestion,
                    "category": original_req.get("category", "functional"),
                    "priority": original_req.get("priority", "should"),
                    "_split_from": base_id,
                    "_validated": False
                }
                new_requirements.append(new_req)

            # Emit event
            await self.emitter.requirement_split(base_id, new_requirements)

            return web.json_response({
                "success": True,
                "original_id": base_id,
                "new_requirements": new_requirements
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    async def _handle_wizard_answer_clarification(self, request: web.Request) -> web.Response:
        """
        Process user answers to clarification questions.
        """
        try:
            data = await request.json()
            req_id = data.get("req_id")
            criterion = data.get("criterion")
            answer = data.get("answer")
            original_text = data.get("requirement_text", "")

            if not answer:
                return web.json_response({
                    "success": False,
                    "error": "No answer provided"
                }, status=400)

            # Simple improvement: append the answer to the requirement
            improved_text = original_text

            if criterion == "measurability":
                improved_text = f"{original_text} ({answer})"
            elif criterion == "testability":
                improved_text = f"{original_text}. Akzeptanzkriterium: {answer}"
            elif criterion in ["clarity", "unambiguous"]:
                improved_text = f"{original_text}. Hinweis: {answer}"
            else:
                improved_text = f"{original_text}. {answer}"

            # Emit event
            await self.emitter.clarification_answered(req_id, criterion, answer)

            return web.json_response({
                "success": True,
                "improved_requirement": {
                    "id": req_id,
                    "title": improved_text,
                    "description": improved_text,
                    "_clarified": True,
                    "_clarification_criterion": criterion
                }
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response({
                "success": False,
                "error": str(e)
            }, status=500)

    # ============ Wizard Auto-Enrich (AutoGen Agent Teams) ============

    def _get_suggestion_queue(self):
        """Lazy-init and return the WizardSuggestionQueue."""
        if self._wizard_suggestion_queue is None:
            from ..wizard.suggestion_queue import WizardSuggestionQueue
            self._wizard_suggestion_queue = WizardSuggestionQueue(
                emitter=self.emitter,
                config=self._get_wizard_config(),
            )
        return self._wizard_suggestion_queue

    def _get_wizard_config(self) -> Dict[str, Any]:
        """Load wizard config from re_config.yaml."""
        try:
            from omegaconf import OmegaConf
            config_path = Path(__file__).parent.parent / "re_config.yaml"
            if config_path.exists():
                cfg = OmegaConf.load(str(config_path))
                wizard_cfg = OmegaConf.to_container(cfg.get("wizard", {}), resolve=True)
                return wizard_cfg if isinstance(wizard_cfg, dict) else {}
        except Exception as e:
            print(f"[SERVER] Could not load wizard config: {e}")
        return {}

    async def _handle_wizard_auto_enrich(self, request: web.Request) -> web.Response:
        """
        Trigger AutoGen agent teams for a wizard step.

        POST /api/wizard/auto-enrich
        Body: { step: 1|3|5, project_name, description, domain, ... }
        Returns: { auto_applied: [...], pending: [...], errors: [...] }
        """
        try:
            data = await request.json()
            step = data.get("step")

            if step not in (1, 3, 5):
                return web.json_response(
                    {"success": False, "error": f"Step {step} does not support auto-enrichment"},
                    status=400,
                )

            queue = self._get_suggestion_queue()
            wizard_config = self._get_wizard_config()
            agent_config = wizard_config.get("agents", {})

            # Emit start event
            await self.emitter.wizard_enrichment_started(step, f"step_{step}_agents")

            auto_applied = []
            pending = []
            errors = []

            from ..wizard.suggestion_queue import WizardSuggestion, SuggestionType

            def _make_suggestion(raw: Dict[str, Any], wizard_step: int, team_name: str) -> WizardSuggestion:
                """Convert raw agent dict to WizardSuggestion."""
                type_map = {
                    "stakeholder": SuggestionType.STAKEHOLDER,
                    "requirement": SuggestionType.REQUIREMENT,
                    "constraint": SuggestionType.CONSTRAINT,
                    "context": SuggestionType.CONTEXT,
                }
                return WizardSuggestion.create(
                    suggestion_type=type_map.get(raw.get("type", ""), SuggestionType.CONTEXT),
                    content=raw.get("content", {}),
                    confidence=float(raw.get("confidence", 0.5)),
                    reasoning=raw.get("reasoning", ""),
                    source_team=team_name,
                    wizard_step=wizard_step,
                )

            if step == 1:
                # Run StakeholderTeam + ContextEnricher in parallel
                from ..wizard.wizard_agents import StakeholderTeam, ContextEnricher

                stakeholder_team = StakeholderTeam(agent_config.get("stakeholder_team", {}))
                context_enricher = ContextEnricher(agent_config.get("context_enricher", {}))

                project_name = data.get("project_name", "")
                description = data.get("description", "")
                domain = data.get("domain", "")
                target_users = data.get("target_users", [])

                # Run both teams concurrently
                stakeholder_coro = stakeholder_team.run(
                    project_name=project_name,
                    description=description,
                    domain=domain,
                    target_users=target_users,
                )
                context_coro = context_enricher.run(
                    project_name=project_name,
                    description=description,
                    domain=domain,
                )

                results = await asyncio.gather(
                    stakeholder_coro, context_coro, return_exceptions=True
                )

                for result in results:
                    if isinstance(result, Exception):
                        errors.append(str(result))
                        continue
                    for raw in result.suggestions:
                        ws = _make_suggestion(raw, step, result.team_name)
                        outcome = await queue.submit(ws)
                        if outcome["action"] == "auto_applied":
                            auto_applied.append(outcome["suggestion"])
                        elif outcome["action"] == "pending":
                            pending.append(outcome["suggestion"])

            elif step == 3:
                # Run RequirementGapTeam
                from ..wizard.wizard_agents import RequirementGapTeam

                gap_team = RequirementGapTeam(agent_config.get("requirement_gap_team", {}))
                requirements = data.get("requirements", [])
                # Convert string requirements to dicts if needed
                req_dicts = [
                    r if isinstance(r, dict) else {"title": r, "description": r}
                    for r in requirements
                ]
                description = data.get("description", "")
                domain = data.get("domain", "")
                stakeholders = data.get("stakeholders", [])

                try:
                    result = await gap_team.run(
                        requirements=req_dicts,
                        stakeholders=stakeholders,
                        domain=domain,
                        description=description,
                    )
                    for raw in result.suggestions:
                        ws = _make_suggestion(raw, step, result.team_name)
                        outcome = await queue.submit(ws)
                        if outcome["action"] == "auto_applied":
                            auto_applied.append(outcome["suggestion"])
                        elif outcome["action"] == "pending":
                            pending.append(outcome["suggestion"])
                except Exception as e:
                    errors.append(str(e))

            elif step == 5:
                # Run ConstraintTeam
                from ..wizard.wizard_agents import ConstraintTeam

                constraint_team = ConstraintTeam(agent_config.get("constraint_team", {}))
                requirements = data.get("requirements", [])
                req_dicts = [
                    r if isinstance(r, dict) else {"title": r, "description": r}
                    for r in requirements
                ]
                existing_constraints = data.get("constraints", {})
                domain = data.get("domain", "")

                try:
                    result = await constraint_team.run(
                        requirements=req_dicts,
                        existing_constraints=existing_constraints,
                        domain=domain,
                    )
                    for raw in result.suggestions:
                        ws = _make_suggestion(raw, step, result.team_name)
                        outcome = await queue.submit(ws)
                        if outcome["action"] == "auto_applied":
                            auto_applied.append(outcome["suggestion"])
                        elif outcome["action"] == "pending":
                            pending.append(outcome["suggestion"])
                except Exception as e:
                    errors.append(str(e))

            # Emit complete event
            await self.emitter.wizard_enrichment_complete(
                step, len(auto_applied), len(pending)
            )

            return web.json_response({
                "success": True,
                "auto_applied": auto_applied,
                "pending": pending,
                "errors": errors,
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return web.json_response(
                {"success": False, "error": str(e)}, status=500
            )

    async def _handle_wizard_get_suggestions(self, request: web.Request) -> web.Response:
        """GET /api/wizard/suggestions - return all pending suggestions."""
        queue = self._get_suggestion_queue()
        step = request.query.get("step")
        wizard_step = int(step) if step and step.isdigit() else None
        return web.json_response({
            "success": True,
            "pending": queue.get_pending(wizard_step),
            "history": queue.get_history(limit=20),
        })

    async def _handle_wizard_approve_suggestion(self, request: web.Request) -> web.Response:
        """POST /api/wizard/suggestions/{id}/approve"""
        suggestion_id = request.match_info["suggestion_id"]
        queue = self._get_suggestion_queue()
        suggestion = await queue.approve(suggestion_id)
        if suggestion:
            return web.json_response({
                "success": True,
                "suggestion": suggestion.to_dict(),
            })
        return web.json_response(
            {"success": False, "error": "Suggestion not found"}, status=404
        )

    async def _handle_wizard_reject_suggestion(self, request: web.Request) -> web.Response:
        """POST /api/wizard/suggestions/{id}/reject"""
        suggestion_id = request.match_info["suggestion_id"]
        data = await request.json() if request.can_read_body else {}
        reason = data.get("reason", "") if isinstance(data, dict) else ""
        queue = self._get_suggestion_queue()
        suggestion = await queue.reject(suggestion_id, reason)
        if suggestion:
            return web.json_response({
                "success": True,
                "suggestion": suggestion.to_dict(),
            })
        return web.json_response(
            {"success": False, "error": "Suggestion not found"}, status=404
        )

    # ============ Change Propagation & Auto-Link Methods ============

    async def _init_propagation_for_project(self, project_id: str):
        """Initialize propagation engine for a project."""
        if not HAS_PROPAGATION:
            print("[SERVER] Propagation module not available")
            return

        # Get project path from enterprise_output
        enterprise_output = Path(__file__).parent.parent.parent / "enterprise_output"
        project_dirs = list(enterprise_output.glob(f"*{project_id}*"))

        if not project_dirs:
            print(f"[SERVER] Project not found: {project_id}")
            return

        project_path = project_dirs[0]
        self._current_project_path = project_path

        # Create event callback
        async def emit_event(event_type: str, data: dict):
            # Map internal event types to EventType enum
            event_map = {
                "propagation_initialized": EventType.PROPAGATION_INITIALIZED,
                "file_changed": EventType.FILE_CHANGED,
                "propagation_suggestion": EventType.PROPAGATION_SUGGESTION,
                "propagation_applied": EventType.PROPAGATION_APPLIED,
                "propagation_rejected": EventType.PROPAGATION_REJECTED,
                "propagation_error": EventType.PROPAGATION_ERROR,
                "file_watching_started": EventType.FILE_WATCHING_STARTED,
                "file_watching_stopped": EventType.FILE_WATCHING_STOPPED,
                "orphans_detected": EventType.ORPHANS_DETECTED,
                "link_suggestion": EventType.LINK_SUGGESTION,
                "link_created": EventType.LINK_CREATED,
                "link_rejected": EventType.LINK_REJECTED,
            }
            if event_type in event_map:
                await self.emitter.emit(event_map[event_type], data)

        # Initialize propagation engine
        self.propagation_engine = PropagationEngine(
            project_path=project_path,
            event_callback=emit_event
        )
        await self.propagation_engine.initialize()

        # Initialize auto linker
        self.auto_linker = AutoLinker(
            link_graph=self.propagation_engine.link_graph,
            llm_analyzer=self.propagation_engine.llm_analyzer,
            project_path=project_path,
            event_callback=emit_event
        )

        print(f"[SERVER] Propagation initialized for: {project_path}")

    async def _start_file_watching(self):
        """Start file watching for the current project."""
        if self.propagation_engine:
            await self.propagation_engine.start_watching()

    async def _stop_file_watching(self):
        """Stop file watching."""
        if self.propagation_engine:
            await self.propagation_engine.stop_watching()

    async def _handle_get_pending_propagations(self, request: web.Request) -> web.Response:
        """Get all pending propagation suggestions."""
        if not self.propagation_engine:
            return web.json_response({"suggestions": []})

        suggestions = self.propagation_engine.get_pending_suggestions()
        return web.json_response({
            "suggestions": [s.to_event_dict() for s in suggestions]
        })

    async def _handle_approve_propagation(self, request: web.Request) -> web.Response:
        """Approve a propagation suggestion."""
        suggestion_id = request.match_info.get("suggestion_id")

        if not self.propagation_engine:
            return web.json_response({"success": False, "error": "Propagation not initialized"}, status=400)

        success = await self.propagation_engine.apply_suggestion(suggestion_id)
        return web.json_response({"success": success})

    async def _handle_reject_propagation(self, request: web.Request) -> web.Response:
        """Reject a propagation suggestion."""
        suggestion_id = request.match_info.get("suggestion_id")

        if not self.propagation_engine:
            return web.json_response({"success": False, "error": "Propagation not initialized"}, status=400)

        success = await self.propagation_engine.reject_suggestion(suggestion_id)
        return web.json_response({"success": success})

    async def _handle_start_watching(self, request: web.Request) -> web.Response:
        """Start file watching via REST API."""
        try:
            data = await request.json()
            project_id = data.get("project_id")

            if project_id:
                await self._init_propagation_for_project(project_id)

            await self._start_file_watching()
            return web.json_response({"success": True})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def _handle_stop_watching(self, request: web.Request) -> web.Response:
        """Stop file watching via REST API."""
        await self._stop_file_watching()
        return web.json_response({"success": True})

    async def _handle_get_orphans(self, request: web.Request) -> web.Response:
        """Get all orphan nodes."""
        if not self.auto_linker:
            return web.json_response({"orphans": [], "statistics": {}})

        orphans = await self.auto_linker.find_orphans()
        statistics = self.auto_linker.get_orphan_statistics()

        return web.json_response({
            "orphans": orphans,
            "statistics": statistics
        })

    async def _handle_discover_links(self, request: web.Request) -> web.Response:
        """Discover links for orphan nodes."""
        # Auto-initialize if not already done
        if not self.auto_linker:
            try:
                # Use the currently loaded project
                project_id = self._current_project_id

                # Fallback: try to parse request body
                if not project_id:
                    try:
                        data = await request.json()
                        project_id = data.get("project_id")
                    except:
                        pass

                # Fallback: use first project in enterprise_output
                if not project_id:
                    enterprise_output = Path(__file__).parent.parent.parent / "enterprise_output"
                    projects = [p for p in enterprise_output.iterdir() if p.is_dir()]
                    if projects:
                        project_id = projects[0].name

                if project_id:
                    print(f"[SERVER] Auto-initializing propagation for: {project_id}")
                    await self._init_propagation_for_project(project_id)
            except Exception as e:
                import traceback
                print(f"[SERVER] Auto-init failed: {e}")
                traceback.print_exc()

        if not self.auto_linker:
            return web.json_response({"success": False, "error": "Auto-linker not initialized. Please load a project first."}, status=400)

        try:
            results = await self.auto_linker.discover_all()

            # Flatten suggestions
            all_suggestions = []
            for orphan_id, suggestions in results.items():
                for s in suggestions:
                    all_suggestions.append(s.to_event_dict())

            return web.json_response({
                "success": True,
                "suggestions": all_suggestions,
                "orphan_count": len(results)
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def _handle_get_pending_links(self, request: web.Request) -> web.Response:
        """Get all pending link suggestions."""
        if not self.auto_linker:
            return web.json_response({"suggestions": []})

        suggestions = self.auto_linker.get_pending_suggestions()
        return web.json_response({
            "suggestions": [s.to_event_dict() for s in suggestions]
        })

    async def _handle_approve_link(self, request: web.Request) -> web.Response:
        """Approve a link suggestion."""
        suggestion_id = request.match_info.get("suggestion_id")

        if not self.auto_linker:
            return web.json_response({"success": False, "error": "Auto-linker not initialized"}, status=400)

        success = await self.auto_linker.approve_link(suggestion_id)
        return web.json_response({"success": success})

    async def _handle_reject_link(self, request: web.Request) -> web.Response:
        """Reject a link suggestion."""
        suggestion_id = request.match_info.get("suggestion_id")

        if not self.auto_linker:
            return web.json_response({"success": False, "error": "Auto-linker not initialized"}, status=400)

        success = await self.auto_linker.reject_link(suggestion_id)
        return web.json_response({"success": success})


# Simple HTTP server fallback if aiohttp is not available
class SimpleDashboardServer:
    """
    Fallback simple HTTP server using Python's built-in http.server.

    This is used when aiohttp is not installed. It provides basic
    static file serving but no WebSocket support.
    """

    def __init__(self, port: int = 8080, open_browser: bool = True):
        self.port = port
        self.open_browser = open_browser
        self.emitter = DashboardEventEmitter()
        self._static_path = Path(__file__).parent / "static"

    async def start(self):
        """Start the simple server."""
        import http.server
        import threading

        os.chdir(self._static_path)

        handler = http.server.SimpleHTTPRequestHandler
        server = http.server.HTTPServer(("localhost", self.port), handler)

        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        print(f"\n  [DASHBOARD] Running at: http://localhost:{self.port}")
        print(f"  [WARN] Note: Using fallback server (no live updates). Install aiohttp for full features.")

        if self.open_browser:
            webbrowser.open(f"http://localhost:{self.port}")

    async def stop(self):
        """Stop the server (not implemented for simple server)."""
        pass


def create_dashboard_server(port: int = 8080, open_browser: bool = True):
    """
    Factory function to create the appropriate dashboard server.

    Returns DashboardServer if aiohttp is available, otherwise SimpleDashboardServer.
    """
    if HAS_AIOHTTP:
        return DashboardServer(port=port, open_browser=open_browser)
    else:
        return SimpleDashboardServer(port=port, open_browser=open_browser)
