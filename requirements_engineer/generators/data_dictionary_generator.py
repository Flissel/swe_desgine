"""
Data Dictionary Generator - Extracts domain entities and relationships.

Generates a comprehensive data dictionary including:
- Entities and their attributes
- Data types and constraints
- Relationships between entities
- Glossary of domain terms

Uses token management to chunk large requirement sets and aggregate results.
"""

import os
import json
import re
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
    TokenBudget, TokenEstimator, RequirementChunker, ResultAggregator, ContextSlicer
)

# Import LLM logger
import time
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


@dataclass_json
@dataclass
class Attribute:
    """An attribute of an entity."""
    name: str
    data_type: str  # string, integer, decimal, boolean, date, datetime, enum, etc.
    description: str = ""
    required: bool = True
    unique: bool = False
    default_value: Optional[str] = None
    constraints: List[str] = field(default_factory=list)  # e.g., ["min: 0", "max: 100"]
    example: Optional[str] = None
    # Gap #8: Field length for string types (e.g., varchar(255))
    max_length: Optional[int] = None
    # Gap #7: Enum values for enum-type fields
    enum_values: List[str] = field(default_factory=list)
    # Gap #9: DB index flag
    is_indexed: bool = False
    # Gap #4: Foreign key support
    is_foreign_key: bool = False
    foreign_key_target: str = ""  # e.g. "User.id"


@dataclass_json
@dataclass
class Relationship:
    """A relationship between entities."""
    name: str
    source_entity: str
    target_entity: str
    cardinality: str  # 1:1, 1:N, N:1, N:M
    description: str = ""
    required: bool = True
    # Gap #3: Junction/pivot table for N:M relationships
    junction_table: Optional[str] = None
    source_fk: str = ""  # FK column name in junction table
    target_fk: str = ""  # FK column name in junction table


@dataclass_json
@dataclass
class Entity:
    """A domain entity with attributes and relationships."""
    name: str
    description: str
    attributes: List[Attribute] = field(default_factory=list)
    primary_key: str = "id"
    source_requirements: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        md = f"### {self.name}\n\n"
        md += f"{self.description}\n\n"

        if self.source_requirements:
            md += f"*Source Requirements:* {', '.join(self.source_requirements)}\n\n"

        md += "| Attribute | Type | MaxLen | Required | FK Target | Indexed | Enum Values | Description |\n"
        md += "|-----------|------|--------|----------|-----------|---------|-------------|-------------|\n"
        for attr in self.attributes:
            req = "Yes" if attr.required else "No"
            maxlen = str(attr.max_length) if attr.max_length else "-"
            fk = attr.foreign_key_target if attr.is_foreign_key else "-"
            idx = "Yes" if attr.is_indexed else "-"
            enums = ", ".join(attr.enum_values) if attr.enum_values else "-"
            md += f"| {attr.name} | {attr.data_type} | {maxlen} | {req} | {fk} | {idx} | {enums} | {attr.description} |\n"
        md += "\n"

        return md

    def to_er_mermaid(self) -> str:
        """Generate Mermaid ER diagram fragment with PK/FK markers."""
        lines = [f"    {self.name} {{"]
        for attr in self.attributes:
            pk = "PK" if attr.name == self.primary_key else ""
            fk = "FK" if attr.is_foreign_key else ""
            marker = pk or fk
            lines.append(f"        {attr.data_type} {attr.name} {marker}".rstrip())
        lines.append("    }")
        return "\n".join(lines)


@dataclass_json
@dataclass
class GlossaryTerm:
    """A domain term definition."""
    term: str
    definition: str
    synonyms: List[str] = field(default_factory=list)
    related_terms: List[str] = field(default_factory=list)


