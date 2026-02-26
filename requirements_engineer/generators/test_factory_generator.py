"""
Test Data Factory Generator - Generates test data factories from data dictionary.

Produces language-appropriate test data factories based on the tech stack:
- Python: factory_boy factory classes
- TypeScript/Node.js: @faker-js/faker factory functions
- Go: gofakeit builder functions
- Java: Javafaker builder methods

Also generates:
- Seed data (SQL for relational DBs, JSON for document DBs)
- Factory summary documentation

Fully programmatic (no LLM needed).
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from pathlib import Path
from datetime import datetime


@dataclass_json
@dataclass
class FieldFactory:
    """Factory configuration for a single field."""
    name: str
    data_type: str
    faker_method: str = ""
    default_value: str = ""
    is_fk: bool = False
    fk_factory: str = ""  # Name of related factory


@dataclass_json
@dataclass
class EntityFactory:
    """Factory definition for one entity."""
    entity_name: str
    table_name: str
    fields: List[FieldFactory] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # factories needed first


# ── Language alias normalization ──────────────────────────────────────────────

LANG_ALIASES = {
    "typescript": "node.js", "javascript": "node.js", "nodejs": "node.js",
    "golang": "go", "csharp": "c#", "dotnet": "c#",
}


def _detect_lang(tech_stack_dict: dict) -> str:
    """Normalize backend language to lookup key.

    Handles version-suffixed values like "Node.js 20.15.1" -> "node.js".
    """
    raw = tech_stack_dict.get("backend_language", "python").lower().strip()
    # Strip version number (e.g. "node.js 20.15.1" -> "node.js")
    raw = re.sub(r'\s+[\d][\d.]*$', '', raw)
    return LANG_ALIASES.get(raw, raw)


def _detect_db(tech_stack_dict: dict) -> str:
    """Normalize primary database to lookup key."""
    raw = tech_stack_dict.get("primary_database", "postgresql").lower().strip()
    if "mongo" in raw:
        return "mongodb"
    if "mysql" in raw or "maria" in raw:
        return "mysql"
    if "sqlite" in raw:
        return "sqlite"
    return "postgresql"


# ── Python (factory_boy) faker maps ──────────────────────────────────────────

FAKER_MAP = {
    "uuid": "factory.LazyFunction(uuid4)",
    "string": "factory.Faker('text', max_nb_chars=50)",
    "text": "factory.Faker('paragraph')",
    "integer": "factory.Faker('random_int', min=0, max=10000)",
    "int": "factory.Faker('random_int', min=0, max=10000)",
    "bigint": "factory.Faker('random_int', min=0, max=1000000)",
    "decimal": "factory.Faker('pydecimal', left_digits=5, right_digits=2, positive=True)",
    "float": "factory.Faker('pyfloat', positive=True)",
    "boolean": "factory.Faker('boolean')",
    "bool": "factory.Faker('boolean')",
    "date": "factory.Faker('date_object')",
    "datetime": "factory.Faker('date_time')",
    "timestamp": "factory.Faker('date_time')",
    "json": "factory.LazyFunction(dict)",
    "jsonb": "factory.LazyFunction(dict)",
    "bytea": "factory.Faker('binary', length=64)",
}

FIELD_FAKER_MAP = {
    "email": "factory.Faker('email')",
    "phone": "factory.Faker('phone_number')",
    "phone_number": "factory.Faker('phone_number')",
    "name": "factory.Faker('name')",
    "first_name": "factory.Faker('first_name')",
    "last_name": "factory.Faker('last_name')",
    "username": "factory.Faker('user_name')",
    "display_name": "factory.Faker('name')",
    "url": "factory.Faker('url')",
    "avatar_url": "factory.Faker('image_url')",
    "profile_image": "factory.Faker('image_url')",
    "address": "factory.Faker('address')",
    "city": "factory.Faker('city')",
    "country": "factory.Faker('country')",
    "country_code": "factory.Faker('country_code')",
    "locale_code": "factory.Faker('locale')",
    "language_code": "factory.Faker('language_code')",
    "description": "factory.Faker('paragraph')",
    "bio": "factory.Faker('paragraph')",
    "title": "factory.Faker('sentence', nb_words=4)",
    "content": "factory.Faker('paragraph')",
    "content_text": "factory.Faker('paragraph')",
    "ip_address": "factory.Faker('ipv4')",
    "user_agent": "factory.Faker('user_agent')",
    "latitude": "factory.Faker('latitude')",
    "longitude": "factory.Faker('longitude')",
    "color": "factory.Faker('hex_color')",
    "password": "factory.Faker('password')",
    "password_hash": "factory.Faker('sha256')",
    "token": "factory.Faker('sha256')",
    "api_key": "factory.Faker('sha256')",
    "created_at": "factory.Faker('date_time')",
    "updated_at": "factory.Faker('date_time')",
    "deleted_at": "None",
    "status": "factory.Faker('random_element', elements=['active', 'inactive'])",
    "emoji": "factory.Faker('emoji')",
}

# ── TypeScript (@faker-js/faker) maps ────────────────────────────────────────

JS_TYPE_MAP = {
    "uuid": "faker.string.uuid()",
    "string": "faker.lorem.words(3)",
    "text": "faker.lorem.paragraph()",
    "integer": "faker.number.int({ min: 0, max: 10000 })",
    "int": "faker.number.int({ min: 0, max: 10000 })",
    "bigint": "faker.number.int({ min: 0, max: 1000000 })",
    "decimal": "parseFloat(faker.finance.amount())",
    "float": "parseFloat(faker.finance.amount())",
    "boolean": "faker.datatype.boolean()",
    "bool": "faker.datatype.boolean()",
    "date": "faker.date.recent()",
    "datetime": "faker.date.recent()",
    "timestamp": "faker.date.recent()",
    "json": "{}",
    "jsonb": "{}",
    "bytea": "Buffer.from(faker.string.alphanumeric(64))",
}

JS_FIELD_MAP = {
    "email": "faker.internet.email()",
    "phone": "faker.phone.number()",
    "phone_number": "faker.phone.number()",
    "name": "faker.person.fullName()",
    "first_name": "faker.person.firstName()",
    "last_name": "faker.person.lastName()",
    "username": "faker.internet.username()",
    "display_name": "faker.person.fullName()",
    "url": "faker.internet.url()",
    "avatar_url": "faker.image.avatar()",
    "profile_image": "faker.image.avatar()",
    "address": "faker.location.streetAddress()",
    "city": "faker.location.city()",
    "country": "faker.location.country()",
    "country_code": "faker.location.countryCode()",
    "description": "faker.lorem.paragraph()",
    "bio": "faker.lorem.paragraph()",
    "title": "faker.lorem.sentence()",
    "content": "faker.lorem.paragraph()",
    "content_text": "faker.lorem.paragraph()",
    "ip_address": "faker.internet.ip()",
    "user_agent": "faker.internet.userAgent()",
    "latitude": "faker.location.latitude()",
    "longitude": "faker.location.longitude()",
    "color": "faker.color.rgb()",
    "password": "faker.internet.password()",
    "password_hash": "faker.string.alphanumeric(64)",
    "token": "faker.string.alphanumeric(64)",
    "api_key": "faker.string.alphanumeric(64)",
    "created_at": "faker.date.recent()",
    "updated_at": "faker.date.recent()",
    "deleted_at": "null",
    "status": "faker.helpers.arrayElement(['active', 'inactive'])",
    "emoji": "faker.internet.emoji()",
}

# ── Go (gofakeit) maps ───────────────────────────────────────────────────────

GO_TYPE_MAP = {
    "uuid": "uuid.New().String()",
    "string": "gofakeit.Word()",
    "text": "gofakeit.Paragraph(1, 3, 5, \" \")",
    "integer": "gofakeit.Number(0, 10000)",
    "int": "gofakeit.Number(0, 10000)",
    "bigint": "gofakeit.Number(0, 1000000)",
    "decimal": "gofakeit.Float64Range(0, 10000)",
    "float": "gofakeit.Float64Range(0, 10000)",
    "boolean": "gofakeit.Bool()",
    "bool": "gofakeit.Bool()",
    "date": "gofakeit.Date()",
    "datetime": "gofakeit.Date()",
    "timestamp": "gofakeit.Date()",
    "json": "\"{}\"",
    "jsonb": "\"{}\"",
}

GO_FIELD_MAP = {
    "email": "gofakeit.Email()",
    "phone": "gofakeit.Phone()",
    "phone_number": "gofakeit.Phone()",
    "name": "gofakeit.Name()",
    "first_name": "gofakeit.FirstName()",
    "last_name": "gofakeit.LastName()",
    "username": "gofakeit.Username()",
    "display_name": "gofakeit.Name()",
    "url": "gofakeit.URL()",
    "avatar_url": "gofakeit.ImageURL(200, 200)",
    "address": "gofakeit.Street()",
    "city": "gofakeit.City()",
    "country": "gofakeit.Country()",
    "country_code": "gofakeit.CountryAbr()",
    "description": "gofakeit.Paragraph(1, 3, 5, \" \")",
    "bio": "gofakeit.Paragraph(1, 3, 5, \" \")",
    "title": "gofakeit.Sentence(4)",
    "content": "gofakeit.Paragraph(1, 3, 5, \" \")",
    "ip_address": "gofakeit.IPv4Address()",
    "user_agent": "gofakeit.UserAgent()",
    "latitude": "gofakeit.Latitude()",
    "longitude": "gofakeit.Longitude()",
    "color": "gofakeit.HexColor()",
    "password": "gofakeit.Password(true, true, true, true, false, 12)",
    "password_hash": "gofakeit.LetterN(64)",
    "token": "gofakeit.LetterN(64)",
    "api_key": "gofakeit.LetterN(64)",
    "created_at": "gofakeit.Date()",
    "updated_at": "gofakeit.Date()",
    "status": "gofakeit.RandomString([]string{\"active\", \"inactive\"})",
    "emoji": "gofakeit.Emoji()",
}

# ── Java (javafaker) maps ────────────────────────────────────────────────────

JAVA_TYPE_MAP = {
    "uuid": "UUID.randomUUID().toString()",
    "string": "faker.lorem().word()",
    "text": "faker.lorem().paragraph()",
    "integer": "faker.number().numberBetween(0, 10000)",
    "int": "faker.number().numberBetween(0, 10000)",
    "bigint": "faker.number().numberBetween(0, 1000000)",
    "decimal": "BigDecimal.valueOf(faker.number().randomDouble(2, 0, 10000))",
    "float": "faker.number().randomDouble(2, 0, 10000)",
    "boolean": "faker.bool().bool()",
    "bool": "faker.bool().bool()",
    "date": "faker.date().birthday()",
    "datetime": "faker.date().birthday()",
    "timestamp": "faker.date().birthday()",
    "json": "\"{}\"",
    "jsonb": "\"{}\"",
}

JAVA_FIELD_MAP = {
    "email": "faker.internet().emailAddress()",
    "phone": "faker.phoneNumber().phoneNumber()",
    "phone_number": "faker.phoneNumber().phoneNumber()",
    "name": "faker.name().fullName()",
    "first_name": "faker.name().firstName()",
    "last_name": "faker.name().lastName()",
    "username": "faker.name().username()",
    "display_name": "faker.name().fullName()",
    "url": "faker.internet().url()",
    "avatar_url": "faker.internet().avatar()",
    "address": "faker.address().streetAddress()",
    "city": "faker.address().city()",
    "country": "faker.address().country()",
    "country_code": "faker.address().countryCode()",
    "description": "faker.lorem().paragraph()",
    "bio": "faker.lorem().paragraph()",
    "title": "faker.lorem().sentence()",
    "content": "faker.lorem().paragraph()",
    "ip_address": "faker.internet().ipV4Address()",
    "user_agent": "faker.internet().userAgentAny()",
    "latitude": "String.valueOf(faker.address().latitude())",
    "longitude": "String.valueOf(faker.address().longitude())",
    "color": "faker.color().hex()",
    "password": "faker.internet().password()",
    "password_hash": "faker.crypto().sha256()",
    "token": "faker.crypto().sha256()",
    "api_key": "faker.crypto().sha256()",
    "created_at": "faker.date().birthday()",
    "updated_at": "faker.date().birthday()",
    "status": "faker.options().option(\"active\", \"inactive\")",
    "emoji": "\"\\uD83D\\uDE00\"",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.lower().replace(' ', '_').replace('-', '_')


def _to_class_name(name: str) -> str:
    """Convert snake_case or any to PascalCase. Preserves existing PascalCase."""
    if re.search(r'[_\-\s]', name):
        # Has separators — split and capitalize each part
        return ''.join(word.capitalize() for word in re.split(r'[_\-\s]+', name))
    # No separators — preserve existing mixed case (PascalCase/camelCase)
    if any(c.isupper() for c in name[1:]):
        return name[0].upper() + name[1:]
    # Single-word lowercase — capitalize
    return name.capitalize()


def _to_camel_case(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = re.split(r'[_\-\s]+', name)
    return parts[0].lower() + ''.join(w.capitalize() for w in parts[1:])


# ── Go type mapping ──────────────────────────────────────────────────────────

GO_TYPE_DECL = {
    "uuid": "string", "string": "string", "text": "string",
    "integer": "int", "int": "int", "bigint": "int64",
    "decimal": "float64", "float": "float64",
    "boolean": "bool", "bool": "bool",
    "date": "time.Time", "datetime": "time.Time", "timestamp": "time.Time",
    "json": "string", "jsonb": "string", "enum": "string",
}

# ── Java type mapping ────────────────────────────────────────────────────────

JAVA_TYPE_DECL = {
    "uuid": "String", "string": "String", "text": "String",
    "integer": "int", "int": "int", "bigint": "long",
    "decimal": "BigDecimal", "float": "double",
    "boolean": "boolean", "bool": "boolean",
    "date": "Date", "datetime": "Date", "timestamp": "Date",
    "json": "String", "jsonb": "String", "enum": "String",
}

# ── TypeScript type mapping ───────────────────────────────────────────────────

TS_TYPE_DECL = {
    "uuid": "string", "string": "string", "text": "string",
    "integer": "number", "int": "number", "bigint": "number",
    "decimal": "number", "float": "number",
    "boolean": "boolean", "bool": "boolean",
    "date": "Date", "datetime": "Date", "timestamp": "Date",
    "json": "Record<string, unknown>", "jsonb": "Record<string, unknown>",
    "bytea": "Buffer", "enum": "string",
}


# ── Suffix-based faker matching (cross-language) ─────────────────────────────
# Catches fields like media_url, profile_image_url, invite_link_url, etc.

SUFFIX_FAKER = {
    "url": {
        "js": "faker.internet.url()", "go": "gofakeit.URL()",
        "java": 'faker.internet().url()', "py": "factory.Faker('url')",
    },
    "email": {
        "js": "faker.internet.email()", "go": "gofakeit.Email()",
        "java": 'faker.internet().emailAddress()', "py": "factory.Faker('email')",
    },
    "phone": {
        "js": "faker.phone.number()", "go": "gofakeit.Phone()",
        "java": 'faker.phoneNumber().phoneNumber()', "py": "factory.Faker('phone_number')",
    },
}


def _suffix_faker(ff_name: str, lang_key: str) -> Optional[str]:
    """Check if field name ends with a known suffix and return the appropriate faker."""
    name_lower = ff_name.lower()
    for suffix, fakers in SUFFIX_FAKER.items():
        if name_lower.endswith(f"_{suffix}") or name_lower == suffix:
            return fakers.get(lang_key)
    return None


def _id_suffix_faker(ff: 'FieldFactory', lang_key: str) -> Optional[str]:
    """If a non-FK field name ends with 'Id' or '_id' and is uuid/string, return UUID faker."""
    camel = _to_camel_case(ff.name)
    if camel.endswith("Id") and ff.data_type in ("uuid", "string") and not ff.is_fk:
        return {
            "js": "faker.string.uuid()",
            "go": "uuid.New().String()",
            "java": "UUID.randomUUID().toString()",
            "py": "factory.LazyFunction(uuid4)",
        }.get(lang_key)
    return None


class TestFactoryGenerator:
    """Generates test data factories from data dictionary entities."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.factories: List[EntityFactory] = []
        self.lang: str = "python"
        self.db: str = "postgresql"

    async def initialize(self):
        """No async init needed for programmatic generator."""
        pass

    def generate_factories(self, data_dict_entities: dict,
                           data_dict_relationships: list = None,
                           tech_stack_dict: dict = None) -> List[EntityFactory]:
        """Generate factory definitions from data dictionary.

        Args:
            data_dict_entities: Dict[str, Entity] from DataDictionary.entities
            data_dict_relationships: List of Relationship objects
            tech_stack_dict: TechStack.to_dict() for language/DB detection

        Returns:
            List of EntityFactory definitions
        """
        relationships = data_dict_relationships or []
        ts = tech_stack_dict or {}
        self.lang = _detect_lang(ts)
        self.db = _detect_db(ts)
        self.factories = []

        for entity_name, entity in data_dict_entities.items():
            table_name = _to_snake_case(entity_name)
            attrs = entity.attributes if hasattr(entity, 'attributes') else []
            if isinstance(attrs, dict):
                attrs = list(attrs.values())

            fields = []
            deps = []

            for attr in attrs:
                a_name = attr.name if hasattr(attr, 'name') else str(attr)
                a_type = (attr.data_type if hasattr(attr, 'data_type') else 'string').lower()
                a_is_fk = getattr(attr, 'is_foreign_key', False)
                a_fk_target = getattr(attr, 'foreign_key_target', '')
                a_enum_values = getattr(attr, 'enum_values', [])

                # Determine faker method (Python — used as canonical; other langs use own maps)
                if a_name == (entity.primary_key if hasattr(entity, 'primary_key') else 'id'):
                    faker = "factory.LazyFunction(uuid4)"
                elif a_is_fk and a_fk_target:
                    ref_entity = a_fk_target.split(".")[0]
                    ref_factory = f"{_to_class_name(ref_entity)}Factory"
                    faker = f"factory.SubFactory({ref_factory})"
                    if ref_entity != entity_name:
                        deps.append(ref_entity)
                elif a_type == "enum" and a_enum_values:
                    vals_str = ", ".join(f"'{v}'" for v in a_enum_values)
                    faker = f"factory.Faker('random_element', elements=[{vals_str}])"
                elif a_name in FIELD_FAKER_MAP:
                    faker = FIELD_FAKER_MAP[a_name]
                else:
                    faker = FAKER_MAP.get(a_type, "factory.Faker('text', max_nb_chars=50)")

                fk_factory = ""
                if a_is_fk and a_fk_target:
                    fk_factory = f"{_to_class_name(a_fk_target.split('.')[0])}Factory"

                fields.append(FieldFactory(
                    name=a_name,
                    data_type=a_type,
                    faker_method=faker,
                    is_fk=a_is_fk,
                    fk_factory=fk_factory,
                ))

            self.factories.append(EntityFactory(
                entity_name=entity_name,
                table_name=table_name,
                fields=fields,
                dependencies=list(set(deps)),
            ))

        return self.factories

    # ── Language dispatcher ───────────────────────────────────────────────────

    def to_factories(self) -> str:
        """Generate factory code in the detected language."""
        dispatch = {
            "python": self.to_python_factories,
            "node.js": self.to_typescript_factories,
            "go": self.to_go_factories,
            "java": self.to_java_factories,
        }
        return dispatch.get(self.lang, self.to_python_factories)()

    def factory_file_extension(self) -> str:
        """Return the file extension for the detected language."""
        return {
            "python": ".py",
            "node.js": ".ts",
            "go": "_test.go",
            "java": ".java",
        }.get(self.lang, ".py")

    def factory_file_name(self) -> str:
        """Return the primary factory file name."""
        return {
            "python": "factories.py",
            "node.js": "factories.ts",
            "go": "factories_test.go",
            "java": "TestDataFactory.java",
        }.get(self.lang, "factories.py")

    # ── Python (factory_boy) ──────────────────────────────────────────────────

    def to_python_factories(self) -> str:
        """Generate Python factory_boy code for all entities."""
        lines = [
            '"""Test data factories for all entities.',
            '',
            'Auto-generated by requirements_engineer pipeline.',
            'Uses factory_boy for declarative test data.',
            '"""',
            'import factory',
            'from uuid import uuid4',
            'from datetime import datetime',
            '',
            '',
        ]

        sorted_factories = self._topological_sort()

        for ef in sorted_factories:
            class_name = f"{_to_class_name(ef.entity_name)}Factory"
            lines.append(f"class {class_name}(factory.Factory):")
            lines.append(f'    """Factory for {ef.entity_name} entity."""')
            lines.append(f"")
            lines.append(f"    class Meta:")
            lines.append(f'        model = dict  # Replace with ORM model')
            lines.append(f"")

            for ff in ef.fields:
                lines.append(f"    {ff.name} = {ff.faker_method}")

            lines.append("")
            lines.append("")

        return "\n".join(lines)

    # ── TypeScript (@faker-js/faker) ──────────────────────────────────────────

    def to_typescript_factories(self) -> str:
        """Generate TypeScript factory functions using @faker-js/faker."""
        lines = [
            '/**',
            ' * Test data factories for all entities.',
            ' *',
            ' * Auto-generated by requirements_engineer pipeline.',
            ' * Uses @faker-js/faker for realistic test data.',
            ' */',
            "import { faker } from '@faker-js/faker';",
            '',
        ]

        sorted_factories = self._topological_sort()

        # Generate interfaces
        for ef in sorted_factories:
            iface = _to_class_name(ef.entity_name)
            lines.append(f"export interface {iface} {{")
            for ff in ef.fields:
                ts_type = TS_TYPE_DECL.get(ff.data_type, "string")
                optional = "?" if ff.name == "deleted_at" else ""
                lines.append(f"  {_to_camel_case(ff.name)}{optional}: {ts_type};")
            lines.append("}")
            lines.append("")

        lines.append("")

        # Generate factory functions
        for ef in sorted_factories:
            iface = _to_class_name(ef.entity_name)
            func_name = f"create{iface}"
            lines.append(f"export function {func_name}(overrides: Partial<{iface}> = {{}}): {iface} {{")
            lines.append(f"  return {{")

            for ff in ef.fields:
                camel = _to_camel_case(ff.name)
                if ff.is_fk:
                    ref_iface = ff.fk_factory.replace("Factory", "")
                    if ref_iface == iface:
                        # Self-reference — use null to avoid infinite recursion
                        val = "null"
                    else:
                        pk = self._get_pk_field(ref_iface)
                        val = f"create{ref_iface}().{_to_camel_case(pk)}"
                else:
                    val = self._js_faker_for(ff)
                lines.append(f"    {camel}: {val},")

            lines.append(f"    ...overrides,")
            lines.append(f"  }};")
            lines.append("}")
            lines.append("")

        # Batch helper
        lines.append("export function createBatch<T>(factory: (o?: Partial<T>) => T, count: number): T[] {")
        lines.append("  return Array.from({ length: count }, () => factory());")
        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _js_faker_for(self, ff: FieldFactory) -> str:
        """Get @faker-js/faker expression for a field."""
        if ff.name in JS_FIELD_MAP:
            return JS_FIELD_MAP[ff.name]
        if ff.data_type == "enum":
            m = re.search(r"elements=\[(.*?)\]", ff.faker_method)
            if m:
                return f"faker.helpers.arrayElement([{m.group(1)}])"
        # Suffix matching: *_url, *_email, *_phone
        sfx = _suffix_faker(ff.name, "js")
        if sfx:
            return sfx
        # ID-suffix fields → UUID
        id_val = _id_suffix_faker(ff, "js")
        if id_val:
            return id_val
        return JS_TYPE_MAP.get(ff.data_type, "faker.lorem.words(3)")

    # ── Go (gofakeit) ────────────────────────────────────────────────────────

    def to_go_factories(self) -> str:
        """Generate Go factory functions using gofakeit."""
        lines = [
            '// Test data factories for all entities.',
            '//',
            '// Auto-generated by requirements_engineer pipeline.',
            '// Uses brianvoe/gofakeit for realistic test data.',
            'package testdata',
            '',
            'import (',
            '\t"time"',
            '',
            '\t"github.com/brianvoe/gofakeit/v7"',
            '\t"github.com/google/uuid"',
            ')',
            '',
        ]

        sorted_factories = self._topological_sort()

        # Generate structs
        for ef in sorted_factories:
            struct_name = _to_class_name(ef.entity_name)
            lines.append(f"type {struct_name} struct {{")
            for ff in ef.fields:
                go_type = GO_TYPE_DECL.get(ff.data_type, "string")
                go_field = _to_class_name(ff.name)
                tag = f'`json:"{ff.name}" db:"{ff.name}"`'
                lines.append(f"\t{go_field} {go_type} {tag}")
            lines.append("}")
            lines.append("")

        # Generate factory functions
        for ef in sorted_factories:
            struct_name = _to_class_name(ef.entity_name)
            lines.append(f"func New{struct_name}() {struct_name} {{")
            lines.append(f"\treturn {struct_name}{{")

            for ff in ef.fields:
                go_field = _to_class_name(ff.name)
                if ff.is_fk:
                    ref_struct = ff.fk_factory.replace("Factory", "")
                    if ref_struct == struct_name:
                        # Self-reference — use empty string to avoid infinite recursion
                        val = '""'
                    else:
                        pk = self._get_pk_field(ref_struct)
                        val = f"New{ref_struct}().{_to_class_name(pk)}"
                else:
                    val = self._go_faker_for(ff)
                lines.append(f"\t\t{go_field}: {val},")

            lines.append("\t}")
            lines.append("}")
            lines.append("")

        # Batch helper
        lines.append(f"func NewBatch[T any](factory func() T, count int) []T {{")
        lines.append(f"\tresult := make([]T, count)")
        lines.append(f"\tfor i := range result {{")
        lines.append(f"\t\tresult[i] = factory()")
        lines.append(f"\t}}")
        lines.append(f"\treturn result")
        lines.append(f"}}")
        lines.append("")

        return "\n".join(lines)

    def _go_faker_for(self, ff: FieldFactory) -> str:
        """Get gofakeit expression for a field."""
        if ff.name in GO_FIELD_MAP:
            return GO_FIELD_MAP[ff.name]
        if ff.data_type == "enum":
            m = re.search(r"elements=\[(.*?)\]", ff.faker_method)
            if m:
                vals = m.group(1).replace("'", '"')
                return f'gofakeit.RandomString([]string{{{vals}}})'
        sfx = _suffix_faker(ff.name, "go")
        if sfx:
            return sfx
        id_val = _id_suffix_faker(ff, "go")
        if id_val:
            return id_val
        return GO_TYPE_MAP.get(ff.data_type, 'gofakeit.Word()')

    # ── Java (javafaker) ─────────────────────────────────────────────────────

    def to_java_factories(self) -> str:
        """Generate Java factory class using javafaker."""
        lines = [
            '/**',
            ' * Test data factories for all entities.',
            ' *',
            ' * Auto-generated by requirements_engineer pipeline.',
            ' * Uses com.github.javafaker:javafaker for realistic test data.',
            ' */',
            'package testdata;',
            '',
            'import com.github.javafaker.Faker;',
            'import java.math.BigDecimal;',
            'import java.util.*;',
            '',
        ]

        sorted_factories = self._topological_sort()

        # Generate POJOs
        for ef in sorted_factories:
            class_name = _to_class_name(ef.entity_name)
            lines.append(f"class {class_name} {{")
            for ff in ef.fields:
                java_type = JAVA_TYPE_DECL.get(ff.data_type, "String")
                lines.append(f"    public {java_type} {_to_camel_case(ff.name)};")
            lines.append("}")
            lines.append("")

        # Generate factory class
        lines.append("public class TestDataFactory {")
        lines.append("    private static final Faker faker = new Faker();")
        lines.append("")

        for ef in sorted_factories:
            class_name = _to_class_name(ef.entity_name)
            method = f"create{class_name}"
            lines.append(f"    public static {class_name} {method}() {{")
            lines.append(f"        {class_name} obj = new {class_name}();")

            for ff in ef.fields:
                camel = _to_camel_case(ff.name)
                if ff.is_fk:
                    ref_class = ff.fk_factory.replace("Factory", "")
                    if ref_class == class_name:
                        # Self-reference — use null to avoid infinite recursion
                        val = "null"
                    else:
                        pk = self._get_pk_field(ref_class)
                        val = f"create{ref_class}().{_to_camel_case(pk)}"
                else:
                    val = self._java_faker_for(ff)
                lines.append(f"        obj.{camel} = {val};")

            lines.append(f"        return obj;")
            lines.append("    }")
            lines.append("")

        # Batch helper
        lines.append("    public static <T> List<T> createBatch(java.util.function.Supplier<T> factory, int count) {")
        lines.append("        List<T> result = new ArrayList<>();")
        lines.append("        for (int i = 0; i < count; i++) { result.add(factory.get()); }")
        lines.append("        return result;")
        lines.append("    }")
        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _java_faker_for(self, ff: FieldFactory) -> str:
        """Get javafaker expression for a field."""
        if ff.name in JAVA_FIELD_MAP:
            return JAVA_FIELD_MAP[ff.name]
        if ff.data_type == "enum":
            m = re.search(r"elements=\[(.*?)\]", ff.faker_method)
            if m:
                vals = m.group(1).replace("'", '"')
                return f'faker.options().option({vals})'
        sfx = _suffix_faker(ff.name, "java")
        if sfx:
            return sfx
        id_val = _id_suffix_faker(ff, "java")
        if id_val:
            return id_val
        return JAVA_TYPE_MAP.get(ff.data_type, 'faker.lorem().word()')

    # ── Seed data ─────────────────────────────────────────────────────────────

    def to_seed_sql(self) -> str:
        """Generate seed data SQL with sample inserts (PostgreSQL or MySQL)."""
        is_mysql = self.db == "mysql"
        q = "`" if is_mysql else ""  # Identifier quoting

        lines = [
            f"-- Seed data for development database ({self.db})",
            f"-- Generated: {datetime.now().isoformat()}",
            f"-- Insert 3 sample rows per entity",
            "",
        ]

        sorted_factories = self._topological_sort()

        for ef in sorted_factories:
            if not ef.fields:
                continue

            simple_fields = [f for f in ef.fields if not f.is_fk]
            if not simple_fields:
                continue

            col_names = ", ".join(f"{q}{f.name}{q}" for f in simple_fields)
            lines.append(f"-- {ef.entity_name}")

            for i in range(1, 4):
                values = []
                for f in simple_fields:
                    values.append(self._sample_value(f, i))
                vals_str = ", ".join(values)
                lines.append(f"INSERT INTO {q}{ef.table_name}{q} ({col_names}) VALUES ({vals_str});")

            lines.append("")

        return "\n".join(lines)

    def to_seed_json(self) -> str:
        """Generate seed data as JSON fixtures (for MongoDB / document DBs)."""
        sorted_factories = self._topological_sort()
        collections = {}

        for ef in sorted_factories:
            if not ef.fields:
                continue

            docs = []
            simple_fields = [f for f in ef.fields if not f.is_fk]
            for i in range(1, 4):
                doc = {}
                for f in simple_fields:
                    doc[f.name] = self._sample_value_raw(f, i)
                docs.append(doc)

            collections[ef.table_name] = docs

        return json.dumps(collections, indent=2, ensure_ascii=False)

    def _sample_value(self, ff: FieldFactory, index: int) -> str:
        """Generate a sample SQL value for a field."""
        t = ff.data_type.lower()
        if ff.name in ("id",) or t == "uuid":
            return f"'00000000-0000-0000-0000-00000000000{index}'"
        elif t in ("string", "varchar", "text"):
            return f"'sample_{ff.name}_{index}'"
        elif t in ("integer", "int", "bigint"):
            return str(index * 100)
        elif t in ("decimal", "float"):
            return f"{index * 10.5}"
        elif t in ("boolean", "bool"):
            return "TRUE" if index % 2 == 0 else "FALSE"
        elif t in ("date",):
            return f"'2026-01-{index:02d}'"
        elif t in ("datetime", "timestamp"):
            return f"'2026-01-{index:02d} 12:00:00+00'"
        elif t == "enum":
            return f"'value_{index}'"
        elif t in ("json", "jsonb"):
            return "'{}'"
        else:
            return f"'sample_{index}'"

    def _sample_value_raw(self, ff: FieldFactory, index: int) -> Any:
        """Generate a sample raw Python value (for JSON export)."""
        t = ff.data_type.lower()
        if ff.name in ("id",) or t == "uuid":
            return f"00000000-0000-0000-0000-00000000000{index}"
        elif t in ("string", "varchar", "text"):
            return f"sample_{ff.name}_{index}"
        elif t in ("integer", "int", "bigint"):
            return index * 100
        elif t in ("decimal", "float"):
            return index * 10.5
        elif t in ("boolean", "bool"):
            return index % 2 == 0
        elif t in ("date",):
            return f"2026-01-{index:02d}"
        elif t in ("datetime", "timestamp"):
            return f"2026-01-{index:02d}T12:00:00Z"
        elif t == "enum":
            return f"value_{index}"
        elif t in ("json", "jsonb"):
            return {}
        else:
            return f"sample_{index}"

    def _get_pk_field(self, entity_name: str) -> str:
        """Find the PK field name of an entity (for FK reference resolution).

        Looks up the referenced entity's factories list and returns
        the name of the first non-FK uuid field (the PK). Falls back
        to the first field's name, then 'id'.
        """
        by_name = {ef.entity_name: ef for ef in self.factories}
        ef = by_name.get(entity_name)
        if not ef or not ef.fields:
            return "id"
        for ff in ef.fields:
            if ff.data_type == "uuid" and not ff.is_fk:
                return ff.name
        return ef.fields[0].name

    def _topological_sort(self) -> List[EntityFactory]:
        """Sort factories so dependencies come first."""
        by_name = {ef.entity_name: ef for ef in self.factories}
        visited = set()
        result = []

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            ef = by_name.get(name)
            if ef:
                for dep in ef.dependencies:
                    visit(dep)
                result.append(ef)

        for ef in self.factories:
            visit(ef.entity_name)

        return result

    def to_markdown(self) -> str:
        """Generate summary markdown."""
        lang_label = {
            "python": "Python (factory_boy)",
            "node.js": "TypeScript (@faker-js/faker)",
            "go": "Go (gofakeit)",
            "java": "Java (javafaker)",
        }.get(self.lang, self.lang)

        md = "# Test Data Factories\n\n"
        md += f"**Generated:** {datetime.now().isoformat()}\n\n"
        md += f"**Language:** {lang_label}\n\n"
        md += f"**Database:** {self.db}\n\n"
        md += f"**Total Factories:** {len(self.factories)}\n\n"

        md += "## Factory Summary\n\n"
        md += "| Entity | Table | Fields | Dependencies |\n"
        md += "|--------|-------|--------|-------------|\n"
        for ef in self.factories:
            deps = ", ".join(ef.dependencies) if ef.dependencies else "-"
            md += f"| {ef.entity_name} | `{ef.table_name}` | {len(ef.fields)} | {deps} |\n"

        # Language-appropriate usage example
        md += "\n## Usage\n\n"
        if self.lang == "node.js":
            md += "```typescript\n"
            md += "import { createUser, createBatch } from './factories';\n\n"
            md += "// Create a single user\n"
            md += "const user = createUser();\n\n"
            md += "// Create with overrides\n"
            md += "const admin = createUser({ email: 'admin@example.com' });\n\n"
            md += "// Create batch\n"
            md += "const users = createBatch(createUser, 10);\n"
            md += "```\n\n"
        elif self.lang == "go":
            md += "```go\n"
            md += "import \"yourmodule/testdata\"\n\n"
            md += "// Create a single user\n"
            md += "user := testdata.NewUser()\n\n"
            md += "// Create batch\n"
            md += "users := testdata.NewBatch(testdata.NewUser, 10)\n"
            md += "```\n\n"
        elif self.lang == "java":
            md += "```java\n"
            md += "import testdata.TestDataFactory;\n\n"
            md += "// Create a single user\n"
            md += "User user = TestDataFactory.createUser();\n\n"
            md += "// Create batch\n"
            md += "List<User> users = TestDataFactory.createBatch(TestDataFactory::createUser, 10);\n"
            md += "```\n\n"
        else:
            md += "```python\n"
            md += "from testing.factories.factories import UserFactory, MessageFactory\n\n"
            md += "# Create a single user\n"
            md += "user = UserFactory()\n\n"
            md += "# Create with overrides\n"
            md += "user = UserFactory(email='test@example.com')\n\n"
            md += "# Create batch\n"
            md += "users = UserFactory.create_batch(10)\n"
            md += "```\n\n"

        return md


