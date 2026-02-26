"""
Task List Generator - Generates tasks from work packages and features.

This module derives actionable tasks from features, user stories, and requirements
with effort estimation, dependencies, and assignment recommendations.
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
class Task:
    """Individual task derived from features/stories."""
    id: str
    title: str
    description: str
    task_type: str  # development, design, testing, devops, documentation

    # Relationships
    parent_feature_id: str = ""
    parent_user_story_id: str = ""
    parent_requirement_id: str = ""
    parent_entity_id: str = ""  # For DATABASE tasks - links to ENTITY-xxx
    parent_api_resource: str = ""  # For API tasks - links to API-xxx

    # Estimation
    estimated_hours: int = 0
    complexity: str = "medium"  # trivial, simple, medium, complex, epic
    story_points: int = 0

    # Dependencies
    depends_on: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)

    # Assignment
    required_skills: List[str] = field(default_factory=list)
    suggested_assignee_role: str = ""

    # Status tracking
    status: str = "todo"  # todo, in_progress, review, done
    acceptance_criteria: List[str] = field(default_factory=list)


@dataclass_json
@dataclass
class TaskBreakdown:
    """Complete task breakdown for a project."""
    project_name: str
    features: Dict[str, List[Task]] = field(default_factory=dict)  # Feature ID -> Tasks
    total_tasks: int = 0
    total_hours: int = 0
    total_story_points: int = 0
    critical_path: List[str] = field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def tasks(self) -> List[Task]:
        """Get all tasks from all features (flattened list)."""
        all_tasks = []
        for task_list in self.features.values():
            all_tasks.extend(task_list)
        return all_tasks


class TaskGenerator:
    """Generates tasks from features, user stories, and requirements."""

    TASK_PROMPT = """Du bist ein erfahrener Project Manager. Analysiere das folgende Feature/Work Package und erstelle eine Liste von Tasks.

## Feature: {feature_name}
{feature_description}

## Zugehoerige User Stories:
{user_stories_text}

## Zugehoerige Requirements:
{requirements_text}

Erstelle Tasks im folgenden JSON-Format:

{{
    "tasks": [
        {{
            "id": "TASK-001",
            "title": "Kurzer Task-Titel",
            "description": "Detaillierte Beschreibung was zu tun ist",
            "task_type": "development|design|testing|devops|documentation",
            "estimated_hours": 8,
            "complexity": "trivial|simple|medium|complex|epic",
            "story_points": 3,
            "depends_on": ["TASK-000"],
            "required_skills": ["frontend", "typescript"],
            "suggested_assignee_role": "Frontend Developer",
            "acceptance_criteria": [
                "Kriterium 1",
                "Kriterium 2"
            ]
        }}
    ]
}}

Beachte:
- Erstelle 3-8 Tasks pro Feature
- Jeder Task sollte in max. 16 Stunden erledigt sein (sonst aufteilen)
- Task-Typen: development, design, testing, devops, documentation
- Complexity: trivial (1h), simple (2-4h), medium (4-8h), complex (8-16h), epic (>16h)
- Story Points: 1, 2, 3, 5, 8, 13 (Fibonacci)
- Definiere Abhaengigkeiten zwischen Tasks