@dataclass_json
@dataclass
class DataDictionary:
    """Complete data dictionary with entities, relationships, and glossary."""
    title: str
    entities: Dict[str, Entity] = field(default_factory=dict)
    relationships: List[Relationship] = field(default_factory=list)
    glossary: Dict[str, GlossaryTerm] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        """Convert entire dictionary to markdown."""
        md = f"# Data Dictionary: {self.title}\n\n"
        md += f"**Generated:** {self.created_at}\n\n"

        md += "## Summary\n\n"
        md += f"- Entities: {len(self.entities)}\n"
        md += f"- Relationships: {len(self.relationships)}\n"
        md += f"- Glossary Terms: {len(self.glossary)}\n\n"

        # Entities
        md += "---\n\n## Entities\n\n"
        for entity in sorted(self.entities.values(), key=lambda x: x.name):
            md += entity.to_markdown()

        # Relationships
        if self.relationships:
            md += "---\n\n## Relationships\n\n"
            md += "| Relationship | Source | Target | Cardinality | Description |\n"
            md += "|--------------|--------|--------|-------------|-------------|\n"
            for rel in self.relationships:
                md += f"| {rel.name} | {rel.source_entity} | {rel.target_entity} | {rel.cardinality} | {rel.description} |\n"
            md += "\n"

        # Glossary
        if self.glossary:
            md += "---\n\n## Glossary\n\n"
            for term in sorted(self.glossary.values(), key=lambda x: x.term):
                md += f"### {term.term}\n\n"
                md += f"{term.definition}\n\n"
                if term.synonyms:
                    md += f"*Synonyms:* {', '.join(term.synonyms)}\n\n"

        return md

    def to_er_diagram(self) -> str:
        """Generate complete Mermaid ER diagram with junction tables for N:M."""
        lines = ["erDiagram"]

        # Add entities
        for entity in self.entities.values():
            lines.append(entity.to_er_mermaid())

        # Add relationships
        cardinality_map = {
            "1:1": "||--||",
            "1:N": "||--o{",
            "N:1": "}o--||",
            "N:M": "}o--o{"
        }
        for rel in self.relationships:
            # Gap #3: Generate junction table entity for N:M with named FKs
            if rel.cardinality == "N:M" and rel.junction_table:
                src_fk = rel.source_fk or f"{rel.source_entity.lower()}_id"
                tgt_fk = rel.target_fk or f"{rel.target_entity.lower()}_id"
                lines.append(f"    {rel.junction_table} {{")
                lines.append(f"        uuid {src_fk} FK")
                lines.append(f"        uuid {tgt_fk} FK")
                lines.append(f"    }}")
                lines.append(f"    {rel.source_entity} ||--o{{ {rel.junction_table} : \"\"")
                lines.append(f"    {rel.junction_table} }}o--|| {rel.target_entity} : \"\"")
            else:
                card = cardinality_map.get(rel.cardinality, "||--||")
                lines.append(f"    {rel.source_entity} {card} {rel.target_entity} : \"{rel.name}\"")

        return "\n".join(lines)

    def to_sql(self) -> str:
        """Generate PostgreSQL DDL from the data dictionary.

        Produces CREATE TYPE, CREATE TABLE, FOREIGN KEY, CREATE INDEX statements
        with proper dependency ordering (topological sort).
        """
        sql_parts = []
        sql_parts.append(f"-- PostgreSQL Schema: {self.title}")
        sql_parts.append(f"-- Generated: {datetime.now().isoformat()}")
        sql_parts.append(f"-- Entities: {len(self.entities)}, Relationships: {len(self.relationships)}")
        sql_parts.append("")

        # Type mapping
        def _sql_type(attr: Attribute) -> str:
            t = attr.data_type.lower()
            if t == "enum" and attr.enum_values:
                return f"{_enum_type_name(attr.name)}"
            type_map = {
                "string": f"VARCHAR({attr.max_length or 255})",
                "varchar": f"VARCHAR({attr.max_length or 255})",
                "text": "TEXT",
                "integer": "INTEGER",
                "int": "INTEGER",
                "bigint": "BIGINT",
                "decimal": "DECIMAL(10, 2)",
                "float": "DOUBLE PRECISION",
                "boolean": "BOOLEAN",
                "bool": "BOOLEAN",
                "date": "DATE",
                "datetime": "TIMESTAMP WITH TIME ZONE",
                "timestamp": "TIMESTAMP WITH TIME ZONE",
                "uuid": "UUID",
                "json": "JSONB",
                "jsonb": "JSONB",
                "bytea": "BYTEA",
            }
            return type_map.get(t, f"VARCHAR({attr.max_length or 255})")

        def _table_name(entity_name: str) -> str:
            s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', entity_name)
            s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
            return s2.lower().replace(' ', '_').replace('-', '_')

        def _enum_type_name(attr_name: str) -> str:
            return f"{attr_name}_type"

        # Collect all enum types
        enum_types = {}  # {type_name: [values]}
        for entity in self.entities.values():
            for attr in entity.attributes:
                if attr.data_type.lower() == "enum" and attr.enum_values:
                    tn = _enum_type_name(attr.name)
                    if tn not in enum_types:
                        enum_types[tn] = attr.enum_values

        # CREATE TYPE for enums
        if enum_types:
            sql_parts.append("-- ============================================")
            sql_parts.append("-- ENUM TYPES")
            sql_parts.append("-- ============================================")
            sql_parts.append("")
            for type_name, values in sorted(enum_types.items()):
                vals = ", ".join(f"'{v}'" for v in values)
                sql_parts.append(f"CREATE TYPE {type_name} AS ENUM ({vals});")
            sql_parts.append("")

        # Topological sort: entities ordered so referenced tables come first
        entity_names = list(self.entities.keys())
        # Build dependency graph: entity -> set of entities it depends on (via FK)
        deps = {name: set() for name in entity_names}
        for entity in self.entities.values():
            for attr in entity.attributes:
                if attr.is_foreign_key and attr.foreign_key_target:
                    target_entity = attr.foreign_key_target.split(".")[0]
                    if target_entity in deps and target_entity != entity.name:
                        deps[entity.name].add(target_entity)

        # Kahn's algorithm
        sorted_entities = []
        in_degree = {name: len(d) for name, d in deps.items()}
        queue = [name for name, deg in in_degree.items() if deg == 0]
        while queue:
            node = queue.pop(0)
            sorted_entities.append(node)
            for name, d in deps.items():
                if node in d:
                    d.remove(node)
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)
        # Add any remaining (circular deps) at the end
        for name in entity_names:
            if name not in sorted_entities:
                sorted_entities.append(name)

        # CREATE TABLE statements
        sql_parts.append("-- ============================================")
        sql_parts.append("-- TABLES")
        sql_parts.append("-- ============================================")
        sql_parts.append("")

        fk_constraints = []  # Deferred FK constraints
        index_statements = []

        for entity_name in sorted_entities:
            entity = self.entities[entity_name]
            tbl = _table_name(entity_name)
            sql_parts.append(f"-- {entity.description}")
            sql_parts.append(f"CREATE TABLE {tbl} (")

            col_lines = []
            for attr in entity.attributes:
                col = f"    {attr.name} {_sql_type(attr)}"
                if attr.name == entity.primary_key:
                    col += " PRIMARY KEY"
                    if attr.data_type.lower() == "uuid":
                        col += " DEFAULT gen_random_uuid()"
                else:
                    if not attr.required:
                        pass  # nullable by default
                    else:
                        col += " NOT NULL"
                    if attr.unique:
                        col += " UNIQUE"
                    if attr.default_value and attr.name != entity.primary_key:
                        col += f" DEFAULT {attr.default_value}"

                col_lines.append(col)

                # Collect FK constraints
                if attr.is_foreign_key and attr.foreign_key_target:
                    parts = attr.foreign_key_target.split(".")
                    ref_table = _table_name(parts[0])
                    ref_col = parts[1] if len(parts) > 1 else "id"
                    on_delete = "CASCADE" if attr.required else "SET NULL"
                    fk_constraints.append(
                        f"ALTER TABLE {tbl} ADD CONSTRAINT fk_{tbl}_{attr.name} "
                        f"FOREIGN KEY ({attr.name}) REFERENCES {ref_table}({ref_col}) ON DELETE {on_delete};"
                    )

                # Collect index statements
                if attr.is_indexed and attr.name != entity.primary_key:
                    index_statements.append(
                        f"CREATE INDEX idx_{tbl}_{attr.name} ON {tbl}({attr.name});"
                    )

            sql_parts.append(",\n".join(col_lines))
            sql_parts.append(");")
            sql_parts.append("")

        # Junction tables for N:M relationships
        junction_tables = []
        for rel in self.relationships:
            if rel.cardinality == "N:M" and rel.junction_table:
                jt = _table_name(rel.junction_table)
                src_fk = rel.source_fk or f"{_table_name(rel.source_entity)}_id"
                tgt_fk = rel.target_fk or f"{_table_name(rel.target_entity)}_id"
                src_tbl = _table_name(rel.source_entity)
                tgt_tbl = _table_name(rel.target_entity)
                junction_tables.append(f"-- Junction table: {rel.source_entity} <-> {rel.target_entity}")
                junction_tables.append(f"CREATE TABLE {jt} (")
                junction_tables.append(f"    {src_fk} UUID NOT NULL REFERENCES {src_tbl}(id) ON DELETE CASCADE,")
                junction_tables.append(f"    {tgt_fk} UUID NOT NULL REFERENCES {tgt_tbl}(id) ON DELETE CASCADE,")
                junction_tables.append(f"    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),")
                junction_tables.append(f"    PRIMARY KEY ({src_fk}, {tgt_fk})")
                junction_tables.append(f");")
                junction_tables.append("")

        if junction_tables:
            sql_parts.append("-- ============================================")
            sql_parts.append("-- JUNCTION TABLES")
            sql_parts.append("-- ============================================")
            sql_parts.append("")
            sql_parts.extend(junction_tables)

        # Foreign key constraints (deferred to avoid ordering issues)
        if fk_constraints:
            sql_parts.append("-- ============================================")
            sql_parts.append("-- FOREIGN KEY CONSTRAINTS")
            sql_parts.append("-- ============================================")
            sql_parts.append("")
            for fk in fk_constraints:
                sql_parts.append(fk)
            sql_parts.append("")

        # Indexes
        if index_statements:
            sql_parts.append("-- ============================================")
            sql_parts.append("-- INDEXES")
            sql_parts.append("-- ============================================")
            sql_parts.append("")
            for idx in index_statements:
                sql_parts.append(idx)
            sql_parts.append("")

        return "\n".join(sql_parts)


