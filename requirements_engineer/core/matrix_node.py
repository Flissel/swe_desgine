"""
Matrix Node - Standardized data structure for matrix visualization events.

Provides consistent metadata schema for all artifacts generated in the 15-step
RE pipeline. Used by MatrixEventBridge to emit structured events to the dashboard.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class MatrixNodeType(Enum):
    """Types of nodes in the work package matrix."""
    REQUIREMENT = "requirement"
    USER_STORY = "user-story"
    EPIC = "epic"
    TEST = "test"
    DIAGRAM = "diagram"
    API = "api"
    TASK = "task"
    PERSONA = "persona"
    USER_FLOW = "user-flow"
    SCREEN = "screen"
    COMPONENT = "component"
    TECH_STACK = "tech-stack"
    DATA_ENTITY = "data-entity"
    WORK_PACKAGE = "work-package"
    REPORT = "report"


class MatrixColumn(Enum):
    """Column categories in the matrix layout."""
    REQUIREMENT = "requirement"
    USER_STORY = "user-story"
    EPIC = "epic"
    API = "api"
    TEST = "test"
    DIAGRAM_FLOWCHART = "diagram-flowchart"
    DIAGRAM_SEQUENCE = "diagram-sequence"
    DIAGRAM_CLASS = "diagram-class"
    DIAGRAM_ER = "diagram-er"
    DIAGRAM_STATE = "diagram-state"
    DIAGRAM_C4 = "diagram-c4"
    DATA_ENTITY = "data-entity"
    TECH_STACK = "tech-stack"
    PERSONA = "persona"
    USER_FLOW = "user-flow"
    COMPONENT = "component"
    SCREEN = "screen"
    TASK = "task"
    REPORT = "report"


@dataclass
class MatrixNodeMetadata:
    """
    Metadata for traceability and quality information.

    Attributes:
        created_at: ISO timestamp when node was created
        source_file: Original source file path
        priority: Priority level (must, should, could, wont)
        quality_score: Quality score 0-10
        traceability: List of linked node IDs
        tags: List of tags/labels
        step_number: Pipeline step number (1-15)
        pass_name: Pipeline pass name (discovery, analysis, specification, testing, validation)
    """
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source_file: str = ""
    priority: str = "should"
    quality_score: float = 0.0
    traceability: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    step_number: int = 0
    pass_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class MatrixNode:
    """
    A node in the work package matrix.

    Maps to frontend visualization where:
    - Rows represent work packages (grouped by requirement ID)
    - Columns represent node types (requirement, user_story, test, diagram, etc.)

    Attributes:
        id: Unique identifier (e.g., REQ-xxx-001, US-001, TEST-001)
        type: Node type for column placement
        row: Work Package ID (typically parent requirement ID)
        column: Column category for positioning
        title: Display title
        description: Detailed description
        content: Type-specific content object
        metadata: Traceability and quality metadata
        mermaid_code: Optional Mermaid diagram code
    """
    id: str
    type: MatrixNodeType
    row: str
    column: str
    title: str = ""
    description: str = ""
    content: Any = None
    metadata: MatrixNodeMetadata = field(default_factory=MatrixNodeMetadata)
    mermaid_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "row": self.row,
            "column": self.column,
            "title": self.title,
            "description": self.description,
            "mermaid_code": self.mermaid_code,
            "metadata": self.metadata.to_dict(),
            "content": self._serialize_content()
        }

    def _serialize_content(self) -> Any:
        """Serialize content object to JSON-compatible format."""
        if self.content is None:
            return None
        if hasattr(self.content, 'to_dict'):
            return self.content.to_dict()
        elif hasattr(self.content, '__dict__'):
            # Filter out private attributes and callables
            return {
                k: v for k, v in vars(self.content).items()
                if not k.startswith('_') and not callable(v)
            }
        elif isinstance(self.content, dict):
            return self.content
        return str(self.content)

    # ============================================
    # Factory Methods for Common Node Types
    # ============================================

    @classmethod
    def from_requirement(cls, req, step: int = 3) -> 'MatrixNode':
        """Create MatrixNode from a RequirementNode."""
        return cls(
            id=req.requirement_id,
            type=MatrixNodeType.REQUIREMENT,
            row=req.requirement_id,
            column=MatrixColumn.REQUIREMENT.value,
            title=req.title,
            description=getattr(req, 'description', ''),
            content=req,
            metadata=MatrixNodeMetadata(
                priority=getattr(req, 'priority', 'should'),
                tags=[getattr(req, 'type', 'functional')],
                step_number=step,
                pass_name="discovery",
                traceability=getattr(req, 'dependencies', []) or []
            )
        )

    @classmethod
    def from_user_story(cls, story, parent_req_id: str, step: int = 4) -> 'MatrixNode':
        """Create MatrixNode from a UserStory."""
        return cls(
            id=story.id,
            type=MatrixNodeType.USER_STORY,
            row=parent_req_id,
            column=MatrixColumn.USER_STORY.value,
            title=story.title,
            description=getattr(story, 'action', ''),
            content=story,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="analysis",
                traceability=[parent_req_id],
                tags=[getattr(story, 'persona', 'User')]
            )
        )

    @classmethod
    def from_epic(cls, epic, step: int = 4) -> 'MatrixNode':
        """Create MatrixNode from an Epic."""
        return cls(
            id=epic.id,
            type=MatrixNodeType.EPIC,
            row=epic.id,
            column=MatrixColumn.EPIC.value,
            title=epic.title,
            description=getattr(epic, 'description', ''),
            content=epic,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="analysis",
                traceability=getattr(epic, 'user_story_ids', []) or []
            )
        )

    @classmethod
    def from_test_case(cls, test, parent_req_id: str, step: int = 8) -> 'MatrixNode':
        """Create MatrixNode from a TestCase."""
        return cls(
            id=test.id if hasattr(test, 'id') else str(test.get('id', '')),
            type=MatrixNodeType.TEST,
            row=parent_req_id,
            column=MatrixColumn.TEST.value,
            title=test.title if hasattr(test, 'title') else test.get('title', ''),
            content=test,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="testing",
                traceability=[parent_req_id],
                tags=getattr(test, 'tags', []) if hasattr(test, 'tags') else test.get('tags', [])
            )
        )

    @classmethod
    def from_diagram(cls, req_id: str, diagram_type: str, mermaid_code: str, step: int = 11) -> 'MatrixNode':
        """Create MatrixNode from a Mermaid diagram."""
        column_map = {
            'flowchart': MatrixColumn.DIAGRAM_FLOWCHART.value,
            'sequence': MatrixColumn.DIAGRAM_SEQUENCE.value,
            'class': MatrixColumn.DIAGRAM_CLASS.value,
            'er': MatrixColumn.DIAGRAM_ER.value,
            'state': MatrixColumn.DIAGRAM_STATE.value,
            'c4': MatrixColumn.DIAGRAM_C4.value,
        }
        return cls(
            id=f"{req_id}-{diagram_type}",
            type=MatrixNodeType.DIAGRAM,
            row=req_id,
            column=column_map.get(diagram_type, f"diagram-{diagram_type}"),
            title=f"{diagram_type.title()} Diagram",
            mermaid_code=mermaid_code,
            content={"diagram_type": diagram_type, "code": mermaid_code},
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="specification",
                traceability=[req_id]
            )
        )

    @classmethod
    def from_api_endpoint(cls, endpoint, parent_req_id: str, step: int = 5) -> 'MatrixNode':
        """Create MatrixNode from an API endpoint."""
        method = getattr(endpoint, 'method', endpoint.get('method', 'GET'))
        path = getattr(endpoint, 'path', endpoint.get('path', '/'))
        return cls(
            id=f"API-{method}-{path.replace('/', '-').strip('-')}",
            type=MatrixNodeType.API,
            row=parent_req_id,
            column=MatrixColumn.API.value,
            title=f"{method} {path}",
            description=getattr(endpoint, 'summary', endpoint.get('summary', '')),
            content=endpoint,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="specification",
                traceability=[parent_req_id]
            )
        )

    @classmethod
    def from_data_entity(cls, entity, step: int = 6) -> 'MatrixNode':
        """Create MatrixNode from a data dictionary entity."""
        name = getattr(entity, 'name', entity.get('name', 'Entity'))
        return cls(
            id=f"ENTITY-{name.replace(' ', '-')}",
            type=MatrixNodeType.DATA_ENTITY,
            row="data-model",
            column=MatrixColumn.DATA_ENTITY.value,
            title=name,
            description=getattr(entity, 'description', entity.get('description', '')),
            content=entity,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="specification"
            )
        )

    @classmethod
    def from_tech_stack(cls, tech_stack, step: int = 7) -> 'MatrixNode':
        """Create MatrixNode from a TechStack recommendation."""
        backend = getattr(tech_stack, 'backend_framework', 'Unknown')
        frontend = getattr(tech_stack, 'frontend_framework', 'Unknown')
        return cls(
            id="TECH-STACK",
            type=MatrixNodeType.TECH_STACK,
            row="infrastructure",
            column=MatrixColumn.TECH_STACK.value,
            title=f"{backend} / {frontend}",
            content=tech_stack,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="architecture"
            )
        )

    @classmethod
    def from_persona(cls, persona, step: int = 9) -> 'MatrixNode':
        """Create MatrixNode from a UX persona."""
        name = getattr(persona, 'name', persona.get('name', 'Persona'))
        return cls(
            id=f"PERSONA-{name.replace(' ', '-')}",
            type=MatrixNodeType.PERSONA,
            row="ux-design",
            column=MatrixColumn.PERSONA.value,
            title=name,
            description=getattr(persona, 'description', persona.get('description', '')),
            content=persona,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="ux_design"
            )
        )

    @classmethod
    def from_user_flow(cls, flow, step: int = 9) -> 'MatrixNode':
        """Create MatrixNode from a user flow."""
        name = getattr(flow, 'name', flow.get('name', 'Flow'))
        return cls(
            id=f"FLOW-{name.replace(' ', '-')}",
            type=MatrixNodeType.USER_FLOW,
            row="ux-design",
            column=MatrixColumn.USER_FLOW.value,
            title=name,
            mermaid_code=getattr(flow, 'mermaid_code', flow.get('mermaid_code', None)),
            content=flow,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="ux_design"
            )
        )

    @classmethod
    def from_component(cls, component, step: int = 10) -> 'MatrixNode':
        """Create MatrixNode from a UI component."""
        name = getattr(component, 'name', component.get('name', 'Component'))
        return cls(
            id=f"COMP-{name.replace(' ', '-')}",
            type=MatrixNodeType.COMPONENT,
            row="ui-design",
            column=MatrixColumn.COMPONENT.value,
            title=name,
            content=component,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="ui_design"
            )
        )

    @classmethod
    def from_screen(cls, screen, step: int = 10) -> 'MatrixNode':
        """Create MatrixNode from a UI screen."""
        name = getattr(screen, 'name', screen.get('name', 'Screen'))
        return cls(
            id=f"SCREEN-{name.replace(' ', '-')}",
            type=MatrixNodeType.SCREEN,
            row="ui-design",
            column=MatrixColumn.SCREEN.value,
            title=name,
            content=screen,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="ui_design"
            )
        )

    @classmethod
    def from_work_package(cls, feature, feature_id: str, step: int = 12) -> 'MatrixNode':
        """Create MatrixNode from a work package/feature."""
        name = getattr(feature, 'feature_name', feature.get('feature_name', str(feature_id)))
        return cls(
            id=f"WP-{feature_id}",
            type=MatrixNodeType.WORK_PACKAGE,
            row=str(feature_id),
            column="work-package",
            title=name,
            content=feature,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="planning"
            )
        )

    @classmethod
    def from_task(cls, task, feature_id: str, step: int = 13) -> 'MatrixNode':
        """Create MatrixNode from a task."""
        task_id = task.get('id', f"TASK-{feature_id}")
        return cls(
            id=task_id,
            type=MatrixNodeType.TASK,
            row=feature_id,
            column=MatrixColumn.TASK.value,
            title=task.get('title', ''),
            description=task.get('description', ''),
            content=task,
            metadata=MatrixNodeMetadata(
                step_number=step,
                pass_name="planning",
                tags=[f"{task.get('hours', 0)}h"]
            )
        )
