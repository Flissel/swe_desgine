"""
Tech Stack Generator - Generates technology recommendations based on requirements.

This module analyzes requirements and generates technology stack recommendations
including frontend, backend, database, infrastructure, and integration technologies.
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from dataclasses_json import dataclass_json
from openai import AsyncOpenAI

# Import LLM logger
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


@dataclass_json
@dataclass
class TechStack:
    """Complete technology stack recommendation."""
    project_name: str

    # Frontend
    frontend_framework: str = ""
    frontend_languages: List[str] = field(default_factory=list)
    ui_library: str = ""
    state_management: str = ""

    # Backend
    backend_language: str = ""
    backend_framework: str = ""
    api_style: str = ""  # REST, GraphQL, gRPC

    # Database
    primary_database: str = ""
    cache_layer: str = ""
    search_engine: str = ""

    # Infrastructure
    cloud_provider: str = ""
    container_runtime: str = ""
    orchestration: str = ""
    ci_cd: str = ""

    # Integration
    message_queue: str = ""
    api_gateway: str = ""

    # Justification
    rationale: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)

    # Architecture
    architecture_pattern: str = ""
    deployment_model: str = ""

    # Gap #14: Pinned versions and package names
    versions: Dict[str, str] = field(default_factory=dict)  # e.g. {"React": "19.0.0"}
    package_names: Dict[str, str] = field(default_factory=dict)  # e.g. {"React": "react"}


class TechStackGenerator:
    """Generates technology stack recommendations from requirements."""

    TECH_STACK_PROMPT = """Du bist ein Senior Software Architect. Analysiere die folgenden Requirements und generiere eine detaillierte Tech-Stack-Empfehlung.

## Projekt: {project_name}
## Domain: {domain}

## Requirements:
{requirements_text}

## Constraints:
{constraints_text}

## API Endpoints (falls vorhanden):
{api_summary}

## Data Entities (falls vorhanden):
{entities_summary}

Generiere eine Tech-Stack-Empfehlung im folgenden JSON-Format:

{{
    "frontend_framework": "React/Vue/Angular/etc.",
    "frontend_languages": ["TypeScript", "JavaScript"],
    "ui_library": "Material-UI/Tailwind/etc.",
    "state_management": "Redux/Zustand/Pinia/etc.",
    "backend_language": "Python/Node.js/Go/Java/etc.",
    "backend_framework": "FastAPI/Express/Spring/etc.",
    "api_style": "REST/GraphQL/gRPC",
    "primary_database": "PostgreSQL/MongoDB/etc.",
    "cache_layer": "Redis/Memcached/etc.",
    "search_engine": "Elasticsearch/Algolia/none",
    "cloud_provider": "AWS/Azure/GCP/On-Premise",
    "container_runtime": "Docker/Podman",
    "orchestration": "Kubernetes/ECS/Docker Compose",
    "ci_cd": "GitHub Actions/GitLab CI/Jenkins",
    "message_queue": "RabbitMQ/Kafka/SQS/none",
    "api_gateway": "Kong/AWS API Gateway/none",
    "architecture_pattern": "Microservices/Monolith/Modular Monolith",
    "deployment_model": "Cloud-native/Hybrid/On-premise",
    "rationale": {{
        "frontend_framework": "Warum diese Wahl...",
        "backend_framework": "Warum diese Wahl...",
        "primary_database": "Warum diese Wahl..."
    }},
    "alternatives": {{
        "frontend_framework": ["Alternative1", "Alternative2"],
        "backend_framework": ["Alternative1", "Alternative2"]
    }}
}}

Beachte:
- Wähle Technologien die zu den Requirements passen
- Berücksichtige Skalierbarkeit, Team-Skills, Budget
- Gib Begründungen für jede wichtige Entscheidung
- Nenne Alternativen für Flexibilität
- WICHTIG: Für jede Technologie MUSS eine spezifische Version angegeben werden (z.B. "19.0.0", nicht "latest")
- Füge ein "versions" Objekt hinzu: {{"React": "19.0.0", "TypeScript": "5.7.2", ...}}
- Füge ein "package_names" Objekt hinzu: {{"React": "react", "FastAPI": "fastapi", ...}}