class DataDictionaryGenerator:
    """
    Generates Data Dictionary from Requirements using LLM.

    The generator:
    1. Analyzes requirements to identify domain entities
    2. Extracts attributes and their data types
    3. Identifies relationships between entities
    4. Builds a glossary of domain terms
    """

    ENTITY_PROMPT = """Extract domain entities from these requirements:

{requirements}

Domain: {domain}

Return COMPACT JSON:
{{
    "entities": [
        {{
            "name": "EntityName",
            "description": "Brief description",
            "attributes": [
                {{
                    "name": "attr_name",
                    "data_type": "string",
                    "description": "Brief purpose of this attribute",
                    "required": true,
                    "max_length": 255,
                    "enum_values": [],
                    "is_indexed": false,
                    "is_foreign_key": false,
                    "foreign_key_target": ""
                }}
            ],
            "source_requirements": ["REQ-001"]
        }}
    ],
    "relationships": [
        {{
            "source_entity": "A",
            "target_entity": "B",
            "cardinality": "1:N",
            "name": "has",
            "junction_table": null,
            "source_fk": "",
            "target_fk": ""
        }}
    ],
    "glossary": [
        {{"term": "Term", "definition": "Brief definition"}}
    ]
}}

Guidelines:
- Use consistent snake_case naming for ALL attribute names (e.g., user_id, created_at, phone_number)
- For string fields: always specify "max_length" (e.g., 50 for names, 255 for emails, 2000 for text)
- For enum fields: set data_type to "enum" and list all valid values in "enum_values"
- For foreign keys: set "is_foreign_key": true and "foreign_key_target": "Entity.field"
- Set "is_indexed": true for fields used in queries, filters, or lookups (FKs, email, status, etc.)
- For N:M relationships: include "junction_table" name (e.g., "user_roles"), "source_fk" and "target_fk"
- ALWAYS include created_at (datetime) and updated_at (datetime) audit fields on every entity
- Every attribute MUST have a non-empty "description" explaining its purpose (e.g., "Unique identifier for the user", "Timestamp of last login")
- Max 5 entities per response. Use: string, integer, decimal, boolean, date, datetime, uuid, enum, text.
Return ONLY valid JSON."""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Data Dictionary Generator.

        Args:
            model_name: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.data_dictionary section
        """
        # Load from config if available
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("data_dictionary", {})

        self.model_name = model_name or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.client = None

    async def initialize(self):
        """Initialize the OpenAI client."""
        if not HAS_OPENAI:
            raise ImportError("openai package required. Install with: pip install openai")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def _call_llm(self, prompt: str, max_tokens: int = None) -> str:
        """Call the LLM and return the response."""
        if not self.client:
            await self.initialize()

        # Use config max_tokens if not specified
        if max_tokens is None:
            max_tokens = self.max_tokens

        start_time = time.time()
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are an expert Data Architect. Always respond with valid JSON only. Keep responses concise."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.temperature,
            max_tokens=max_tokens
        )
        latency_ms = int((time.time() - start_time) * 1000)

        response_text = response.choices[0].message.content.strip()

        # Log the LLM call
        log_llm_call(
            component="data_dictionary_generator",
            model=self.model_name,
            response=response,
            latency_ms=latency_ms,
            system_message="You are an expert Data Architect. Always respond with valid JSON only. Keep responses concise.",
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
        return {"entities": []}

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

    async def generate_dictionary(
        self,
        requirements: List,
        domain: str = "",
        title: str = "Data Dictionary",
        max_context_tokens: int = 100000,
        max_requirements_per_batch: int = 10
    ) -> DataDictionary:
        """
        Generate a complete Data Dictionary from requirements.

        Uses token-aware chunking to process large requirement sets.
        Limits batch size to prevent LLM output truncation.

        Args:
            requirements: List of RequirementNode instances
            domain: Domain context description
            title: Title for the data dictionary
            max_context_tokens: Maximum tokens per LLM call
            max_requirements_per_batch: Maximum requirements per batch to prevent output truncation

        Returns:
            DataDictionary instance
        """
        if not requirements:
            print("  [WARN] No requirements provided")
            return DataDictionary(title=title)

        # Use smaller batches to prevent output truncation
        # Even if all reqs fit in context, limit batch size to prevent huge JSON responses
        budget = TokenBudget(max_context=max_context_tokens)

        # Calculate number of batches based on max_requirements_per_batch
        num_batches = (len(requirements) + max_requirements_per_batch - 1) // max_requirements_per_batch
        print(f"  Processing {len(requirements)} requirements in {num_batches} batch(es) (max {max_requirements_per_batch}/batch)")

        dictionary = DataDictionary(title=title)
        all_batch_results = []
        # Track seen entity names (case-insensitive) to prevent duplicates like User/user
        seen_entity_keys = set()

        # Process each batch using fixed batch size
        batch_num = 0
        for i in range(0, len(requirements), max_requirements_per_batch):
            batch = requirements[i:i + max_requirements_per_batch]
            batch_num += 1
            print(f"  [Batch {batch_num}/{num_batches}] Processing {len(batch)} requirements...")

            # Build requirements summary for this batch
            req_summary = ""
            for req in batch:
                req_summary += f"- {req.requirement_id}: {req.title}\n"
                req_summary += f"  {req.description}\n"

            prompt = self.ENTITY_PROMPT.format(
                requirements=req_summary,
                domain=domain or "Software System"
            )

            print(f"    Analyzing batch for domain entities...")
            response = await self._call_llm(prompt)
            data = self._extract_json(response)
            all_batch_results.append(data)

            # Parse entities from this batch
            batch_entities = 0
            for entity_data in data.get("entities", []):
                entity_name = entity_data.get("name", "Unknown").strip()

                # Skip duplicates (case-insensitive to catch User/user/USER)
                entity_key = entity_name.lower()
                if entity_key in seen_entity_keys or entity_name in dictionary.entities:
                    print(f"    [Skip] Entity '{entity_name}' already exists (case-insensitive)")
                    continue
                seen_entity_keys.add(entity_key)

                attributes = []
                for attr_data in entity_data.get("attributes", []):
                    # Gap #19: Enforce snake_case naming
                    attr_name = self._to_snake_case(attr_data.get("name", ""))
                    attributes.append(Attribute(
                        name=attr_name,
                        data_type=attr_data.get("data_type", "string"),
                        description=attr_data.get("description", ""),
                        required=attr_data.get("required", True),
                        unique=attr_data.get("unique", False),
                        constraints=attr_data.get("constraints", []),
                        example=attr_data.get("example"),
                        max_length=attr_data.get("max_length"),
                        enum_values=attr_data.get("enum_values", []),
                        is_indexed=attr_data.get("is_indexed", False),
                        is_foreign_key=attr_data.get("is_foreign_key", False),
                        foreign_key_target=attr_data.get("foreign_key_target", ""),
                    ))

                entity = Entity(
                    name=entity_name,
                    description=entity_data.get("description", ""),
                    attributes=attributes,
                    primary_key=entity_data.get("primary_key", "id"),
                    source_requirements=entity_data.get("source_requirements", [])
                )
                # Gap #17: Enforce audit fields (created_at, updated_at) on every entity
                self._ensure_audit_fields(entity)
                dictionary.entities[entity.name] = entity
                batch_entities += 1
                print(f"    Found entity: {entity.name}")

            # Parse relationships from this batch
            for rel_data in data.get("relationships", []):
                relationship = Relationship(
                    name=rel_data.get("name", ""),
                    source_entity=rel_data.get("source_entity", ""),
                    target_entity=rel_data.get("target_entity", ""),
                    cardinality=rel_data.get("cardinality", "1:N"),
                    description=rel_data.get("description", ""),
                    # Gap #3: Junction table for N:M
                    junction_table=rel_data.get("junction_table"),
                    source_fk=rel_data.get("source_fk", ""),
                    target_fk=rel_data.get("target_fk", ""),
                )
                # Avoid duplicate relationships
                existing = [r for r in dictionary.relationships
                           if r.source_entity == relationship.source_entity
                           and r.target_entity == relationship.target_entity]
                if not existing:
                    dictionary.relationships.append(relationship)

            # Parse glossary from this batch
            for term_data in data.get("glossary", []):
                term_name = term_data.get("term", "")
                if term_name and term_name not in dictionary.glossary:
                    term = GlossaryTerm(
                        term=term_name,
                        definition=term_data.get("definition", ""),
                        synonyms=term_data.get("synonyms", []),
                        related_terms=term_data.get("related_terms", [])
                    )
                    dictionary.glossary[term.term] = term

            print(f"    Batch {batch_num}/{num_batches} complete: {batch_entities} new entities")

        print(f"  Generated dictionary with {len(dictionary.entities)} entities, "
              f"{len(dictionary.relationships)} relationships, "
              f"{len(dictionary.glossary)} glossary terms")

        return dictionary

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert camelCase or PascalCase to snake_case (Gap #19)."""
        if not name:
            return name
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
        s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower().replace(' ', '_').replace('-', '_')

    @staticmethod
    def _ensure_audit_fields(entity: Entity) -> None:
        """Ensure created_at and updated_at exist on every entity (Gap #17)."""
        existing_names = {a.name for a in entity.attributes}
        for audit_name in ("created_at", "updated_at"):
            if audit_name not in existing_names:
                entity.attributes.append(Attribute(
                    name=audit_name,
                    data_type="datetime",
                    description=f"Timestamp when the record was {'created' if 'created' in audit_name else 'last updated'}",
                    required=True,
                    default_value="NOW()",
                ))