Antworte NUR mit dem JSON-Objekt."""

    COMPLEXITY_HOURS = {
        "trivial": 1,
        "simple": 3,
        "medium": 6,
        "complex": 12,
        "epic": 24
    }

    COMPLEXITY_POINTS = {
        "trivial": 1,
        "simple": 2,
        "medium": 3,
        "complex": 5,
        "epic": 8
    }

    def __init__(
        self,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Task Generator.

        Args:
            model: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.task section
        """
        import os
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("task", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or os.environ.get("OPENROUTER_API_KEY"))
        self.task_counter = 0

    async def generate_tasks_for_feature(
        self,
        feature_id: str,
        feature_name: str,
        feature_description: str,
        user_stories: List[Any] = None,
        requirements: List[Any] = None
    ) -> List[Task]:
        """Generate tasks for a single feature."""

        # Build user stories text
        us_lines = []
        if user_stories:
            for us in user_stories[:5]:
                if hasattr(us, 'title'):
                    us_lines.append(f"- {us.id}: {us.title}")
                elif isinstance(us, dict):
                    us_lines.append(f"- {us.get('id', 'US')}: {us.get('title', '')}")
        user_stories_text = "\n".join(us_lines) if us_lines else "Keine User Stories"

        # Build requirements text
        req_lines = []
        if requirements:
            for req in requirements[:5]:
                if hasattr(req, 'title'):
                    req_lines.append(f"- {req.requirement_id}: {req.title}")
                elif isinstance(req, dict):
                    req_lines.append(f"- {req.get('id', 'REQ')}: {req.get('title', '')}")
        requirements_text = "\n".join(req_lines) if req_lines else "Keine Requirements"

        prompt = self.TASK_PROMPT.format(
            feature_name=feature_name,
            feature_description=feature_description,
            user_stories_text=user_stories_text,
            requirements_text=requirements_text
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
                component="task_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            tasks = []

            for task_data in data.get("tasks", []):
                self.task_counter += 1
                task_id = f"TASK-{self.task_counter:03d}"

                task = Task(
                    id=task_id,
                    title=task_data.get("title", "Untitled Task"),
                    description=task_data.get("description", ""),
                    task_type=task_data.get("task_type", "development"),
                    parent_feature_id=feature_id,
                    estimated_hours=task_data.get("estimated_hours", self.COMPLEXITY_HOURS.get(task_data.get("complexity", "medium"), 6)),
                    complexity=task_data.get("complexity", "medium"),
                    story_points=task_data.get("story_points", self.COMPLEXITY_POINTS.get(task_data.get("complexity", "medium"), 3)),
                    depends_on=task_data.get("depends_on", []),
                    required_skills=task_data.get("required_skills", []),
                    suggested_assignee_role=task_data.get("suggested_assignee_role", ""),
                    acceptance_criteria=task_data.get("acceptance_criteria", [])
                )
                tasks.append(task)

            return tasks

        except json.JSONDecodeError as e:
            print(f"    [WARN] Could not parse tasks JSON: {e}")
            return []
        except Exception as e:
            print(f"    [ERROR] Task generation failed: {e}")
            return []

    async def generate_all_tasks(
        self,
        features: List[Any],
        user_stories: List[Any] = None,
        requirements: List[Any] = None,
        api_endpoints: List[Any] = None,
        entities: List[Any] = None
    ) -> TaskBreakdown:
        """Generate tasks for all features."""

        breakdown = TaskBreakdown(project_name="Project Tasks")
        self.task_counter = 0

        # Group user stories and requirements by feature if possible
        us_by_feature = {}
        req_by_feature = {}

        if user_stories:
            for us in user_stories:
                fid = getattr(us, 'linked_epic', None) or (us.get('linked_epic') if isinstance(us, dict) else None)
                if fid:
                    us_by_feature.setdefault(fid, []).append(us)

        print(f"  Generating tasks for {len(features)} features...")

        for i, feature in enumerate(features, 1):
            # Extract feature info
            if hasattr(feature, 'id'):
                feature_id = feature.id
                feature_name = getattr(feature, 'name', feature.id)
                feature_desc = getattr(feature, 'description', '')
            elif isinstance(feature, dict):
                feature_id = feature.get('id', f'FEAT-{i:03d}')
                feature_name = feature.get('name', feature.get('title', feature_id))
                feature_desc = feature.get('description', '')
            else:
                feature_id = f'FEAT-{i:03d}'
                feature_name = str(feature)
                feature_desc = ''

            print(f"    [{i}/{len(features)}] {feature_name}...")

            # Get related user stories
            related_us = us_by_feature.get(feature_id, user_stories[:3] if user_stories else [])

            tasks = await self.generate_tasks_for_feature(
                feature_id=feature_id,
                feature_name=feature_name,
                feature_description=feature_desc,
                user_stories=related_us,
                requirements=requirements
            )

            if tasks:
                breakdown.features[feature_id] = tasks
                print(f"      Generated {len(tasks)} tasks")

        # Add infrastructure tasks from entities (DB migrations)
        if entities:
            db_tasks = self._generate_db_tasks(entities)
            breakdown.features["DATABASE"] = db_tasks
            print(f"    Generated {len(db_tasks)} database tasks")

        # Add API tasks
        if api_endpoints:
            api_tasks = self._generate_api_tasks(api_endpoints)
            breakdown.features["API"] = api_tasks
            print(f"    Generated {len(api_tasks)} API tasks")

        # Calculate totals
        all_tasks = [t for tasks in breakdown.features.values() for t in tasks]
        breakdown.total_tasks = len(all_tasks)
        breakdown.total_hours = sum(t.estimated_hours for t in all_tasks)
        breakdown.total_story_points = sum(t.story_points for t in all_tasks)

        # Build dependency graph
        breakdown.dependency_graph = self._build_dependency_graph(all_tasks)

        # Calculate critical path (simplified)
        breakdown.critical_path = self._calculate_critical_path(all_tasks)

        return breakdown

    def _generate_db_tasks(self, entities: List[Any]) -> List[Task]:
        """Generate database-related tasks from entities."""
        tasks = []
        # Handle both list and dict of entities
        entity_list = list(entities.values()) if isinstance(entities, dict) else list(entities)
        for i, entity in enumerate(entity_list[:10], 1):
            self.task_counter += 1
            name = getattr(entity, 'name', str(entity)) if hasattr(entity, 'name') else entity.get('name', f'Entity{i}')

            # Generate entity ID to match Dashboard naming convention
            entity_id = f"ENTITY-{name.upper().replace(' ', '-')}"

            task = Task(
                id=f"TASK-{self.task_counter:03d}",
                title=f"Create {name} model and migration",
                description=f"Implement database model for {name} entity with all attributes and relationships. Create migration script.",
                task_type="development",
                parent_feature_id="DATABASE",
                parent_entity_id=entity_id,  # Direct link to entity node
                estimated_hours=4,
                complexity="medium",
                story_points=3,
                required_skills=["backend", "database", "orm"],
                suggested_assignee_role="Backend Developer",
                acceptance_criteria=[
                    f"{name} model created with all attributes",
                    "Migration script works forward and backward",
                    "Unit tests for model validation"
                ]
            )
            tasks.append(task)

        return tasks

    def _generate_api_tasks(self, endpoints: List[Any]) -> List[Task]:
        """Generate API implementation tasks from endpoints."""
        tasks = []
        # Group by resource
        resources = {}
        for ep in endpoints:
            # Handle both objects and dicts
            path = ep.get('path', '/') if isinstance(ep, dict) else getattr(ep, 'path', '/')
            resource = path.split('/')[1] if len(path.split('/')) > 1 else 'root'
            resources.setdefault(resource, []).append(ep)

        for resource, eps in list(resources.items())[:10]:
            self.task_counter += 1
            # Generate API resource ID to match Dashboard naming convention
            api_resource_id = f"API-{resource.upper().replace(' ', '-')}"

            task = Task(
                id=f"TASK-{self.task_counter:03d}",
                title=f"Implement {resource} API endpoints",
                description=f"Implement {len(eps)} endpoints for {resource} resource including validation, error handling, and documentation.",
                task_type="development",
                parent_feature_id="API",
                parent_api_resource=api_resource_id,  # Direct link to API resource
                estimated_hours=8 if len(eps) > 3 else 4,
                complexity="complex" if len(eps) > 3 else "medium",
                story_points=5 if len(eps) > 3 else 3,
                required_skills=["backend", "api", "rest"],
                suggested_assignee_role="Backend Developer",
                acceptance_criteria=[
                    f"All {len(eps)} endpoints implemented",
                    "Request/response validation",
                    "OpenAPI documentation updated",
                    "Integration tests written"
                ]
            )
            tasks.append(task)

        return tasks

    def _build_dependency_graph(self, tasks: List[Task]) -> Dict[str, List[str]]:
        """Build task dependency graph."""
        graph = {}
        for task in tasks:
            graph[task.id] = task.depends_on.copy() if task.depends_on else []
        return graph

    def _calculate_critical_path(self, tasks: List[Task]) -> List[str]:
        """Calculate critical path (simplified - longest chain)."""
        # Find tasks with no dependencies (roots)
        task_map = {t.id: t for t in tasks}
        roots = [t.id for t in tasks if not t.depends_on]

        if not roots:
            return [tasks[0].id] if tasks else []

        # Simple approach: find longest path from any root
        def get_path_length(task_id: str, visited: set) -> tuple:
            if task_id in visited or task_id not in task_map:
                return (0, [])
            visited.add(task_id)
            task = task_map[task_id]

            # Find tasks that depend on this one
            dependents = [t.id for t in tasks if task_id in t.depends_on]
            if not dependents:
                return (task.estimated_hours, [task_id])

            max_length = 0
            max_path = []
            for dep in dependents:
                length, path = get_path_length(dep, visited.copy())
                if length > max_length:
                    max_length = length
                    max_path = path

            return (task.estimated_hours + max_length, [task_id] + max_path)

        # Find longest path from any root
        longest_path = []
        for root in roots:
            _, path = get_path_length(root, set())
            if len(path) > len(longest_path):
                longest_path = path

        return longest_path


def save_task_list(breakdown: TaskBreakdown, output_dir) -> None:
    """Save task breakdown to files."""
    from pathlib import Path

    tasks_dir = Path(output_dir) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    with open(tasks_dir / "task_list.json", "w", encoding="utf-8") as f:
        json.dump(breakdown.to_dict(), f, indent=2, ensure_ascii=False)

    # Save Markdown
    md = generate_task_list_markdown(breakdown)
    with open(tasks_dir / "task_list.md", "w", encoding="utf-8") as f:
        f.write(md)

    # Save Gantt Chart
    gantt = generate_gantt_chart(breakdown)
    with open(tasks_dir / "gantt_chart.mmd", "w", encoding="utf-8") as f:
        f.write(gantt)

    # Save Dependency Graph
    dep_graph = generate_dependency_diagram(breakdown)
    with open(tasks_dir / "dependency_graph.mmd", "w", encoding="utf-8") as f:
        f.write(dep_graph)


def generate_task_list_markdown(breakdown: TaskBreakdown) -> str:
    """Generate markdown documentation for task list."""

    md = f"""# Task List - {breakdown.project_name}

## Summary

| Metric | Value |
|--------|-------|
| Total Tasks | {breakdown.total_tasks} |
| Total Hours | {breakdown.total_hours}h |
| Total Story Points | {breakdown.total_story_points} |

---

## Critical Path

The following tasks are on the critical path:

"""

    for i, task_id in enumerate(breakdown.critical_path[:10], 1):
        md += f"{i}. `{task_id}`\n"

    md += "\n---\n\n## Tasks by Feature\n\n"

    for feature_id, tasks in breakdown.features.items():
        feature_hours = sum(t.estimated_hours for t in tasks)
        feature_points = sum(t.story_points for t in tasks)

        md += f"""### {feature_id}

| Tasks | Hours | Points |
|-------|-------|--------|
| {len(tasks)} | {feature_hours}h | {feature_points} |

"""

        for task in tasks:
            md += f"""#### {task.id}: {task.title}

- **Type:** {task.task_type}
- **Complexity:** {task.complexity}
- **Estimated:** {task.estimated_hours}h / {task.story_points} points
- **Skills:** {', '.join(task.required_skills) if task.required_skills else 'General'}
- **Assignee:** {task.suggested_assignee_role or 'TBD'}

{task.description}

**Acceptance Criteria:**
"""
            for ac in task.acceptance_criteria:
                md += f"- [ ] {ac}\n"

            if task.depends_on:
                md += f"\n**Depends on:** {', '.join(task.depends_on)}\n"

            md += "\n---\n\n"

    return md


def generate_gantt_chart(breakdown: TaskBreakdown) -> str:
    """Generate Mermaid Gantt chart."""

    gantt = f"""gantt
    title {breakdown.project_name} - Project Schedule
    dateFormat  YYYY-MM-DD
    excludes    weekends

"""

    for feature_id, tasks in breakdown.features.items():
        gantt += f"    section {feature_id}\n"
        for task in tasks[:5]:  # Limit per feature for readability
            duration = max(1, task.estimated_hours // 8)  # Convert to days
            deps = f"after {task.depends_on[0]}" if task.depends_on else ""
            gantt += f"    {task.title[:30]} :{task.id}, {deps}, {duration}d\n"

    return gantt


def generate_dependency_diagram(breakdown: TaskBreakdown) -> str:
    """Generate Mermaid flowchart for dependencies."""

    diagram = """flowchart LR
    subgraph Tasks
"""

    all_tasks = [t for tasks in breakdown.features.values() for t in tasks]

    for task in all_tasks[:20]:  # Limit for readability
        shape = "([" if task.task_type == "testing" else "[" if task.task_type == "development" else "(("
        shape_end = "])" if task.task_type == "testing" else "]" if task.task_type == "development" else "))"
        diagram += f"        {task.id}{shape}{task.title[:20]}{shape_end}\n"

    diagram += "    end\n\n"

    # Add dependencies
    for task in all_tasks[:20]:
        for dep in task.depends_on:
            if any(t.id == dep for t in all_tasks[:20]):
                diagram += f"    {dep} --> {task.id}\n"

    return diagram
