"""
Service-based Work Breakdown Structure

Breaks down requirements into service/microservice-centric work packages.
Useful for distributed systems and microservice architectures.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class ServiceWorkPackage:
    """A work package representing a service/microservice."""
    service_id: str
    service_name: str
    description: str
    responsibilities: List[str]
    requirements: List[str]  # Requirement IDs
    api_endpoints: List[Dict[str, str]] = field(default_factory=list)
    data_entities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Other service IDs
    communication_protocols: List[str] = field(default_factory=list)
    mermaid_diagrams: Dict[str, str] = field(default_factory=dict)
    technology_stack: Dict[str, str] = field(default_factory=dict)


class ServiceBreakdown:
    """
    Breaks down requirements into service-based work packages.

    Services are independent, deployable units that handle specific
    business capabilities. Useful for microservice architectures.
    """

    def __init__(self):
        self.services: Dict[str, ServiceWorkPackage] = {}
        self.requirement_to_services: Dict[str, List[str]] = {}  # One req can span multiple services
        self.service_interactions: List[Dict[str, str]] = []

    def create_service(
        self,
        service_id: str,
        service_name: str,
        description: str,
        responsibilities: List[str] = None
    ) -> ServiceWorkPackage:
        """Create a new service work package."""
        service = ServiceWorkPackage(
            service_id=service_id,
            service_name=service_name,
            description=description,
            responsibilities=responsibilities or [],
            requirements=[]
        )
        self.services[service_id] = service
        return service

    def assign_requirement(self, requirement_id: str, service_id: str) -> bool:
        """Assign a requirement to a service."""
        if service_id not in self.services:
            return False

        if requirement_id not in self.services[service_id].requirements:
            self.services[service_id].requirements.append(requirement_id)

        if requirement_id not in self.requirement_to_services:
            self.requirement_to_services[requirement_id] = []
        if service_id not in self.requirement_to_services[requirement_id]:
            self.requirement_to_services[requirement_id].append(service_id)

        return True

    def add_api_endpoint(
        self,
        service_id: str,
        method: str,
        path: str,
        description: str
    ) -> bool:
        """Add an API endpoint to a service."""
        if service_id not in self.services:
            return False

        self.services[service_id].api_endpoints.append({
            "method": method,
            "path": path,
            "description": description
        })
        return True

    def add_service_interaction(
        self,
        from_service: str,
        to_service: str,
        interaction_type: str,
        description: str
    ) -> None:
        """Record an interaction between two services."""
        self.service_interactions.append({
            "from": from_service,
            "to": to_service,
            "type": interaction_type,  # sync, async, event, etc.
            "description": description
        })

        # Also add as dependency
        if from_service in self.services and to_service not in self.services[from_service].dependencies:
            self.services[from_service].dependencies.append(to_service)

    def get_services_for_requirement(self, requirement_id: str) -> List[str]:
        """Get all services involved in implementing a requirement."""
        return self.requirement_to_services.get(requirement_id, [])

    def get_service_dependencies(self, service_id: str) -> List[str]:
        """Get all services that a given service depends on."""
        if service_id not in self.services:
            return []
        return self.services[service_id].dependencies

    def generate_breakdown_from_requirements(
        self,
        requirements: List[Any],
        domain_entities: List[str] = None
    ) -> None:
        """
        Generate service breakdown from requirements.

        Args:
            requirements: List of RequirementNode objects
            domain_entities: Optional list of domain entities to derive services
        """
        # Group requirements by functional area
        functional_areas = self._identify_functional_areas(requirements)

        for i, (area_name, req_ids) in enumerate(functional_areas.items()):
            service_id = f"SVC-{i+1:03d}"
            service_name = f"{area_name} Service"

            self.create_service(
                service_id=service_id,
                service_name=service_name,
                description=f"Handles {area_name.lower()} functionality",
                responsibilities=[f"Manage {area_name.lower()} operations"]
            )

            for req_id in req_ids:
                self.assign_requirement(req_id, service_id)

    def _identify_functional_areas(
        self,
        requirements: List[Any]
    ) -> Dict[str, List[str]]:
        """Identify functional areas from requirements."""
        areas: Dict[str, List[str]] = {}

        # Common functional areas to look for
        area_keywords = {
            "User Management": ["user", "account", "profile", "registration", "login", "auth"],
            "Content": ["content", "article", "post", "media", "upload"],
            "Payment": ["payment", "billing", "invoice", "transaction", "order"],
            "Notification": ["notification", "email", "sms", "alert", "message"],
            "Search": ["search", "filter", "query", "find"],
            "Analytics": ["analytics", "report", "metric", "dashboard", "statistics"],
            "Integration": ["integration", "api", "external", "third-party", "sync"]
        }

        for req in requirements:
            title_lower = req.title.lower()
            desc_lower = req.description.lower()

            assigned = False
            for area, keywords in area_keywords.items():
                for keyword in keywords:
                    if keyword in title_lower or keyword in desc_lower:
                        if area not in areas:
                            areas[area] = []
                        areas[area].append(req.requirement_id)
                        assigned = True
                        break
                if assigned:
                    break

            if not assigned:
                if "Core" not in areas:
                    areas["Core"] = []
                areas["Core"].append(req.requirement_id)

        return areas

    def generate_sequence_diagram(self) -> str:
        """Generate a Mermaid sequence diagram for service interactions."""
        lines = ["sequenceDiagram"]

        # Add participants
        for service_id, service in self.services.items():
            lines.append(f"    participant {service_id} as {service.service_name}")

        # Add interactions
        for interaction in self.service_interactions:
            arrow = "->>" if interaction["type"] == "sync" else "-->"
            lines.append(f"    {interaction['from']}{arrow}{interaction['to']}: {interaction['description']}")

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Export breakdown as Markdown."""
        lines = ["# Service Work Breakdown Structure\n"]

        # Summary
        lines.append("## Summary\n")
        lines.append(f"- Total Services: {len(self.services)}")
        lines.append(f"- Total Interactions: {len(self.service_interactions)}\n")

        # Services
        lines.append("## Services\n")
        for service_id, service in self.services.items():
            lines.append(f"### {service.service_id}: {service.service_name}\n")
            lines.append(f"{service.description}\n")

            if service.responsibilities:
                lines.append("**Responsibilities:**")
                for resp in service.responsibilities:
                    lines.append(f"- {resp}")
                lines.append("")

            if service.requirements:
                lines.append("**Requirements:**")
                for req_id in service.requirements:
                    lines.append(f"- {req_id}")
                lines.append("")

            if service.api_endpoints:
                lines.append("**API Endpoints:**")
                for endpoint in service.api_endpoints:
                    lines.append(f"- `{endpoint['method']} {endpoint['path']}` - {endpoint['description']}")
                lines.append("")

            if service.dependencies:
                lines.append(f"**Dependencies:** {', '.join(service.dependencies)}\n")

        # Interactions
        if self.service_interactions:
            lines.append("## Service Interactions\n")
            for interaction in self.service_interactions:
                lines.append(f"- **{interaction['from']}** → **{interaction['to']}** ({interaction['type']}): {interaction['description']}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Export breakdown as dictionary."""
        return {
            "breakdown_type": "service",
            "services": {sid: s.to_dict() for sid, s in self.services.items()},
            "requirement_mapping": self.requirement_to_services,
            "interactions": self.service_interactions
        }