def save_test_factories(factories_gen: 'TestFactoryGenerator', output_dir) -> None:
    """Save test factory files to output directory."""
    factory_dir = Path(output_dir) / "testing" / "factories"
    factory_dir.mkdir(parents=True, exist_ok=True)

    # Language-appropriate factory file
    factory_code = factories_gen.to_factories()
    factory_filename = factories_gen.factory_file_name()
    with open(factory_dir / factory_filename, "w", encoding="utf-8") as f:
        f.write(factory_code)

    # Remove stale factory files from prior runs with different languages
    for old in ("factories.py", "factories.ts", "factories_test.go", "TestDataFactory.java"):
        old_path = factory_dir / old
        if old_path.exists() and old != factory_filename:
            old_path.unlink()

    # Python __init__.py (only for Python projects)
    if factories_gen.lang == "python":
        with open(factory_dir / "__init__.py", "w", encoding="utf-8") as f:
            f.write('"""Auto-generated test data factories."""\n')

    # Seed data — SQL for relational DBs, JSON for document DBs
    testing_dir = Path(output_dir) / "testing"
    if factories_gen.db == "mongodb":
        seed = factories_gen.to_seed_json()
        with open(testing_dir / "seed_data.json", "w", encoding="utf-8") as f:
            f.write(seed)
    else:
        seed_sql = factories_gen.to_seed_sql()
        with open(testing_dir / "seed_data.sql", "w", encoding="utf-8") as f:
            f.write(seed_sql)

    # Summary markdown
    md = factories_gen.to_markdown()
    with open(factory_dir / "factories_overview.md", "w", encoding="utf-8") as f:
        f.write(md)

    # JSON export (always — for dashboard consumption)
    with open(factory_dir / "factories.json", "w", encoding="utf-8") as f:
        json.dump([ef.to_dict() for ef in factories_gen.factories], f, indent=2, ensure_ascii=False)
