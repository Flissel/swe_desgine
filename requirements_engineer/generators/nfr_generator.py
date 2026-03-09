"""
NFR Generator - Derives Non-Functional Requirements from functional requirements.

Generates NFRs across 12 categories:
Performance, Scalability, Availability, Security, Privacy, Reliability,
Maintainability, Observability, Accessibility, Interoperability, Capacity, Disaster Recovery
"""

import json
import os
import re
import time
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI

from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call

# Import RequirementNode for type hint
try:
    from requirements_engineer.core.re_journal import RequirementNode
except ImportError:
    RequirementNode = Any


NFR_CATEGORIES = [
    "performance",
    "scalability",
    "availability",
    "security",
    "privacy",
    "reliability",
    "maintainability",
    "observability",
    "accessibility",
    "interoperability",
    "capacity",
    "disaster_recovery",
]

NFR_PROMPT = """You are a Senior Non-Functional Requirements Engineer.

Given these functional requirements for a {domain} system called "{project_name}":

## Functional Requirements:
{requirements_text}

Generate Non-Functional Requirements (NFRs) for the following categories:
{categories_text}

Return JSON format:
{{
    "nfr_requirements": [
        {{
            "title": "Short NFR title",
            "description": "Detailed, measurable description with specific targets",
            "category": "performance|scalability|availability|security|privacy|reliability|maintainability|observability|accessibility|interoperability|capacity|disaster_recovery",
            "priority": "must|should|could",
            "acceptance_criteria": "Measurable criteria (e.g., p99 latency < 200ms, 99.9% uptime)"
        }}
    ]
}}

Guidelines:
- Generate 2-3 NFRs per category (24-36 total)
- Each NFR MUST have measurable, specific acceptance criteria (no vague statements)
- Performance: response times (p50, p95, p99), throughput (requests/sec), page load time
- Scalability: max concurrent users, horizontal scaling triggers, data growth rate
- Availability: uptime SLA (99.9%, 99.99%), planned maintenance window, failover time
- Security: encryption standards (AES-256, TLS 1.3), auth requirements, pen test frequency
- Privacy: GDPR/CCPA compliance, data retention, anonymization requirements
- Reliability: MTBF, MTTR, error budget, fault tolerance
- Maintainability: code coverage, deployment frequency, max build time, tech debt ratio
- Observability: log retention, metric granularity, alert response time, dashboard coverage
- Accessibility: WCAG level (AA/AAA), screen reader support, keyboard navigation
- Interoperability: API standards (REST/GraphQL), data formats (JSON/Protocol Buffers), SSO
- Capacity: max storage per user, max message size, max file upload size, retention policy
- Disaster Recovery: RPO, RTO, backup frequency, geo-redundancy

Return ONLY valid JSON."""


class NFRGenerator:
    """Generates Non-Functional Requirements from functional requirements."""

    def __init__(
        self,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("nfr", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.categories = gen_config.get("categories", NFR_CATEGORIES)

        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY"),
        )

    async def generate(
        self,
        requirements: List[Any],
        domain: str = "",
        project_name: str = "",
    ) -> List["RequirementNode"]:
        """Generate NFR RequirementNode objects from functional requirements.

        Args:
            requirements: List of existing functional RequirementNode objects
            domain: Project domain (e.g., "messaging", "e-commerce")
            project_name: Project name

        Returns:
            List of RequirementNode objects with type="non_functional"
        """
        from requirements_engineer.core.re_journal import RequirementNode

        # Build requirements text
        req_lines = []
        for req in requirements[:30]:
            if hasattr(req, "title"):
                req_lines.append(f"- {req.requirement_id}: {req.title} — {getattr(req, 'description', '')[:100]}")
            elif isinstance(req, dict):
                req_lines.append(f"- {req.get('id', 'REQ')}: {req.get('title', '')} — {req.get('description', '')[:100]}")
        req_text = "\n".join(req_lines) if req_lines else "No requirements provided"

        # Build categories text
        cat_text = ", ".join(self.categories)

        prompt = NFR_PROMPT.format(
            domain=domain or "software",
            project_name=project_name or "Project",
            requirements_text=req_text,
            categories_text=cat_text,
        )

        try:
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Non-Functional Requirements expert. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            content = response.choices[0].message.content.strip()

            # Log the LLM call
            log_llm_call(
                component="nfr_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                system_message="You are a Non-Functional Requirements expert. Respond with valid JSON only.",
                user_message=prompt,
                response_text=content,
            )

            # Parse JSON
            data = self._extract_json(content)
            nfr_list = data.get("nfr_requirements", [])

            # Find max existing requirement number
            max_num = 0
            for req in requirements:
                rid = getattr(req, "requirement_id", "") if hasattr(req, "requirement_id") else req.get("requirement_id", "")
                match = re.search(r"(\d+)", rid)
                if match:
                    max_num = max(max_num, int(match.group(1)))

            # Create RequirementNode objects
            nodes = []
            for nfr_data in nfr_list:
                max_num += 1
                req_id = f"NFR-{max_num:03d}"
                category = nfr_data.get("category", "performance")

                node = RequirementNode(
                    id=f"node-{req_id}",
                    requirement_id=req_id,
                    title=nfr_data.get("title", "Untitled NFR"),
                    description=nfr_data.get("description", ""),
                    type="non_functional",
                    priority=nfr_data.get("priority", "should"),
                    source="nfr_generator",
                    validation_status="draft",
                )
                # Store category in the node's metadata if possible
                if hasattr(node, "nfr_category"):
                    node.nfr_category = category
                # Store acceptance criteria
                ac_text = nfr_data.get("acceptance_criteria", "")
                if ac_text and hasattr(node, "acceptance_criteria"):
                    node.acceptance_criteria = ac_text

                nodes.append(node)

            return nodes

        except Exception as e:
            print(f"    [ERROR] NFR generation failed: {e}")
            return []

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown fenced blocks
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {"nfr_requirements": []}
