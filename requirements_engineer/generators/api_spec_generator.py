"""
API Specification Generator - Derives OpenAPI 3.0 specs from Requirements.

Generates REST API endpoints, request/response schemas, and documentation
based on functional requirements.

Uses token management to chunk large requirement sets and aggregate results.
"""

import os
import json
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from datetime import datetime

# Try to import OpenAI, fall back gracefully
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Import token management
from requirements_engineer.core.token_manager import (
    TokenBudget, TokenEstimator, RequirementChunker, ResultAggregator
)

# Import LLM logger
import time
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


@dataclass_json
@dataclass
class APIParameter:
    """An API parameter (path, query, header, cookie)."""
    name: str
    location: str  # path, query, header, cookie
    type: str  # string, integer, boolean, array, object
    required: bool = True
    description: str = ""
    example: Any = None


@dataclass_json
@dataclass
class APISchema:
    """A schema for request/response body."""
    name: str
    type: str = "object"
    properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required_fields: List[str] = field(default_factory=list)
    description: str = ""


@dataclass_json
@dataclass
class APIEndpoint:
    """A single API endpoint definition."""
    path: str
    method: str  # GET, POST, PUT, DELETE, PATCH
    summary: str
    description: str = ""
    operation_id: str = ""
    tags: List[str] = field(default_factory=list)
    parameters: List[APIParameter] = field(default_factory=list)
    request_body: Optional[APISchema] = None
    response_schema: Optional[APISchema] = None
    responses: Dict[str, str] = field(default_factory=dict)
    parent_requirement_id: str = ""
    # Gap #5: Auth override for public endpoints (registration, login, etc.)
    is_public: bool = False
    # Gap #6: Content type for file uploads (multipart/form-data)
    content_type: str = "application/json"

    def to_openapi_dict(self) -> Dict[str, Any]:
        """Convert to OpenAPI format dictionary."""
        endpoint = {
            "summary": self.summary,
            "description": self.description,
            "operationId": self.operation_id,
            "tags": self.tags
        }

        # Gap #5: Override global security for public endpoints
        if self.is_public:
            endpoint["security"] = []

        if self.parameters:
            endpoint["parameters"] = [
                {
                    "name": p.name,
                    "in": p.location,
                    "required": p.required,
                    "description": p.description,
                    "schema": {"type": p.type}
                }
                for p in self.parameters
            ]

        # Gap #6: Use dynamic content type (supports multipart/form-data for uploads)
        if self.request_body:
            content_type = self.content_type
            schema_ref = {"$ref": f"#/components/schemas/{self.request_body.name}"}
            # For multipart, mark binary fields with format
            endpoint["requestBody"] = {
                "required": True,
                "content": {
                    content_type: {
                        "schema": schema_ref
                    }
                }
            }

        # Build responses
        responses = {}
        for status, desc in self.responses.items():
            responses[status] = {"description": desc}
            # Gap #2: Apply response schema for both 200 and 201 (POST create)
            if status in ("200", "201") and self.response_schema:
                responses[status]["content"] = {
                    "application/json": {
                        "schema": {
                            "$ref": f"#/components/schemas/{self.response_schema.name}"
                        }
                    }
                }
            # Gap #1: Add error response schema reference for 4xx/5xx
            elif status.startswith(("4", "5")):
                responses[status]["content"] = {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/ErrorResponse"
                        }
                    }
                }
        endpoint["responses"] = responses or {"200": {"description": "Success"}}

        return endpoint