Antworte NUR mit dem JSON-Objekt, keine zusätzlichen Erklärungen."""

    def __init__(
        self,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Tech Stack Generator.

        Args:
            model: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.tech_stack section
        """
        import os
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("tech_stack", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 4000)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or os.environ.get("OPENROUTER_API_KEY"))

    async def generate_tech_stack(
        self,
        project_name: str,
        domain: str,
        requirements: List[Any],
        constraints: Dict[str, Any],
        api_endpoints: Optional[List[Any]] = None,
        entities: Optional[List[Any]] = None
    ) -> TechStack:
        """Generate technology stack recommendation based on requirements."""

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

        # Build constraints text
        constraints_text = json.dumps(constraints, indent=2, ensure_ascii=False) if constraints else "Keine Constraints"

        # Build API summary
        api_summary = "Keine API-Spezifikation"
        if api_endpoints:
            api_lines = [f"- {ep.method} {ep.path}: {ep.summary}" for ep in api_endpoints[:10]]
            api_summary = "\n".join(api_lines)

        # Build entities summary
        entities_summary = "Keine Entities"
        if entities:
            # Handle both list and dict of entities
            entity_list = list(entities.values()) if isinstance(entities, dict) else list(entities)
            entity_lines = [f"- {e.name}: {len(e.attributes)} attributes" for e in entity_list[:10]]
            entities_summary = "\n".join(entity_lines)

        prompt = self.TECH_STACK_PROMPT.format(
            project_name=project_name,
            domain=domain,
            requirements_text=requirements_text,
            constraints_text=constraints_text,
            api_summary=api_summary,
            entities_summary=entities_summary
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
                component="tech_stack_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)

            return TechStack(
                project_name=project_name,
                frontend_framework=data.get("frontend_framework", ""),
                frontend_languages=data.get("frontend_languages", []),
                ui_library=data.get("ui_library", ""),
                state_management=data.get("state_management", ""),
                backend_language=data.get("backend_language", ""),
                backend_framework=data.get("backend_framework", ""),
                api_style=data.get("api_style", "REST"),
                primary_database=data.get("primary_database", ""),
                cache_layer=data.get("cache_layer", ""),
                search_engine=data.get("search_engine", ""),
                cloud_provider=data.get("cloud_provider", ""),
                container_runtime=data.get("container_runtime", ""),
                orchestration=data.get("orchestration", ""),
                ci_cd=data.get("ci_cd", ""),
                message_queue=data.get("message_queue", ""),
                api_gateway=data.get("api_gateway", ""),
                rationale=data.get("rationale", {}),
                alternatives=data.get("alternatives", {}),
                architecture_pattern=data.get("architecture_pattern", ""),
                deployment_model=data.get("deployment_model", ""),
                # Gap #14: Pinned versions and package names
                versions=data.get("versions", {}),
                package_names=data.get("package_names", {}),
            )

        except json.JSONDecodeError as e:
            print(f"    [WARN] Could not parse tech stack JSON: {e}")
            return TechStack(project_name=project_name)
        except Exception as e:
            print(f"    [ERROR] Tech stack generation failed: {e}")
            return TechStack(project_name=project_name)

    def generate_architecture_diagram(self, tech_stack: TechStack) -> str:
        """Generate a C4 Context diagram for the tech stack."""

        mermaid = f"""C4Context
    title System Architecture - {tech_stack.project_name}

    Person(user, "User", "End user of the system")

    System_Boundary(system, "{tech_stack.project_name}") {{
        Container(frontend, "Frontend", "{tech_stack.frontend_framework}", "User Interface")
        Container(backend, "Backend API", "{tech_stack.backend_framework}", "{tech_stack.api_style} API")
        ContainerDb(db, "Database", "{tech_stack.primary_database}", "Primary data store")
"""

        if tech_stack.cache_layer and tech_stack.cache_layer != "none":
            mermaid += f'        ContainerDb(cache, "Cache", "{tech_stack.cache_layer}", "Caching layer")\n'

        if tech_stack.message_queue and tech_stack.message_queue != "none":
            mermaid += f'        Container(mq, "Message Queue", "{tech_stack.message_queue}", "Async messaging")\n'

        mermaid += """    }

    Rel(user, frontend, "Uses", "HTTPS")
    Rel(frontend, backend, "API calls", "HTTPS")
    Rel(backend, db, "Reads/Writes", "SQL/NoSQL")
"""

        if tech_stack.cache_layer and tech_stack.cache_layer != "none":
            mermaid += '    Rel(backend, cache, "Caches", "TCP")\n'

        if tech_stack.message_queue and tech_stack.message_queue != "none":
            mermaid += '    Rel(backend, mq, "Publishes/Subscribes", "AMQP/Kafka")\n'

        return mermaid


def save_tech_stack(tech_stack: TechStack, output_dir) -> None:
    """Save tech stack to files."""
    from pathlib import Path

    tech_dir = Path(output_dir) / "tech_stack"
    tech_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    with open(tech_dir / "tech_stack.json", "w", encoding="utf-8") as f:
        json.dump(tech_stack.to_dict(), f, indent=2, ensure_ascii=False)

    # Save Markdown
    md = generate_tech_stack_markdown(tech_stack)
    with open(tech_dir / "tech_stack.md", "w", encoding="utf-8") as f:
        f.write(md)

    # Save Architecture Diagram
    generator = TechStackGenerator.__new__(TechStackGenerator)
    diagram = generator.generate_architecture_diagram(tech_stack)
    with open(tech_dir / "architecture_diagram.mmd", "w", encoding="utf-8") as f:
        f.write(diagram)


def generate_tech_stack_markdown(tech_stack: TechStack) -> str:
    """Generate markdown documentation for tech stack."""

    md = f"""# Technology Stack - {tech_stack.project_name}

## Overview

| Category | Technology |
|----------|------------|
| Architecture | {tech_stack.architecture_pattern} |
| Deployment | {tech_stack.deployment_model} |

---

## Frontend

| Component | Technology |
|-----------|------------|
| Framework | **{tech_stack.frontend_framework}** |
| Languages | {', '.join(tech_stack.frontend_languages)} |
| UI Library | {tech_stack.ui_library} |
| State Management | {tech_stack.state_management} |

"""

    if "frontend_framework" in tech_stack.rationale:
        md += f"**Rationale:** {tech_stack.rationale['frontend_framework']}\n\n"

    md += f"""---

## Backend

| Component | Technology |
|-----------|------------|
| Language | **{tech_stack.backend_language}** |
| Framework | **{tech_stack.backend_framework}** |
| API Style | {tech_stack.api_style} |

"""

    if "backend_framework" in tech_stack.rationale:
        md += f"**Rationale:** {tech_stack.rationale['backend_framework']}\n\n"

    md += f"""---

## Data Layer

| Component | Technology |
|-----------|------------|
| Primary Database | **{tech_stack.primary_database}** |
| Cache | {tech_stack.cache_layer or 'None'} |
| Search Engine | {tech_stack.search_engine or 'None'} |

"""

    if "primary_database" in tech_stack.rationale:
        md += f"**Rationale:** {tech_stack.rationale['primary_database']}\n\n"

    md += f"""---

## Infrastructure

| Component | Technology |
|-----------|------------|
| Cloud Provider | **{tech_stack.cloud_provider}** |
| Container Runtime | {tech_stack.container_runtime} |
| Orchestration | {tech_stack.orchestration} |
| CI/CD | {tech_stack.ci_cd} |

---

## Integration

| Component | Technology |
|-----------|------------|
| Message Queue | {tech_stack.message_queue or 'None'} |
| API Gateway | {tech_stack.api_gateway or 'None'} |

---

## Alternatives Considered

"""

    for tech, alts in tech_stack.alternatives.items():
        if alts:
            md += f"### {tech.replace('_', ' ').title()}\n"
            for alt in alts:
                md += f"- {alt}\n"
            md += "\n"

    # Gap #14: Pinned versions table
    if tech_stack.versions:
        md += """---

## Pinned Versions

| Technology | Version | Package Name |
|------------|---------|--------------|
"""
        for tech, version in sorted(tech_stack.versions.items()):
            pkg = tech_stack.package_names.get(tech, "")
            md += f"| {tech} | `{version}` | `{pkg}` |\n"
        md += "\n"

    md += """---

## Architecture Diagram

See `architecture_diagram.mmd` for the C4 Context diagram.
"""

    return md
