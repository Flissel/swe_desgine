"""
Architecture Generator - Produces C4 diagrams and deployment architecture.

This module analyzes requirements, tech stack, and API/entity counts to generate
a comprehensive architecture specification including:
- Service decomposition (microservices/modules)
- C4 Context and Container diagrams in Mermaid format
- Deployment diagrams in Mermaid format
- Data flow diagrams in Mermaid format
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from openai import AsyncOpenAI

# Import LLM logger
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


@dataclass_json
@dataclass
class ServiceDefinition:
    """A single service/module in the architecture."""
    name: str
    type: str = ""  # api, worker, gateway, database, cache, queue
    technology: str = ""
    responsibilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    ports: List[int] = field(default_factory=list)


@dataclass_json
@dataclass
class ArchitectureSpec:
    """Complete architecture specification."""
    project_name: str
    services: List[ServiceDefinition] = field(default_factory=list)
    c4_context_diagram: str = ""      # Mermaid
    c4_container_diagram: str = ""    # Mermaid
    deployment_diagram: str = ""      # Mermaid
    data_flow_diagram: str = ""       # Mermaid
    architecture_pattern: str = ""    # microservices, monolith, etc.
    communication_patterns: List[str] = field(default_factory=list)  # REST, gRPC, events


class ArchitectureGenerator:
    """Generates architecture specifications from requirements and tech stack."""

    ARCHITECTURE_PROMPT = """Du bist ein Senior Software Architect. Analysiere die folgenden Informationen und generiere eine detaillierte Architekturspezifikation.

## Projekt: {project_name}
## Domain: {domain}

## Requirements:
{requirements_text}

## Tech-Stack:
{tech_stack_text}

## Statistiken:
- API Endpoints: {api_endpoint_count}
- Data Entities: {entity_count}

Generiere eine Architekturspezifikation im folgenden JSON-Format:

{{
    "services": [
        {{
            "name": "ServiceName",
            "type": "api|worker|gateway|database|cache|queue",
            "technology": "FastAPI/Express/PostgreSQL/etc.",
            "responsibilities": ["Verantwortung 1", "Verantwortung 2"],
            "dependencies": ["OtherService"],
            "ports": [8080]
        }}
    ],
    "c4_context": "C4Context\\n    title System Context - ProjectName\\n    ...",
    "c4_container": "graph TB\\n    subgraph System\\n    ...",
    "deployment": "graph TB\\n    subgraph Cloud\\n    ...",
    "data_flow": "flowchart LR\\n    A[Client] --> B[API Gateway]\\n    ...",
    "architecture_pattern": "Microservices|Monolith|Modular Monolith|Serverless",
    "communication_patterns": ["REST", "gRPC", "Event-Driven", "WebSocket"]
}}

Beachte:
- Identifiziere alle notwendigen Services/Module basierend auf den Requirements
- Erstelle valide Mermaid-Diagramme fuer jeden Diagrammtyp
- Das C4 Context Diagramm soll Benutzer, externes System und die Systemgrenzen zeigen
- Das C4 Container Diagramm soll die internen Container (Frontend, Backend, DB, Cache, etc.) zeigen
- Das Deployment Diagramm soll die Cloud/Server-Infrastruktur darstellen
- Das Data Flow Diagramm soll den Datenfluss zwischen Komponenten zeigen
- Verwende Mermaid-Syntax (graph TB, flowchart LR, etc.) fuer alle Diagramme
- Beruecksichtige die Anzahl der API Endpoints und Entities fuer die Granularitaet
- Jeder Service muss mindestens eine Verantwortung und einen Port haben
- Zeilenumbrueche in Mermaid-Diagrammen mit \\n kodieren