# Test function
async def test_data_dictionary_generator():
    """Test the DataDictionaryGenerator with sample data."""
    from requirements_engineer.core.re_journal import RequirementNode

    # Create sample requirements
    requirements = [
        RequirementNode(
            requirement_id="REQ-001",
            title="User Registration",
            description="Users should be able to register with email, password, and profile information including name and address",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-002",
            title="Product Catalog",
            description="System should display products with name, description, price, category, and stock quantity",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-003",
            title="Shopping Cart",
            description="Users should be able to add products to cart with quantity, view cart contents, and see total price",
            type="functional",
            priority="must"
        ),
        RequirementNode(
            requirement_id="REQ-004",
            title="Order Processing",
            description="Users should be able to place orders with shipping address, payment method, and receive order confirmation",
            type="functional",
            priority="must"
        )
    ]

    generator = DataDictionaryGenerator()
    await generator.initialize()

    print("=== Generating Data Dictionary ===\n")
    dictionary = await generator.generate_dictionary(
        requirements,
        domain="E-Commerce Platform",
        title="E-Commerce Data Dictionary"
    )

    print("\n=== Markdown Output ===\n")
    print(dictionary.to_markdown())

    print("\n=== ER Diagram (Mermaid) ===\n")
    print(dictionary.to_er_diagram())

    return dictionary


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_data_dictionary_generator())
