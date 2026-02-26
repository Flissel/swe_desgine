"""
Billing Spec Importer - Imports autonomous_billing_spec.json format.

This importer handles the complex billing service specification format
with agents, n8n workflows, autogen integration, and LLM configs.
"""

import json
import os
from typing import Dict, Any, List

from .base_importer import BaseImporter, ImportResult
from requirements_engineer.core.re_journal import RequirementNode


class BillingSpecImporter(BaseImporter):
    """
    Importer for autonomous billing service specification format.

    This format includes:
    - project: Project metadata with autonomy_level
    - frontend_requirements: UI component requirements
    - requirements: Main requirements list
    - agents: AI agent definitions
    - n8n_workflows: Workflow automation specs
    - autogen_integration: Multi-agent collaboration specs
    - llm_configs: LLM model configurations
    """

    name = "Billing Spec"
    supported_extensions = [".json"]

    # Priority mapping
    PRIORITY_MAP = {
        "critical": "must",
        "high": "must",
        "medium": "should",
        "low": "could",
        "nice-to-have": "could"
    }

    # Type mapping
    TYPE_MAP = {
        "imported": "functional",
        "autonomy": "non_functional",
        "strategic": "non_functional",
        "functional": "functional",
        "non-functional": "non_functional",
        "integration": "functional"
    }

    @classmethod
    def can_import(cls, file_path: str) -> bool:
        """Check if file is billing spec format."""
        if not file_path.endswith('.json'):
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Billing spec format has "project" with "autonomy_level"
            return "project" in data and "autonomy_level" in data.get("project", {})
        except Exception:
            return False

    async def import_requirements(self, file_path: str) -> ImportResult:
        """Import requirements from billing spec format."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        requirements = []
        req_counter = 1

        # Get the project section
        project = data.get("project", {})

        # 1. Import main requirements from the nested structure
        # The requirements can be in data["requirements"] with sub-keys like:
        # - imported_requirements
        # - autonomy_requirements
        # etc.
        requirements_section = data.get("requirements", {})

        # Handle both dict and list formats
        if isinstance(requirements_section, dict):
            # Nested format with sub-categories
            for category_key, req_list in requirements_section.items():
                if isinstance(req_list, list):
                    for req in req_list:
                        if isinstance(req, dict):
                            # Map category to type
                            category = req.get("category", category_key.replace("_requirements", ""))
                            req_type = self.TYPE_MAP.get(category, "functional")

                            node = self._create_requirement_node(
                                req_id=req.get("id", f"REQ-{req_counter:03d}"),
                                title=req.get("title", "Untitled Requirement"),
                                description=req.get("text", req.get("description", "")),
                                req_type=req_type,
                                priority=self.PRIORITY_MAP.get(req.get("priority", "medium"), "should"),
                                source=f"billing_spec_{category_key}"
                            )
                            node.metadata = {
                                "category": category,
                                "source_section": req.get("source_section", ""),
                                "source_file": req.get("source_file", "")
                            }
                            requirements.append(node)
                            req_counter += 1
        elif isinstance(requirements_section, list):
            # Flat list format
            for req in requirements_section:
                if isinstance(req, dict):
                    node = self._create_requirement_node(
                        req_id=req.get("id", f"REQ-{req_counter:03d}"),
                        title=req.get("title", "Untitled Requirement"),
                        description=req.get("text", req.get("description", "")),
                        req_type=self.TYPE_MAP.get(req.get("type", "functional"), "functional"),
                        priority=self.PRIORITY_MAP.get(req.get("priority", "medium"), "should"),
                        source="billing_spec_main"
                    )
                    node.metadata = {
                        "category": req.get("category", ""),
                        "original_type": req.get("type", ""),
                        "original_priority": req.get("priority", "")
                    }
                    requirements.append(node)
                    req_counter += 1

        # 2. Import frontend requirements (can be at root or inside project)
        frontend_reqs = data.get("frontend_requirements", {})
        if not frontend_reqs:
            # Try nested inside project
            frontend_reqs = project.get("frontend_requirements", {})

        # Track processed frontend requirements to avoid duplicates
        processed_frontend = set()

        # Frontend requirements might have nested structure
        if frontend_reqs:
            for section_name, section_content in frontend_reqs.items():
                if isinstance(section_content, dict):
                    # Check if it's a direct requirement or a container
                    if "description" in section_content:
                        # Direct requirement
                        if section_name not in processed_frontend:
                            req_id = f"FR-FE-{section_name.upper().replace('_', '-')}"
                            description = self._build_frontend_description(section_name, section_content)
                            node = self._create_requirement_node(
                                req_id=req_id,
                                title=f"Frontend: {section_name.replace('_', ' ').title()}",
                                description=description,
                                req_type="functional",
                                priority="must",
                                source="billing_spec_frontend"
                            )
                            node.metadata = {
                                "component": section_name,
                                "fields": section_content.get("fields", []),
                                "features": section_content.get("features", [])
                            }
                            requirements.append(node)
                            processed_frontend.add(section_name)
                    else:
                        # Container with nested requirements
                        for name, spec in section_content.items():
                            if isinstance(spec, dict) and name not in processed_frontend:
                                req_id = f"FR-FE-{name.upper().replace('_', '-')}"
                                description = self._build_frontend_description(name, spec)
                                node = self._create_requirement_node(
                                    req_id=req_id,
                                    title=f"Frontend: {name.replace('_', ' ').title()}",
                                    description=description,
                                    req_type="functional",
                                    priority="must",
                                    source="billing_spec_frontend"
                                )
                                node.metadata = {
                                    "component": name,
                                    "fields": spec.get("fields", []),
                                    "features": spec.get("features", [])
                                }
                                requirements.append(node)
                                processed_frontend.add(name)

        # 3. Import agent definitions as non-functional requirements
        agents = data.get("agents", {})

        # Handle different agent structures
        agent_list = []
        if isinstance(agents, dict):
            # Check for "types" key (list of agent definitions)
            if "types" in agents and isinstance(agents["types"], list):
                agent_list = agents["types"]
            else:
                # Dict of agent_name -> agent_spec
                agent_list = [{"name": k, **v} if isinstance(v, dict) else {"name": k}
                              for k, v in agents.items()]
        elif isinstance(agents, list):
            agent_list = agents

        for agent_spec in agent_list:
            if isinstance(agent_spec, dict):
                agent_name = agent_spec.get("name", f"Agent-{len(requirements)+1}")
                req_id = f"NFR-AGENT-{agent_name.upper().replace(' ', '-').replace('_', '-')}"

                description = self._build_agent_description(agent_name, agent_spec)

                node = self._create_requirement_node(
                    req_id=req_id,
                    title=f"Agent: {agent_name}",
                    description=description,
                    req_type="non_functional",
                    priority="should",
                    source="billing_spec_agent"
                )
                node.metadata = {
                    "agent_name": agent_name,
                    "trigger": agent_spec.get("trigger", ""),
                    "capabilities": agent_spec.get("capabilities", []),
                    "tools": agent_spec.get("tools", [])
                }
                requirements.append(node)

        # 4. Import n8n workflows as integration requirements
        n8n_workflows = data.get("n8n_workflows", {})
        for wf_name, wf_spec in n8n_workflows.items():
            req_id = f"INT-WF-{wf_name.upper().replace('_', '-')}"

            description = self._build_workflow_description(wf_name, wf_spec)

            node = self._create_requirement_node(
                req_id=req_id,
                title=f"Workflow: {wf_spec.get('name', wf_name)}",
                description=description,
                req_type="functional",
                priority="should",
                source="billing_spec_workflow"
            )
            node.metadata = {
                "workflow_name": wf_name,
                "trigger": wf_spec.get("trigger", {}),
                "nodes": wf_spec.get("nodes", [])
            }
            requirements.append(node)

        # 5. Import autogen teams as collaboration requirements
        autogen = data.get("autogen_integration", {})
        for team_name, team_spec in autogen.get("teams", {}).items():
            req_id = f"NFR-TEAM-{team_name.upper().replace('_', '-')}"

            description = self._build_team_description(team_name, team_spec)

            node = self._create_requirement_node(
                req_id=req_id,
                title=f"Autogen Team: {team_spec.get('name', team_name)}",
                description=description,
                req_type="non_functional",
                priority="could",
                source="billing_spec_autogen"
            )
            node.metadata = {
                "team_name": team_name,
                "agents": team_spec.get("agents", []),
                "workflow_type": team_spec.get("workflow_type", "")
            }
            requirements.append(node)

        # Extract stakeholders from the data structure
        stakeholders = self._extract_stakeholders(data)

        # Build context
        project = data.get("project", {})
        context = {
            "business": "Automated invoicing and payment processing service",
            "technical": f"Autonomy Level: {project.get('autonomy_level', 'unknown')}",
            "domain": "Billing, Invoicing, Payment Processing, Financial Automation",
            "version": project.get("version", "1.0.0")
        }

        return ImportResult(
            project_name=project.get("name", "billing_service"),
            project_title=project.get("description", project.get("name", "Billing Service")),
            domain="billing",
            context=context,
            stakeholders=stakeholders,
            requirements=requirements,
            constraints=data.get("integration", {}),
            metadata={
                "n8n_workflows": n8n_workflows,
                "autogen_integration": autogen,
                "llm_configs": data.get("llm_configs", {}),
                "monitoring": data.get("monitoring", {}),
                "observability": data.get("observability", {})
            },
            source_format="billing_spec"
        )

    def _build_frontend_description(self, name: str, spec: Dict[str, Any]) -> str:
        """Build description for frontend requirement."""
        parts = [spec.get("description", f"Frontend component for {name.replace('_', ' ')}.")]

        if spec.get("api_endpoint"):
            parts.append(f"API Endpoint: {spec['api_endpoint']}")

        if spec.get("ui_elements"):
            ui_elements = spec["ui_elements"]
            if isinstance(ui_elements, list):
                parts.append(f"UI Elements: {', '.join(str(e) for e in ui_elements)}")

        if spec.get("fields"):
            fields = spec["fields"]
            if isinstance(fields, dict):
                field_names = list(fields.keys())
            elif isinstance(fields, list):
                field_names = [str(f) for f in fields]
            else:
                field_names = [str(fields)]
            parts.append(f"Fields: {', '.join(field_names)}")

        if spec.get("features"):
            features = spec["features"]
            if isinstance(features, list):
                parts.append(f"Features: {', '.join(str(f) for f in features)}")

        if spec.get("validation_rules"):
            rules = spec["validation_rules"]
            if isinstance(rules, list):
                parts.append(f"Validation: {', '.join(str(r) for r in rules)}")

        if spec.get("security_measures"):
            security = spec["security_measures"]
            if isinstance(security, list):
                parts.append(f"Security: {', '.join(str(s) for s in security)}")

        return " ".join(parts)

    def _build_agent_description(self, name: str, spec: Dict[str, Any]) -> str:
        """Build description for agent requirement."""
        parts = [spec.get("description", f"AI agent for {name.replace('_', ' ')}.")]

        if spec.get("trigger"):
            parts.append(f"Trigger: {spec['trigger']}")

        if spec.get("capabilities"):
            parts.append(f"Capabilities: {', '.join(spec['capabilities'])}")

        if spec.get("tools"):
            tool_names = [t.get("name", str(t)) if isinstance(t, dict) else str(t) for t in spec["tools"]]
            parts.append(f"Tools: {', '.join(tool_names)}")

        return " ".join(parts)

    def _build_workflow_description(self, name: str, spec: Dict[str, Any]) -> str:
        """Build description for workflow requirement."""
        parts = [spec.get("description", f"Workflow for {name.replace('_', ' ')}.")]

        trigger = spec.get("trigger", {})
        if trigger:
            trigger_type = trigger.get("type", "unknown")
            parts.append(f"Trigger Type: {trigger_type}")

        nodes = spec.get("nodes", [])
        if nodes:
            node_names = [n.get("name", str(n)) if isinstance(n, dict) else str(n) for n in nodes]
            parts.append(f"Nodes: {', '.join(node_names[:5])}")
            if len(nodes) > 5:
                parts.append(f"(+{len(nodes)-5} more)")

        return " ".join(parts)

    def _build_team_description(self, name: str, spec: Dict[str, Any]) -> str:
        """Build description for autogen team requirement."""
        parts = [spec.get("description", f"Autogen team for {name.replace('_', ' ')}.")]

        if spec.get("workflow_type"):
            parts.append(f"Workflow Type: {spec['workflow_type']}")

        agents = spec.get("agents", [])
        if agents:
            agent_names = [a.get("name", str(a)) if isinstance(a, dict) else str(a) for a in agents]
            parts.append(f"Agents: {', '.join(agent_names)}")

        return " ".join(parts)

    def _extract_stakeholders(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract stakeholders from billing spec data."""
        stakeholders = []

        # Default stakeholders for billing service
        stakeholders.append({
            "role": "Finance Team",
            "persona": "Accountant",
            "concerns": ["accurate invoicing", "timely payments", "audit trail"],
            "goals": ["automate invoice generation", "reduce manual errors"]
        })

        stakeholders.append({
            "role": "Operations",
            "persona": "Operations Manager",
            "concerns": ["process efficiency", "exception handling", "reporting"],
            "goals": ["streamline billing workflow", "reduce processing time"]
        })

        stakeholders.append({
            "role": "IT/DevOps",
            "persona": "System Administrator",
            "concerns": ["system reliability", "integration stability", "monitoring"],
            "goals": ["maintain high availability", "easy troubleshooting"]
        })

        # Add stakeholders from LLM configs (models represent different processing needs)
        llm_configs = data.get("llm_configs", {})
        if llm_configs:
            stakeholders.append({
                "role": "AI/ML Team",
                "persona": "ML Engineer",
                "concerns": ["model accuracy", "cost optimization", "latency"],
                "goals": ["optimal model selection", "reliable AI responses"]
            })

        return stakeholders