Antworte NUR mit dem JSON-Objekt, keine zusaetzlichen Erklaerungen."""

    def __init__(
        self,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Architecture Generator.

        Args:
            model: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.architecture section
        """
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("architecture", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 6000)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY")
        )

        # Store last generated spec for to_markdown()
        self._last_spec: Optional[ArchitectureSpec] = None

    async def initialize(self):
        """Initialize the generator (client is already created in __init__)."""
        pass

    async def generate_architecture(
        self,
        requirements: List[Any],
        tech_stack_dict: Dict[str, Any],
        api_endpoint_count: int,
        entity_count: int,
        project_name: str,
        domain: str
    ) -> ArchitectureSpec:
        """
        Generate architecture specification based on requirements and tech stack.

        Args:
            requirements: List of RequirementNode instances or dicts
            tech_stack_dict: Tech stack as a dict (from TechStack.to_dict())
            api_endpoint_count: Number of API endpoints in the project
            entity_count: Number of data entities in the project
            project_name: Name of the project
            domain: Project domain (e.g., "E-Commerce", "Healthcare")

        Returns:
            ArchitectureSpec with service definitions and Mermaid diagrams
        """
        # Build requirements text
        req_lines = []
        for req in requirements[:20]:  # Limit to avoid token overflow
            if hasattr(req, 'title'):
                req_lines.append(f"- {req.requirement_id}: {req.title}")
                if hasattr(req, 'description') and req.description:
                    req_lines.append(f"  {req.description[:200]}")
            elif isinstance(req, dict):
                req_lines.append(f"- {req.get('id', 'REQ')}: {req.get('title', 'Untitled')}")

        requirements_text = "\n".join(req_lines) if req_lines else "Keine Requirements angegeben"

        # Build tech stack text
        tech_lines = []
        for key, value in tech_stack_dict.items():
            if isinstance(value, str) and value:
                tech_lines.append(f"- {key}: {value}")
            elif isinstance(value, list) and value:
                tech_lines.append(f"- {key}: {', '.join(str(v) for v in value)}")
        tech_stack_text = "\n".join(tech_lines) if tech_lines else "Kein Tech-Stack angegeben"

        prompt = self.ARCHITECTURE_PROMPT.format(
            project_name=project_name,
            domain=domain,
            requirements_text=requirements_text,
            tech_stack_text=tech_stack_text,
            api_endpoint_count=api_endpoint_count,
            entity_count=entity_count
        )

        try:
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            latency_ms = int((time.time() - start_time) * 1000)

            content = response.choices[0].message.content.strip()

            # Log the LLM call
            log_llm_call(
                component="architecture_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON from response
            data = self._extract_json(content)

            # Parse services
            services = []
            for svc_data in data.get("services", []):
                services.append(ServiceDefinition(
                    name=svc_data.get("name", "Unknown"),
                    type=svc_data.get("type", ""),
                    technology=svc_data.get("technology", ""),
                    responsibilities=svc_data.get("responsibilities", []),
                    dependencies=svc_data.get("dependencies", []),
                    ports=svc_data.get("ports", []),
                ))

            # Parse Mermaid diagrams (replace literal \n with newlines)
            c4_context = data.get("c4_context", "")
            c4_container = data.get("c4_container", "")
            deployment = data.get("deployment", "")
            data_flow = data.get("data_flow", "")

            # Unescape \n in diagram strings from JSON
            for diagram_str in [c4_context, c4_container, deployment, data_flow]:
                if isinstance(diagram_str, str):
                    diagram_str = diagram_str.replace("\\n", "\n")

            c4_context = c4_context.replace("\\n", "\n") if isinstance(c4_context, str) else ""
            c4_container = c4_container.replace("\\n", "\n") if isinstance(c4_container, str) else ""
            deployment = deployment.replace("\\n", "\n") if isinstance(deployment, str) else ""
            data_flow = data_flow.replace("\\n", "\n") if isinstance(data_flow, str) else ""

            spec = ArchitectureSpec(
                project_name=project_name,
                services=services,
                c4_context_diagram=c4_context,
                c4_container_diagram=c4_container,
                deployment_diagram=deployment,
                data_flow_diagram=data_flow,
                architecture_pattern=data.get("architecture_pattern", ""),
                communication_patterns=data.get("communication_patterns", []),
            )

            self._last_spec = spec
            return spec

        except json.JSONDecodeError as e:
            print(f"    [WARN] Could not parse architecture JSON: {e}")
            return ArchitectureSpec(project_name=project_name)
        except Exception as e:
            print(f"    [ERROR] Architecture generation failed: {e}")
            return ArchitectureSpec(project_name=project_name)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response with robust error handling."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown fence extraction
        if "```json" in text:
            try:
                extracted = text.split("```json")[1].split("```")[0].strip()
                return json.loads(extracted)
            except (json.JSONDecodeError, IndexError):
                pass

        # Try generic fence extraction
        if "```" in text:
            try:
                extracted = text.split("```")[1].split("```")[0].strip()
                return json.loads(extracted)
            except (json.JSONDecodeError, IndexError):
                pass

        # Try regex extraction for JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return empty structure
        print(f"    [WARN] Could not extract JSON from architecture response")
        return {}

    def to_markdown(self) -> str:
        """Generate markdown documentation for the last generated architecture."""
        spec = self._last_spec
        if not spec:
            return "# Architecture\n\nNo architecture generated yet.\n"

        return generate_architecture_markdown(spec)


def generate_architecture_markdown(spec: ArchitectureSpec) -> str:
    """Generate markdown documentation for an architecture spec."""

    md = f"""# Architecture - {spec.project_name}

## Overview

| Property | Value |
|----------|-------|
| Architecture Pattern | **{spec.architecture_pattern}** |
| Communication Patterns | {', '.join(spec.communication_patterns) if spec.communication_patterns else 'N/A'} |
| Total Services | {len(spec.services)} |

---

## Services

"""

    for svc in spec.services:
        md += f"### {svc.name}\n\n"
        md += f"| Property | Value |\n"
        md += f"|----------|-------|\n"
        md += f"| Type | {svc.type} |\n"
        md += f"| Technology | {svc.technology} |\n"
        if svc.ports:
            md += f"| Ports | {', '.join(str(p) for p in svc.ports)} |\n"
        if svc.dependencies:
            md += f"| Dependencies | {', '.join(svc.dependencies)} |\n"
        md += "\n"

        if svc.responsibilities:
            md += "**Responsibilities:**\n"
            for resp in svc.responsibilities:
                md += f"- {resp}\n"
            md += "\n"

    md += "---\n\n"

    # C4 Context Diagram
    if spec.c4_context_diagram:
        md += "## C4 Context Diagram\n\n"
        md += "```mermaid\n"
        md += spec.c4_context_diagram.strip()
        md += "\n```\n\n"

    # C4 Container Diagram
    if spec.c4_container_diagram:
        md += "## C4 Container Diagram\n\n"
        md += "```mermaid\n"
        md += spec.c4_container_diagram.strip()
        md += "\n```\n\n"

    # Deployment Diagram
    if spec.deployment_diagram:
        md += "## Deployment Diagram\n\n"
        md += "```mermaid\n"
        md += spec.deployment_diagram.strip()
        md += "\n```\n\n"

    # Data Flow Diagram
    if spec.data_flow_diagram:
        md += "## Data Flow Diagram\n\n"
        md += "```mermaid\n"
        md += spec.data_flow_diagram.strip()
        md += "\n```\n\n"

    md += "---\n\n"
    md += "See `architecture/` directory for individual `.mmd` diagram files.\n"

    return md


def save_architecture(spec: ArchitectureSpec, output_dir) -> None:
    """
    Save architecture specification to files.

    Creates:
        architecture/
            architecture.json       - Full spec as JSON
            architecture.md         - Overview markdown
            c4_context.mmd          - C4 Context diagram
            c4_container.mmd        - C4 Container diagram
            deployment.mmd          - Deployment diagram
            data_flow.mmd           - Data flow diagram

    Args:
        spec: ArchitectureSpec to save
        output_dir: Base output directory
    """
    arch_dir = Path(output_dir) / "architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    with open(arch_dir / "architecture.json", "w", encoding="utf-8") as f:
        json.dump(spec.to_dict(), f, indent=2, ensure_ascii=False)

    # Save Markdown overview
    md = generate_architecture_markdown(spec)
    with open(arch_dir / "architecture.md", "w", encoding="utf-8") as f:
        f.write(md)

    # Save individual Mermaid diagrams
    diagrams = {
        "c4_context.mmd": spec.c4_context_diagram,
        "c4_container.mmd": spec.c4_container_diagram,
        "deployment.mmd": spec.deployment_diagram,
        "data_flow.mmd": spec.data_flow_diagram,
    }

    for filename, content in diagrams.items():
        if content and content.strip():
            with open(arch_dir / filename, "w", encoding="utf-8") as f:
                f.write(content.strip() + "\n")
