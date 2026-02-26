"""
Link Configuration Generator for Dashboard Visualization.

Generates project-specific link_config.json based on discovered relationships.
This enables dynamic visualization of connections between requirements, user stories,
tests, diagrams, and other artifacts.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Set
from datetime import datetime
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class LinkType:
    """Definition of a link type between node types."""
    id: str
    from_type: str
    to_type: str
    relation: str
    color: str
    label: str
    label_en: Optional[str] = None
    style: str = "solid"  # solid, dashed, dotted
    arrow: bool = True


@dataclass
class NodeTypeConfig:
    """Visual configuration for a node type."""
    id: str
    color: str
    icon: str
    label: str


@dataclass
class LinkConfig:
    """Complete link configuration for a project."""
    project_id: str
    link_types: List[LinkType] = field(default_factory=list)
    node_types: List[NodeTypeConfig] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'project_id': self.project_id,
            'generated_at': self.generated_at,
            'link_types': [asdict(lt) for lt in self.link_types],
            'node_types': [asdict(nt) for nt in self.node_types]
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# Default colors and icons for node types
DEFAULT_NODE_COLORS = {
    'requirement': ('#1d9bf0', '&#128203;', 'Requirement'),  # Blue
    'epic': ('#7856ff', '&#127919;', 'Epic'),  # Purple
    'user-story': ('#00ba7c', '&#128214;', 'User Story'),  # Green
    'test': ('#f4212e', '&#129514;', 'Test'),  # Red
    'diagram': ('#ffd400', '&#128202;', 'Diagram'),  # Yellow
    'persona': ('#f97316', '&#128100;', 'Persona'),  # Orange
    'user-flow': ('#ec4899', '&#128260;', 'User Flow'),  # Pink
    'screen': ('#8b5cf6', '&#128421;', 'Screen'),  # Violet
    'component': ('#84cc16', '&#129513;', 'Component'),  # Lime
    'api': ('#ff7a00', '&#128268;', 'API'),  # Orange-Red
    'task': ('#f59e0b', '&#9989;', 'Task'),  # Amber
    'tech-stack': ('#06b6d4', '&#128295;', 'Tech Stack'),  # Cyan
    'feature': ('#10b981', '&#11088;', 'Feature'),  # Emerald
    'entity': ('#6366f1', '&#128451;', 'Entity'),  # Indigo
}

# Default link type definitions
DEFAULT_LINK_TYPES = [
    # Core traceability chain: REQ → US → Test
    LinkType('req-story', 'requirement', 'user-story', 'implements', '#1d9bf0', 'implementiert', 'implements'),
    LinkType('epic-story', 'epic', 'user-story', 'derives', '#7856ff', 'leitet ab', 'derives'),
    LinkType('story-test', 'user-story', 'test', 'verified_by', '#00ba7c', 'getestet durch', 'tested by'),
    LinkType('req-diagram', 'requirement', 'diagram', 'visualized_by', '#ffd400', 'visualisiert', 'visualized by'),
    # Persona & Flow
    LinkType('persona-story', 'persona', 'user-story', 'needs', '#f97316', 'benoetigt', 'needs'),
    LinkType('persona-screen', 'persona', 'screen', 'uses', '#f97316', 'nutzt', 'uses'),
    LinkType('flow-screen', 'user-flow', 'screen', 'contains', '#ec4899', 'enthaelt', 'contains'),
    # Screen & Component
    LinkType('screen-comp', 'screen', 'component', 'uses', '#84cc16', 'verwendet', 'uses'),
    LinkType('story-screen', 'user-story', 'screen', 'realized_in', '#8b5cf6', 'realisiert in', 'realized in'),
    # Tasks
    LinkType('epic-task', 'epic', 'task', 'breaks_down', '#f59e0b', 'unterteilt in', 'breaks down to'),
    LinkType('story-task', 'user-story', 'task', 'implemented_by', '#10b981', 'umgesetzt durch', 'implemented by'),
    # API links (new for graph enhancement)
    LinkType('req-api', 'requirement', 'api', 'exposes', '#ff7a00', 'exponiert', 'exposes'),
    LinkType('api-screen', 'api', 'screen', 'consumed_by', '#8b5cf6', 'konsumiert von', 'consumed by'),
    LinkType('comp-api', 'component', 'api', 'calls', '#ff7a00', 'ruft auf', 'calls'),
    LinkType('test-api', 'test', 'api', 'validates', '#f4212e', 'validiert', 'validates'),
    # Entity links (new for graph enhancement)
    LinkType('api-entity', 'api', 'entity', 'manages', '#6366f1', 'verwaltet', 'manages'),
    LinkType('req-entity', 'requirement', 'entity', 'models', '#6366f1', 'modelliert', 'models'),
    LinkType('screen-entity', 'screen', 'entity', 'displays', '#84cc16', 'zeigt an', 'displays'),
    LinkType('entity-api', 'entity', 'api', 'served_by', '#6366f1', 'bedient durch', 'served by'),
    # Diagram & Feature
    LinkType('diagram-entity', 'diagram', 'entity', 'shows', '#ffd400', 'zeigt', 'shows'),
    LinkType('req-feature', 'requirement', 'feature', 'defines', '#1d9bf0', 'definiert', 'defines'),
    LinkType('feature-story', 'feature', 'user-story', 'includes', '#10b981', 'beinhaltet', 'includes'),
    LinkType('tech-comp', 'tech-stack', 'component', 'enables', '#06b6d4', 'ermoeglicht', 'enables'),
]


class LinkConfigGenerator:
    """Generates link configuration based on project analysis."""

    def __init__(self, project_id: str):
        """
        Initialize LinkConfigGenerator.

        Args:
            project_id: Unique project identifier
        """
        self.project_id = project_id
        self.discovered_node_types: Set[str] = set()
        self.discovered_link_pairs: Set[str] = set()

    def analyze_connections(
        self,
        connections: List[Dict[str, Any]],
        nodes: Dict[str, Any]
    ) -> None:
        """
        Analyze existing connections to discover link types.

        Args:
            connections: List of connection dictionaries with 'from' and 'to' keys
            nodes: Dictionary of node data keyed by node ID
        """
        for conn in connections:
            from_id = conn.get('from')
            to_id = conn.get('to')

            from_node = nodes.get(from_id)
            to_node = nodes.get(to_id)

            if from_node and to_node:
                from_type = from_node.get('type', 'unknown')
                to_type = to_node.get('type', 'unknown')

                self.discovered_node_types.add(from_type)
                self.discovered_node_types.add(to_type)

                pair_key = f"{from_type}-{to_type}"
                self.discovered_link_pairs.add(pair_key)

        log.info(f"Discovered {len(self.discovered_node_types)} node types")
        log.info(f"Discovered {len(self.discovered_link_pairs)} link pairs")

    def analyze_artifacts(
        self,
        requirements: List[Any] = None,
        user_stories: List[Any] = None,
        epics: List[Any] = None,
        tests: List[Any] = None,
        diagrams: List[Any] = None,
        personas: List[Any] = None,
        screens: List[Any] = None,
        components: List[Any] = None,
        api_endpoints: List[Any] = None,
        tasks: List[Any] = None,
        entities: List[Any] = None
    ) -> None:
        """
        Analyze artifacts to discover node types.

        Args:
            Various lists of artifacts from the project
        """
        if requirements:
            self.discovered_node_types.add('requirement')
        if user_stories:
            self.discovered_node_types.add('user-story')
        if epics:
            self.discovered_node_types.add('epic')
        if tests:
            self.discovered_node_types.add('test')
        if diagrams:
            self.discovered_node_types.add('diagram')
        if personas:
            self.discovered_node_types.add('persona')
        if screens:
            self.discovered_node_types.add('screen')
        if components:
            self.discovered_node_types.add('component')
        if api_endpoints:
            self.discovered_node_types.add('api')
        if tasks:
            self.discovered_node_types.add('task')
        if entities:
            self.discovered_node_types.add('entity')

    def generate_config(self) -> LinkConfig:
        """
        Generate complete link configuration.

        Returns:
            LinkConfig with node types and link types
        """
        # Generate node type configurations
        node_types = []
        for node_type in sorted(self.discovered_node_types):
            config = DEFAULT_NODE_COLORS.get(node_type, ('#536471', '&#128196;', 'Unknown'))
            node_types.append(NodeTypeConfig(
                id=node_type,
                color=config[0],
                icon=config[1],
                label=config[2] if len(config) > 2 else node_type.replace('-', ' ').title()
            ))

        # Filter link types to only include those with discovered node types
        link_types = []
        for lt in DEFAULT_LINK_TYPES:
            # Include if both types are discovered
            if lt.from_type in self.discovered_node_types and lt.to_type in self.discovered_node_types:
                link_types.append(lt)

        # Add discovered pairs that don't have a default definition
        for pair in self.discovered_link_pairs:
            parts = pair.split('-', 1)
            if len(parts) == 2:
                from_type, to_type = parts
                # Check if we already have a link type for this pair
                exists = any(lt.from_type == from_type and lt.to_type == to_type for lt in link_types)
                if not exists:
                    # Create a generic link type
                    color = DEFAULT_NODE_COLORS.get(from_type, ('#536471',))[0]
                    link_types.append(LinkType(
                        id=pair,
                        from_type=from_type,
                        to_type=to_type,
                        relation='related',
                        color=color,
                        label='verknuepft mit',
                        label_en='linked to'
                    ))

        return LinkConfig(
            project_id=self.project_id,
            link_types=link_types,
            node_types=node_types
        )

    def save(self, output_dir: Path) -> Path:
        """
        Save link configuration to file.

        Args:
            output_dir: Directory to save the configuration

        Returns:
            Path to saved file
        """
        config = self.generate_config()
        output_path = Path(output_dir) / 'link_config.json'

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(config.to_json())

        log.info(f"Link configuration saved to {output_path}")
        log.info(f"  - {len(config.node_types)} node types")
        log.info(f"  - {len(config.link_types)} link types")

        return output_path


def generate_link_config(
    project_id: str,
    output_dir: Path,
    requirements: List[Any] = None,
    user_stories: List[Any] = None,
    epics: List[Any] = None,
    tests: List[Any] = None,
    diagrams: List[Any] = None,
    personas: List[Any] = None,
    screens: List[Any] = None,
    components: List[Any] = None,
    api_endpoints: List[Any] = None,
    tasks: List[Any] = None,
    entities: List[Any] = None
) -> Path:
    """
    Convenience function to generate link configuration.

    Args:
        project_id: Unique project identifier
        output_dir: Directory to save the configuration
        Various artifact lists

    Returns:
        Path to saved configuration file
    """
    generator = LinkConfigGenerator(project_id)
    generator.analyze_artifacts(
        requirements=requirements,
        user_stories=user_stories,
        epics=epics,
        tests=tests,
        diagrams=diagrams,
        personas=personas,
        screens=screens,
        components=components,
        api_endpoints=api_endpoints,
        tasks=tasks,
        entities=entities
    )
    return generator.save(output_dir)
