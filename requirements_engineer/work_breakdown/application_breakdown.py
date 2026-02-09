"""
Application-based Work Breakdown Structure

Breaks down requirements into application-centric work packages.
Useful for multi-application systems (frontend, backend, mobile, etc.).
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import Enum


class ApplicationType(str, Enum):
    """Types of applications."""
    WEB_FRONTEND = "web_frontend"
    WEB_BACKEND = "web_backend"
    MOBILE_IOS = "mobile_ios"
    MOBILE_ANDROID = "mobile_android"
    DESKTOP = "desktop"
    CLI = "cli"
    API_GATEWAY = "api_gateway"
    WORKER = "worker"
    DATABASE = "database"


@dataclass_json
@dataclass
class ApplicationWorkPackage:
    """A work package representing an application."""
    app_id: str
    app_name: str
    app_type: str
    description: str
    requirements: List[str]  # Requirement IDs
    technology_stack: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # Other app IDs
    deployment_target: str = ""
    interfaces: List[Dict[str, str]] = field(default_factory=list)
    mermaid_diagrams: Dict[str, str] = field(default_factory=dict)
    build_commands: List[str] = field(default_factory=list)
    test_strategy: str = ""


class ApplicationBreakdown:
    """
    Breaks down requirements into application-based work packages.

    Applications are deployable units that together form the complete system.
    Useful for multi-tier architectures and polyglot systems.
    """

    def __init__(self):
        self.applications: Dict[str, ApplicationWorkPackage] = {}
        self.requirement_to_apps: Dict[str, List[str]] = {}
        self.app_communications: List[Dict[str, str]] = []

    def create_application(
        self,
        app_id: str,
        app_name: str,
        app_type: str,
        description: str,
        technology_stack: Dict[str, str] = None,
        deployment_target: str = ""
    ) -> ApplicationWorkPackage:
        """Create a new application work package."""
        app = ApplicationWorkPackage(
            app_id=app_id,
            app_name=app_name,
            app_type=app_type,
            description=description,
            requirements=[],
            technology_stack=technology_stack or {},
            deployment_target=deployment_target
        )
        self.applications[app_id] = app
        return app

    def assign_requirement(self, requirement_id: str, app_id: str) -> bool:
        """Assign a requirement to an application."""
        if app_id not in self.applications:
            return False

        if requirement_id not in self.applications[app_id].requirements:
            self.applications[app_id].requirements.append(requirement_id)

        if requirement_id not in self.requirement_to_apps:
            self.requirement_to_apps[requirement_id] = []
        if app_id not in self.requirement_to_apps[requirement_id]:
            self.requirement_to_apps[requirement_id].append(app_id)

        return True

    def add_interface(
        self,
        app_id: str,
        interface_type: str,
        protocol: str,
        description: str
    ) -> bool:
        """Add an interface to an application."""
        if app_id not in self.applications:
            return False

        self.applications[app_id].interfaces.append({
            "type": interface_type,  # api, ui, event, file, etc.
            "protocol": protocol,  # http, grpc, websocket, etc.
            "description": description
        })
        return True

    def add_communication(
        self,
        from_app: str,
        to_app: str,
        protocol: str,
        description: str
    ) -> None:
        """Record communication between applications."""
        self.app_communications.append({
            "from": from_app,
            "to": to_app,
            "protocol": protocol,
            "description": description
        })

        # Add as dependency
        if from_app in self.applications and to_app not in self.applications[from_app].dependencies:
            self.applications[from_app].dependencies.append(to_app)

    def get_apps_for_requirement(self, requirement_id: str) -> List[str]:
        """Get all applications involved in implementing a requirement."""
        return self.requirement_to_apps.get(requirement_id, [])

    def get_apps_by_type(self, app_type: str) -> List[ApplicationWorkPackage]:
        """Get all applications of a specific type."""
        return [a for a in self.applications.values() if a.app_type == app_type]

    def generate_breakdown_from_requirements(
        self,
        requirements: List[Any],
        architecture_type: str = "three_tier"
    ) -> None:
        """
        Generate application breakdown from requirements.

        Args:
            requirements: List of RequirementNode objects
            architecture_type: Type of architecture (three_tier, microservices, monolith)
        """
        if architecture_type == "three_tier":
            self._generate_three_tier(requirements)
        elif architecture_type == "microservices":
            self._generate_microservices(requirements)
        else:
            self._generate_monolith(requirements)

    def _generate_three_tier(self, requirements: List[Any]) -> None:
        """Generate a three-tier architecture breakdown."""
        # Create standard three-tier applications
        self.create_application(
            app_id="APP-001",
            app_name="Frontend Application",
            app_type=ApplicationType.WEB_FRONTEND.value,
            description="Web-based user interface",
            technology_stack={"framework": "React/Vue/Angular", "language": "TypeScript"},
            deployment_target="CDN/Static hosting"
        )

        self.create_application(
            app_id="APP-002",
            app_name="Backend API",
            app_type=ApplicationType.WEB_BACKEND.value,
            description="REST/GraphQL API server",
            technology_stack={"framework": "FastAPI/Express/Spring", "language": "Python/Node/Java"},
            deployment_target="Container/PaaS"
        )

        self.create_application(
            app_id="APP-003",
            app_name="Database",
            app_type=ApplicationType.DATABASE.value,
            description="Persistent data storage",
            technology_stack={"database": "PostgreSQL/MongoDB"},
            deployment_target="Managed DB service"
        )

        # Add communications
        self.add_communication("APP-001", "APP-002", "HTTP/REST", "API calls")
        self.add_communication("APP-002", "APP-003", "SQL/Driver", "Data queries")

        # Assign requirements based on type
        for req in requirements:
            if req.type == "non_functional":
                # Non-functional requirements often span all apps
                for app_id in self.applications:
                    self.assign_requirement(req.requirement_id, app_id)
            elif self._is_ui_requirement(req):
                self.assign_requirement(req.requirement_id, "APP-001")
                self.assign_requirement(req.requirement_id, "APP-002")  # API support
            elif self._is_data_requirement(req):
                self.assign_requirement(req.requirement_id, "APP-002")
                self.assign_requirement(req.requirement_id, "APP-003")
            else:
                # Default to backend
                self.assign_requirement(req.requirement_id, "APP-002")

    def _generate_microservices(self, requirements: List[Any]) -> None:
        """Generate a microservices architecture breakdown."""
        # API Gateway
        self.create_application(
            app_id="APP-001",
            app_name="API Gateway",
            app_type=ApplicationType.API_GATEWAY.value,
            description="Entry point for all API requests",
            technology_stack={"framework": "Kong/Ambassador"},
            deployment_target="Kubernetes"
        )

        # Frontend
        self.create_application(
            app_id="APP-002",
            app_name="Frontend SPA",
            app_type=ApplicationType.WEB_FRONTEND.value,
            description="Single-page application",
            technology_stack={"framework": "React", "language": "TypeScript"},
            deployment_target="CDN"
        )

        # Group requirements into services
        service_groups = self._group_requirements_for_microservices(requirements)

        app_counter = 3
        for service_name, req_ids in service_groups.items():
            app_id = f"APP-{app_counter:03d}"
            self.create_application(
                app_id=app_id,
                app_name=f"{service_name} Service",
                app_type=ApplicationType.WEB_BACKEND.value,
                description=f"Microservice for {service_name.lower()}",
                technology_stack={"framework": "FastAPI/Spring Boot"},
                deployment_target="Kubernetes"
            )

            self.add_communication("APP-001", app_id, "HTTP/gRPC", f"{service_name} API")

            for req_id in req_ids:
                self.assign_requirement(req_id, app_id)

            app_counter += 1

    def _generate_monolith(self, requirements: List[Any]) -> None:
        """Generate a monolithic architecture breakdown."""
        self.create_application(
            app_id="APP-001",
            app_name="Monolithic Application",
            app_type=ApplicationType.WEB_BACKEND.value,
            description="Full-stack monolithic application",
            technology_stack={"framework": "Django/Rails/Spring MVC"},
            deployment_target="VM/Container"
        )

        self.create_application(
            app_id="APP-002",
            app_name="Database",
            app_type=ApplicationType.DATABASE.value,
            description="Relational database",
            technology_stack={"database": "PostgreSQL"},
            deployment_target="Managed DB"
        )

        self.add_communication("APP-001", "APP-002", "SQL", "Data persistence")

        # All requirements go to the monolith
        for req in requirements:
            self.assign_requirement(req.requirement_id, "APP-001")
            if self._is_data_requirement(req):
                self.assign_requirement(req.requirement_id, "APP-002")

    def _is_ui_requirement(self, req: Any) -> bool:
        """Check if requirement is UI-related."""
        keywords = ["display", "show", "view", "interface", "screen", "form", "button", "ui", "ux"]
        text = f"{req.title} {req.description}".lower()
        return any(kw in text for kw in keywords)

    def _is_data_requirement(self, req: Any) -> bool:
        """Check if requirement is data-related."""
        keywords = ["store", "save", "persist", "database", "data", "record", "query"]
        text = f"{req.title} {req.description}".lower()
        return any(kw in text for kw in keywords)

    def _group_requirements_for_microservices(
        self,
        requirements: List[Any]
    ) -> Dict[str, List[str]]:
        """Group requirements for microservice breakdown."""
        groups: Dict[str, List[str]] = {}

        # Domain-based grouping
        domain_keywords = {
            "User": ["user", "account", "profile", "auth", "login"],
            "Order": ["order", "cart", "checkout", "purchase"],
            "Product": ["product", "catalog", "inventory", "item"],
            "Payment": ["payment", "billing", "invoice"],
            "Notification": ["notification", "email", "alert"]
        }

        for req in requirements:
            text = f"{req.title} {req.description}".lower()
            assigned = False

            for domain, keywords in domain_keywords.items():
                if any(kw in text for kw in keywords):
                    if domain not in groups:
                        groups[domain] = []
                    groups[domain].append(req.requirement_id)
                    assigned = True
                    break

            if not assigned:
                if "Core" not in groups:
                    groups["Core"] = []
                groups["Core"].append(req.requirement_id)

        return groups

    def generate_c4_diagram(self) -> str:
        """Generate a C4 Context diagram for the applications."""
        lines = ["C4Context", "    title System Context Diagram", ""]

        # Add external user
        lines.append('    Person(user, "User", "System user")')
        lines.append("")

        # Add applications
        for app_id, app in self.applications.items():
            if app.app_type == ApplicationType.DATABASE.value:
                lines.append(f'    SystemDb({app_id}, "{app.app_name}", "{app.description}")')
            else:
                lines.append(f'    System({app_id}, "{app.app_name}", "{app.description}")')

        lines.append("")

        # Add relationships
        frontend_apps = [a.app_id for a in self.applications.values()
                        if a.app_type in [ApplicationType.WEB_FRONTEND.value, ApplicationType.MOBILE_IOS.value, ApplicationType.MOBILE_ANDROID.value]]

        for app_id in frontend_apps:
            lines.append(f'    Rel(user, {app_id}, "Uses")')

        for comm in self.app_communications:
            lines.append(f'    Rel({comm["from"]}, {comm["to"]}, "{comm["description"]}")')

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Export breakdown as Markdown."""
        lines = ["# Application Work Breakdown Structure\n"]

        # Summary
        lines.append("## Summary\n")
        lines.append(f"- Total Applications: {len(self.applications)}")
        for app_type in ApplicationType:
            count = len(self.get_apps_by_type(app_type.value))
            if count > 0:
                lines.append(f"- {app_type.value}: {count}")
        lines.append("")

        # Applications
        lines.append("## Applications\n")
        for app_id, app in self.applications.items():
            lines.append(f"### {app.app_id}: {app.app_name}\n")
            lines.append(f"**Type:** {app.app_type}")
            lines.append(f"**Deployment:** {app.deployment_target or 'TBD'}")
            lines.append(f"\n{app.description}\n")

            if app.technology_stack:
                lines.append("**Technology Stack:**")
                for key, value in app.technology_stack.items():
                    lines.append(f"- {key}: {value}")
                lines.append("")

            if app.requirements:
                lines.append("**Requirements:**")
                for req_id in app.requirements:
                    lines.append(f"- {req_id}")
                lines.append("")

            if app.interfaces:
                lines.append("**Interfaces:**")
                for iface in app.interfaces:
                    lines.append(f"- {iface['type']} ({iface['protocol']}): {iface['description']}")
                lines.append("")

            if app.dependencies:
                lines.append(f"**Dependencies:** {', '.join(app.dependencies)}\n")

        # Communications
        if self.app_communications:
            lines.append("## Application Communications\n")
            for comm in self.app_communications:
                lines.append(f"- **{comm['from']}** → **{comm['to']}** ({comm['protocol']}): {comm['description']}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Export breakdown as dictionary."""
        return {
            "breakdown_type": "application",
            "applications": {aid: a.to_dict() for aid, a in self.applications.items()},
            "requirement_mapping": self.requirement_to_apps,
            "communications": self.app_communications
        }