class APISpecGenerator:
    """
    Generates OpenAPI 3.0 specifications from Requirements.

    The generator:
    1. Analyzes functional requirements to identify API endpoints
    2. Derives request/response schemas from requirement context
    3. Groups endpoints by resource/tag
    4. Produces valid OpenAPI 3.0 YAML
    """

    ENDPOINT_PROMPT = """You are a Software Architect expert in REST API design.

Given this requirement:
- ID: {req_id}
- Title: {title}
- Description: {description}
- Type: {type}

Technical Constraints:
{constraints}

Derive the REST API endpoint(s) needed to implement this requirement.

Return JSON format:
{{
    "endpoints": [
        {{
            "path": "/api/v1/resource",
            "method": "POST",
            "summary": "Short description",
            "description": "Detailed description",
            "operation_id": "createResource",
            "tags": ["ResourceTag"],
            "is_public": false,
            "content_type": "application/json",
            "parameters": [
                {{
                    "name": "id",
                    "location": "path",
                    "type": "string",
                    "required": true,
                    "description": "Resource ID"
                }}
            ],
            "request_body": {{
                "name": "CreateResourceRequest",
                "properties": {{
                    "field1": {{"type": "string", "description": "Field description"}}
                }},
                "required_fields": ["field1"]
            }},
            "response_body": {{
                "name": "ResourceResponse",
                "properties": {{
                    "id": {{"type": "string", "description": "Resource ID"}},
                    "field1": {{"type": "string", "description": "Field description"}}
                }}
            }},
            "responses": {{
                "201": "Created",
                "400": "Bad Request - Invalid input",
                "401": "Unauthorized - Missing or invalid token",
                "409": "Conflict - Resource already exists"
            }}
        }}
    ]
}}

Guidelines:
- Use RESTful conventions (GET for read, POST for create, PUT for update, DELETE for delete)
- Use plural nouns for resources (/users, /products, /orders)
- Include appropriate HTTP status codes with descriptive error messages
- POST endpoints that create resources MUST return 201, not 200
- GET endpoints that return lists MUST include pagination parameters (page, pageSize)
- Error responses (4xx, 5xx) MUST have specific descriptions (not just "Bad Request")
- Use camelCase for operationId
- EVERY endpoint MUST have a "response_body" with the expected response schema
- Set "is_public": true for registration, login, password-reset, health-check, and other unauthenticated endpoints
- For file/image/media upload endpoints, set "content_type": "multipart/form-data" and use type "string" with format "binary" for file fields

Return ONLY valid JSON, no other text."""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        api_version: str = "1.0.0",
        api_title: str = "Generated API",
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the API Spec Generator.

        Args:
            model_name: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            api_version: Version for the generated API spec
            api_title: Title for the generated API spec
            config: Configuration dict with generators.api_spec section
        """
        # Load from config if available
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("api_spec", {})

        self.model_name = model_name or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.client = None
        self.api_version = api_version
        self.api_title = api_title

        # Storage
        self.endpoints: List[APIEndpoint] = []
        self.schemas: Dict[str, APISchema] = {}

    async def initialize(self):
        """Initialize the OpenAI client."""
        if not HAS_OPENAI:
            raise ImportError("openai package required. Install with: pip install openai")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM and return the response."""
        if not self.client:
            await self.initialize()

        start_time = time.time()
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are an expert API architect. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        latency_ms = int((time.time() - start_time) * 1000)

        response_text = response.choices[0].message.content.strip()

        # Log the LLM call
        log_llm_call(
            component="api_spec_generator",
            model=self.model_name,
            response=response,
            latency_ms=latency_ms,
            system_message="You are an expert API architect. Always respond with valid JSON only.",
            user_message=prompt,
            response_text=response_text,
        )

        return response_text

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response with robust error handling."""
        errors = []

        # Try to parse directly
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            errors.append(f"Direct parse: {e}")

        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                errors.append(f"Code block parse: {e}")

        # Try to find JSON object (greedy match for last closing brace)
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                errors.append(f"Object parse: {e}")
                # Try to fix truncated JSON by closing open brackets
                try:
                    fixed = self._fix_truncated_json(json_str)
                    return json.loads(fixed)
                except json.JSONDecodeError as e2:
                    errors.append(f"Fixed parse: {e2}")

        # Return empty result with warning instead of raising exception
        print(f"    [WARN] Could not parse JSON response. Returning empty result.")
        print(f"    Errors: {'; '.join(errors)}")
        return {"endpoints": []}

    def _fix_truncated_json(self, text: str) -> str:
        """Try to fix truncated JSON by adding missing closing brackets."""
        # Count open/close brackets
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')

        # Add missing closing brackets
        fixed = text
        for _ in range(open_brackets):
            fixed += ']'
        for _ in range(open_braces):
            fixed += '}'

        return fixed

    async def derive_endpoints(
        self,
        requirement,
        constraints: List[str] = None
    ) -> List[APIEndpoint]:
        """
        Derive API endpoints from a requirement.

        Args:
            requirement: RequirementNode instance
            constraints: List of technical constraints

        Returns:
            List of APIEndpoint instances
        """
        constraints_text = "\n".join(f"- {c}" for c in (constraints or [])) or "None specified"

        prompt = self.ENDPOINT_PROMPT.format(
            req_id=requirement.requirement_id,
            title=requirement.title,
            description=requirement.description,
            type=requirement.type,
            constraints=constraints_text
        )

        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        endpoints = []
        for ep_data in data.get("endpoints", []):
            # Parse parameters
            parameters = []
            for p in ep_data.get("parameters", []):
                parameters.append(APIParameter(
                    name=p.get("name", ""),
                    location=p.get("location", "query"),
                    type=p.get("type", "string"),
                    required=p.get("required", False),
                    description=p.get("description", "")
                ))

            # Parse request body
            request_body = None
            if rb := ep_data.get("request_body"):
                request_body = APISchema(
                    name=rb.get("name", "RequestBody"),
                    properties=rb.get("properties", {}),
                    required_fields=rb.get("required_fields", [])
                )
                self.schemas[request_body.name] = request_body

            # Parse response body
            response_schema = None
            if rs := ep_data.get("response_body"):
                response_schema = APISchema(
                    name=rs.get("name", "ResponseBody"),
                    properties=rs.get("properties", {}),
                    required_fields=rs.get("required_fields", [])
                )
                self.schemas[response_schema.name] = response_schema

            endpoint = APIEndpoint(
                path=ep_data.get("path", "/api/unknown"),
                method=ep_data.get("method", "GET").upper(),
                summary=ep_data.get("summary", requirement.title),
                description=ep_data.get("description", requirement.description),
                operation_id=ep_data.get("operation_id", ""),
                tags=ep_data.get("tags", []),
                parameters=parameters,
                request_body=request_body,
                response_schema=response_schema,
                responses=ep_data.get("responses", {"200": "Success"}),
                parent_requirement_id=requirement.requirement_id,
                # Gap #5: Parse public endpoint flag
                is_public=ep_data.get("is_public", False),
                # Gap #6: Parse content type for file uploads
                content_type=ep_data.get("content_type", "application/json"),
            )

            self.endpoints.append(endpoint)
            endpoints.append(endpoint)

        return endpoints

    async def generate_openapi_spec(
        self,
        requirements: List,
        constraints: List[str] = None,
        server_url: str = "https://api.example.com",
        max_context_tokens: int = 100000
    ) -> str:
        """
        Generate complete OpenAPI 3.0 specification.

        Uses token-aware chunking to process large requirement sets.

        Args:
            requirements: List of RequirementNode instances
            constraints: List of technical constraints
            server_url: Base server URL for the API
            max_context_tokens: Maximum tokens per LLM call

        Returns:
            OpenAPI 3.0 specification as YAML string
        """
        # Filter to functional requirements only
        functional_reqs = [r for r in requirements if r.type == "functional"]

        if not functional_reqs:
            print("  [WARN] No functional requirements found")
            return self._build_empty_spec(server_url)

        # Set up chunking
        budget = TokenBudget(max_context=max_context_tokens)
        chunker = RequirementChunker(budget)

        # Estimate prompt template tokens (the ENDPOINT_PROMPT without variables)
        template_tokens = TokenEstimator.estimate_tokens(self.ENDPOINT_PROMPT)

        # Get batch info
        batch_info = chunker.get_batch_info(functional_reqs)
        print(f"  Processing {batch_info['total_requirements']} functional requirements in {batch_info['num_batches']} batch(es)")

        # Process each batch
        batch_num = 0
        for batch in chunker.chunk_requirements(functional_reqs, template_tokens):
            batch_num += 1
            print(f"  [Batch {batch_num}/{batch_info['num_batches']}] Processing {len(batch)} requirements...")

            for req in batch:
                await self.derive_endpoints(req, constraints)
                print(f"    Derived endpoints for {req.requirement_id}: {req.title}")

        # Deduplicate endpoints: merge same method+path, combine requirement refs
        total_before = len(self.endpoints)
        seen = {}  # key: (method, path) -> endpoint
        deduped = []
        for ep in self.endpoints:
            key = (ep.method.upper(), ep.path)
            if key in seen:
                existing = seen[key]
                if ep.parent_requirement_id and ep.parent_requirement_id not in (existing.tags or []):
                    if existing.tags is None:
                        existing.tags = []
                    existing.tags.append(ep.parent_requirement_id)
                existing_param_names = {p.name for p in existing.parameters}
                for p in ep.parameters:
                    if p.name not in existing_param_names:
                        existing.parameters.append(p)
            else:
                seen[key] = ep
                deduped.append(ep)
        self.endpoints = deduped
        if total_before != len(self.endpoints):
            print(f"  Deduplicated: {len(self.endpoints)} unique endpoints (from {total_before} total)")

        # Build OpenAPI structure
        openapi = {
            "openapi": "3.0.3",
            "info": {
                "title": self.api_title,
                "version": self.api_version,
                "description": f"API specification generated from requirements.\n\nGenerated: {datetime.now().isoformat()}"
            },
            "servers": [
                {"url": server_url, "description": "Production server"}
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": self._build_security_schemes()
            },
            "security": [{"bearerAuth": []}]
        }

        # Add paths
        for endpoint in self.endpoints:
            if endpoint.path not in openapi["paths"]:
                openapi["paths"][endpoint.path] = {}
            openapi["paths"][endpoint.path][endpoint.method.lower()] = endpoint.to_openapi_dict()

        # Add schemas
        for schema_name, schema in self.schemas.items():
            openapi["components"]["schemas"][schema_name] = {
                "type": schema.type,
                "properties": schema.properties,
                "required": schema.required_fields if schema.required_fields else None
            }
            # Remove None values
            if not openapi["components"]["schemas"][schema_name]["required"]:
                del openapi["components"]["schemas"][schema_name]["required"]

        # Gap #1: Add ErrorResponse schema (referenced by all 4xx/5xx responses)
        openapi["components"]["schemas"]["ErrorResponse"] = {
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Machine-readable error code"},
                "message": {"type": "string", "description": "Human-readable error message"},
                "details": {
                    "type": "array",
                    "description": "Validation error details",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "message": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["error", "message"]
        }

        # Gap #16: Add PaginationMeta schema
        openapi["components"]["schemas"]["PaginationMeta"] = {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Current page number"},
                "pageSize": {"type": "integer", "description": "Items per page"},
                "totalItems": {"type": "integer", "description": "Total number of items"},
                "totalPages": {"type": "integer", "description": "Total number of pages"}
            },
            "required": ["page", "pageSize", "totalItems", "totalPages"]
        }

        # Gap #16: Wrap GET list endpoints with pagination envelope
        for path, methods in openapi["paths"].items():
            for method_name, method_spec in methods.items():
                if method_name != "get":
                    continue
                # Detect list endpoints: have page/pageSize params or path has no {id}
                params = method_spec.get("parameters", [])
                has_pagination_param = any(
                    p.get("name") in ("page", "pageSize", "limit", "offset")
                    for p in params
                )
                if not has_pagination_param:
                    continue
                # Wrap the 200 response schema with pagination envelope
                resp_200 = method_spec.get("responses", {}).get("200", {})
                content = resp_200.get("content", {}).get("application/json", {})
                inner_schema = content.get("schema")
                if inner_schema:
                    wrapper_name = f"Paginated{inner_schema.get('$ref', '').split('/')[-1]}"
                    openapi["components"]["schemas"][wrapper_name] = {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "items": inner_schema
                            },
                            "pagination": {
                                "$ref": "#/components/schemas/PaginationMeta"
                            }
                        },
                        "required": ["data", "pagination"]
                    }
                    resp_200["content"]["application/json"]["schema"] = {
                        "$ref": f"#/components/schemas/{wrapper_name}"
                    }

        return yaml.dump(openapi, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _build_security_schemes(self) -> dict:
        """Build security schemes for OpenAPI spec (JWT + API Key + OAuth2)."""
        schemes = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT Bearer token authentication. Include in Authorization header."
            },
            "apiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for service-to-service authentication."
            },
            "oauth2Auth": {
                "type": "oauth2",
                "description": "OAuth 2.0 authorization code flow for user-facing applications.",
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": "https://auth.example.com/authorize",
                        "tokenUrl": "https://auth.example.com/token",
                        "refreshUrl": "https://auth.example.com/refresh",
                        "scopes": {
                            "read": "Read access to resources",
                            "write": "Write access to resources",
                            "admin": "Administrative access"
                        }
                    }
                }
            }
        }
        return schemes

    def _build_empty_spec(self, server_url: str = "https://api.example.com") -> str:
        """Build an empty OpenAPI spec when no requirements are processed."""
        openapi = {
            "openapi": "3.0.3",
            "info": {
                "title": self.api_title,
                "version": self.api_version,
                "description": f"API specification (no endpoints generated).\n\nGenerated: {datetime.now().isoformat()}"
            },
            "servers": [
                {"url": server_url, "description": "Production server"}
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": self._build_security_schemes()
            },
            "security": [{"bearerAuth": []}]
        }
        return yaml.dump(openapi, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def to_markdown(self) -> str:
        """Export API documentation as markdown."""
        md = f"# {self.api_title} - API Documentation\n\n"
        md += f"**Version:** {self.api_version}\n"
        md += f"**Generated:** {datetime.now().isoformat()}\n\n"

        # Group by tags
        by_tag: Dict[str, List[APIEndpoint]] = {}
        for ep in self.endpoints:
            for tag in ep.tags or ["Untagged"]:
                if tag not in by_tag:
                    by_tag[tag] = []
                by_tag[tag].append(ep)

        md += "## Endpoints\n\n"

        for tag, endpoints in sorted(by_tag.items()):
            md += f"### {tag}\n\n"
            for ep in endpoints:
                md += f"#### `{ep.method}` {ep.path}\n\n"
                md += f"**{ep.summary}**\n\n"
                if ep.description:
                    md += f"{ep.description}\n\n"
                if ep.parent_requirement_id:
                    md += f"*Requirement:* {ep.parent_requirement_id}\n\n"

                if ep.parameters:
                    md += "**Parameters:**\n\n"
                    md += "| Name | In | Type | Required | Description |\n"
                    md += "|------|-----|------|----------|-------------|\n"
                    for p in ep.parameters:
                        md += f"| {p.name} | {p.location} | {p.type} | {p.required} | {p.description} |\n"
                    md += "\n"

                if ep.request_body:
                    md += f"**Request Body:** `{ep.request_body.name}`\n\n"

                if ep.responses:
                    md += "**Responses:**\n\n"
                    for status, desc in ep.responses.items():
                        md += f"- `{status}`: {desc}\n"
                    md += "\n"

                md += "---\n\n"

        # Schemas
        if self.schemas:
            md += "## Schemas\n\n"
            for name, schema in sorted(self.schemas.items()):
                md += f"### {name}\n\n"
                if schema.properties:
                    md += "| Property | Type | Description |\n"
                    md += "|----------|------|-------------|\n"
                    for prop, details in schema.properties.items():
                        ptype = details.get("type", "string")
                        pdesc = details.get("description", "")
                        md += f"| {prop} | {ptype} | {pdesc} |\n"
                    md += "\n"

        return md


# Test function
async def test_api_spec_generator():
    """Test the APISpecGenerator with sample data."""
    from requirements_engineer.core.re_journal import RequirementNode

    # Create sample requirements
    requirements = [
        RequirementNode(
            requirement_id="REQ-001",
            title="User Registration",
            description="Users should be able to register with email and password",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-002",
            title="User Login",
            description="Users should be able to login with their credentials and receive a JWT token",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-003",
            title="Product Listing",
            description="Users should be able to view a list of products with pagination and filtering",
            type="functional",
            priority="should"
        )
    ]

    constraints = [
        "REST API architecture",
        "JWT authentication",
        "JSON request/response format"
    ]

    generator = APISpecGenerator(
        api_title="E-Commerce API",
        api_version="1.0.0"
    )
    await generator.initialize()

    print("=== Generating OpenAPI Specification ===\n")
    spec = await generator.generate_openapi_spec(requirements, constraints)

    print("\n=== OpenAPI YAML ===\n")
    print(spec)

    print("\n=== Markdown Documentation ===\n")
    print(generator.to_markdown())

    return generator


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api_spec_generator())
