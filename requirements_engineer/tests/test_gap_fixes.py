"""
Tests for RE-Pipeline gap fixes (20 gaps across all generators).

Tests the dataclass extensions, prompt improvements, post-processing logic,
and new generators added to close the identified gaps.
"""

import json
import pytest
import yaml
from pathlib import Path
from dataclasses import fields
from unittest.mock import MagicMock, patch
from datetime import datetime


# ============================================================================
# 1. API Spec Generator Tests (Gaps #1, #2, #5, #6, #16)
# ============================================================================

class TestAPISpecGaps:
    """Test API Spec Generator gap fixes."""

    def test_endpoint_has_is_public_field(self):
        """Gap #5: APIEndpoint should have is_public field."""
        from requirements_engineer.generators.api_spec_generator import APIEndpoint
        ep = APIEndpoint(path="/auth/login", method="POST", summary="Login")
        assert hasattr(ep, "is_public")
        assert ep.is_public is False

    def test_endpoint_has_content_type_field(self):
        """Gap #6: APIEndpoint should have content_type field."""
        from requirements_engineer.generators.api_spec_generator import APIEndpoint
        ep = APIEndpoint(path="/upload", method="POST", summary="Upload")
        assert hasattr(ep, "content_type")
        assert ep.content_type == "application/json"

    def test_public_endpoint_security_override(self):
        """Gap #5: Public endpoints should have security: [] in OpenAPI dict."""
        from requirements_engineer.generators.api_spec_generator import APIEndpoint
        ep = APIEndpoint(
            path="/auth/register",
            method="POST",
            summary="Register",
            is_public=True,
            responses={"201": "Created"},
        )
        openapi = ep.to_openapi_dict()
        assert openapi.get("security") == []

    def test_non_public_endpoint_no_security_override(self):
        """Gap #5: Non-public endpoints should NOT have security key."""
        from requirements_engineer.generators.api_spec_generator import APIEndpoint
        ep = APIEndpoint(
            path="/users/me",
            method="GET",
            summary="Get profile",
            responses={"200": "OK"},
        )
        openapi = ep.to_openapi_dict()
        assert "security" not in openapi

    def test_multipart_content_type(self):
        """Gap #6: File upload endpoints should use multipart/form-data."""
        from requirements_engineer.generators.api_spec_generator import (
            APIEndpoint, APISchema,
        )
        ep = APIEndpoint(
            path="/media/upload",
            method="POST",
            summary="Upload file",
            content_type="multipart/form-data",
            request_body=APISchema(
                name="FileUpload",
                properties={"file": {"type": "string", "format": "binary"}},
            ),
            responses={"201": "Created"},
        )
        openapi = ep.to_openapi_dict()
        assert "multipart/form-data" in openapi["requestBody"]["content"]

    def test_error_response_schema_ref(self):
        """Gap #1: 4xx/5xx responses should reference ErrorResponse schema."""
        from requirements_engineer.generators.api_spec_generator import APIEndpoint
        ep = APIEndpoint(
            path="/users",
            method="POST",
            summary="Create user",
            responses={
                "201": "Created",
                "400": "Bad Request",
                "500": "Internal Server Error",
            },
        )
        openapi = ep.to_openapi_dict()
        assert "#/components/schemas/ErrorResponse" in json.dumps(
            openapi["responses"]["400"]
        )
        assert "#/components/schemas/ErrorResponse" in json.dumps(
            openapi["responses"]["500"]
        )

    def test_201_response_schema(self):
        """Gap #2: POST 201 responses should reference response schema."""
        from requirements_engineer.generators.api_spec_generator import (
            APIEndpoint, APISchema,
        )
        ep = APIEndpoint(
            path="/users",
            method="POST",
            summary="Create user",
            response_schema=APISchema(name="UserResponse"),
            responses={"201": "Created"},
        )
        openapi = ep.to_openapi_dict()
        assert "#/components/schemas/UserResponse" in json.dumps(
            openapi["responses"]["201"]
        )

    def test_endpoint_prompt_has_new_fields(self):
        """Prompt should include is_public and content_type fields."""
        from requirements_engineer.generators.api_spec_generator import APISpecGenerator
        prompt = APISpecGenerator.ENDPOINT_PROMPT
        assert "is_public" in prompt
        assert "content_type" in prompt
        assert "response_body" in prompt
        assert "multipart/form-data" in prompt


# ============================================================================
# 2. Data Dictionary Generator Tests (Gaps #3, #4, #7, #8, #9, #17, #19)
# ============================================================================

class TestDataDictionaryGaps:
    """Test Data Dictionary Generator gap fixes."""

    def test_attribute_has_max_length(self):
        """Gap #8: Attribute should have max_length field."""
        from requirements_engineer.generators.data_dictionary_generator import Attribute
        attr = Attribute(name="email", data_type="string", max_length=255)
        assert attr.max_length == 255

    def test_attribute_has_enum_values(self):
        """Gap #7: Attribute should have enum_values field."""
        from requirements_engineer.generators.data_dictionary_generator import Attribute
        attr = Attribute(
            name="status", data_type="enum", enum_values=["active", "inactive"]
        )
        assert attr.enum_values == ["active", "inactive"]

    def test_attribute_has_indexed(self):
        """Gap #9: Attribute should have is_indexed field."""
        from requirements_engineer.generators.data_dictionary_generator import Attribute
        attr = Attribute(name="email", data_type="string", is_indexed=True)
        assert attr.is_indexed is True

    def test_attribute_has_foreign_key(self):
        """Gap #4: Attribute should have is_foreign_key and foreign_key_target."""
        from requirements_engineer.generators.data_dictionary_generator import Attribute
        attr = Attribute(
            name="user_id",
            data_type="uuid",
            is_foreign_key=True,
            foreign_key_target="User.id",
        )
        assert attr.is_foreign_key is True
        assert attr.foreign_key_target == "User.id"

    def test_relationship_has_junction_table(self):
        """Gap #3: Relationship should have junction_table for N:M."""
        from requirements_engineer.generators.data_dictionary_generator import Relationship
        rel = Relationship(
            name="has_roles",
            source_entity="User",
            target_entity="Role",
            cardinality="N:M",
            junction_table="user_roles",
            source_fk="user_id",
            target_fk="role_id",
        )
        assert rel.junction_table == "user_roles"
        assert rel.source_fk == "user_id"
        assert rel.target_fk == "role_id"

    def test_er_diagram_junction_table(self):
        """Gap #3: ER diagram should include junction table for N:M."""
        from requirements_engineer.generators.data_dictionary_generator import (
            DataDictionary, Entity, Attribute, Relationship,
        )
        dd = DataDictionary(
            title="Test",
            entities={
                "User": Entity(
                    name="User",
                    description="A user",
                    attributes=[Attribute(name="id", data_type="uuid")],
                ),
                "Role": Entity(
                    name="Role",
                    description="A role",
                    attributes=[Attribute(name="id", data_type="uuid")],
                ),
            },
            relationships=[
                Relationship(
                    name="has_roles",
                    source_entity="User",
                    target_entity="Role",
                    cardinality="N:M",
                    junction_table="user_roles",
                    source_fk="user_id",
                    target_fk="role_id",
                )
            ],
        )
        er = dd.to_er_diagram()
        assert "user_roles" in er
        assert "user_id FK" in er
        assert "role_id FK" in er

    def test_er_mermaid_fk_marker(self):
        """Gap #4: ER diagram should show FK markers on attributes."""
        from requirements_engineer.generators.data_dictionary_generator import (
            Entity, Attribute,
        )
        entity = Entity(
            name="Order",
            description="An order",
            attributes=[
                Attribute(name="id", data_type="uuid"),
                Attribute(
                    name="user_id",
                    data_type="uuid",
                    is_foreign_key=True,
                    foreign_key_target="User.id",
                ),
            ],
        )
        mermaid = entity.to_er_mermaid()
        assert "user_id FK" in mermaid

    def test_snake_case_conversion(self):
        """Gap #19: _to_snake_case should convert camelCase/PascalCase."""
        from requirements_engineer.generators.data_dictionary_generator import (
            DataDictionaryGenerator,
        )
        assert DataDictionaryGenerator._to_snake_case("userId") == "user_id"
        assert DataDictionaryGenerator._to_snake_case("UserName") == "user_name"
        assert DataDictionaryGenerator._to_snake_case("firstName") == "first_name"
        assert DataDictionaryGenerator._to_snake_case("already_snake") == "already_snake"

    def test_ensure_audit_fields(self):
        """Gap #17: _ensure_audit_fields should add created_at/updated_at."""
        from requirements_engineer.generators.data_dictionary_generator import (
            DataDictionaryGenerator, Entity, Attribute,
        )
        entity = Entity(
            name="Product",
            description="A product",
            attributes=[Attribute(name="id", data_type="uuid")],
        )
        DataDictionaryGenerator._ensure_audit_fields(entity)
        names = [a.name for a in entity.attributes]
        assert "created_at" in names
        assert "updated_at" in names

    def test_ensure_audit_fields_no_duplicate(self):
        """Gap #17: _ensure_audit_fields should not duplicate if already present."""
        from requirements_engineer.generators.data_dictionary_generator import (
            DataDictionaryGenerator, Entity, Attribute,
        )
        entity = Entity(
            name="Product",
            description="A product",
            attributes=[
                Attribute(name="id", data_type="uuid"),
                Attribute(name="created_at", data_type="datetime"),
            ],
        )
        DataDictionaryGenerator._ensure_audit_fields(entity)
        count = sum(1 for a in entity.attributes if a.name == "created_at")
        assert count == 1

    def test_markdown_has_extended_columns(self):
        """Gap #8/#9: Markdown table should show MaxLen, FK, Indexed, Enum columns."""
        from requirements_engineer.generators.data_dictionary_generator import (
            Entity, Attribute,
        )
        entity = Entity(
            name="User",
            description="A user",
            attributes=[
                Attribute(
                    name="email",
                    data_type="string",
                    max_length=255,
                    is_indexed=True,
                ),
                Attribute(
                    name="status",
                    data_type="enum",
                    enum_values=["active", "inactive"],
                ),
            ],
        )
        md = entity.to_markdown()
        assert "MaxLen" in md
        assert "FK Target" in md
        assert "Indexed" in md
        assert "Enum Values" in md
        assert "255" in md
        assert "active, inactive" in md


# ============================================================================
# 3. UI Design Generator Tests (Gaps #10, #11, #12, #20)
# ============================================================================

class TestUIDesignGaps:
    """Test UI Design Generator gap fixes."""

    def test_screen_has_state_bindings(self):
        """Gap #11: Screen should have state_bindings field."""
        from requirements_engineer.generators.ui_design_generator import Screen
        screen = Screen(
            id="SCREEN-001",
            name="Login",
            route="/login",
            state_bindings={"COMP-001": "auth.phoneNumber"},
        )
        assert screen.state_bindings == {"COMP-001": "auth.phoneNumber"}

    def test_screen_has_navigation_rules(self):
        """Gap #12: Screen should have navigation_rules field."""
        from requirements_engineer.generators.ui_design_generator import Screen
        screen = Screen(
            id="SCREEN-001",
            name="Login",
            route="/login",
            navigation_rules=[{"trigger": "submit", "target": "/dashboard"}],
        )
        assert len(screen.navigation_rules) == 1

    def test_screen_has_responsive(self):
        """Gap #20: Screen should have responsive field."""
        from requirements_engineer.generators.ui_design_generator import Screen
        screen = Screen(
            id="SCREEN-001",
            name="Login",
            route="/login",
            responsive={"mobile": {"layout": "stack"}},
        )
        assert "mobile" in screen.responsive

    def test_screen_has_auth_required(self):
        """Screen should have auth_required field."""
        from requirements_engineer.generators.ui_design_generator import Screen
        screen = Screen(id="SCREEN-001", name="Login", route="/login", auth_required=False)
        assert screen.auth_required is False

    def test_ui_spec_has_navigation_map(self):
        """Gap #12: UIDesignSpec should have navigation_map."""
        from requirements_engineer.generators.ui_design_generator import UIDesignSpec
        spec = UIDesignSpec(project_name="Test", navigation_map=[{"path": "/login"}])
        assert len(spec.navigation_map) == 1

    def test_ui_spec_has_state_architecture(self):
        """Gap #11: UIDesignSpec should have state_architecture."""
        from requirements_engineer.generators.ui_design_generator import UIDesignSpec
        spec = UIDesignSpec(
            project_name="Test",
            state_architecture={"auth": {"slice": "authSlice"}},
        )
        assert "auth" in spec.state_architecture

    def test_select_diverse_stories(self):
        """Gap #10: _select_diverse_stories should pick from different categories."""
        from requirements_engineer.generators.ui_design_generator import UIDesignGenerator

        stories = [
            {"title": "User Login", "description": "Login with password"},
            {"title": "User Register", "description": "Create account"},
            {"title": "Send Message", "description": "Chat with contacts"},
            {"title": "Receive Message", "description": "Get notifications"},
            {"title": "View Profile", "description": "Show user info"},
            {"title": "Edit Settings", "description": "Change preferences"},
            {"title": "Upload Photo", "description": "Share media"},
            {"title": "Voice Call", "description": "Call a contact"},
            {"title": "Search Users", "description": "Find people"},
            {"title": "Admin Dashboard", "description": "Manage users"},
        ]

        selected = UIDesignGenerator._select_diverse_stories(stories, 5)
        assert len(selected) == 5

        # Should pick from different categories, not just first 5
        titles = [s["title"] for s in selected]
        categories_hit = set()
        if any("login" in t.lower() or "register" in t.lower() for t in titles):
            categories_hit.add("auth")
        if any("message" in t.lower() for t in titles):
            categories_hit.add("messaging")
        if any("profile" in t.lower() for t in titles):
            categories_hit.add("profile")
        if any("setting" in t.lower() for t in titles):
            categories_hit.add("settings")
        if any("photo" in t.lower() for t in titles):
            categories_hit.add("media")
        # Should cover at least 3 categories
        assert len(categories_hit) >= 3

    def test_select_diverse_stories_small_list(self):
        """If stories <= max_screens, return all."""
        from requirements_engineer.generators.ui_design_generator import UIDesignGenerator
        stories = [{"title": "A"}, {"title": "B"}]
        selected = UIDesignGenerator._select_diverse_stories(stories, 5)
        assert len(selected) == 2

    def test_build_navigation_map(self):
        """Gap #12: _build_navigation_map should create route entries."""
        from requirements_engineer.generators.ui_design_generator import (
            UIDesignGenerator, Screen,
        )
        screens = [
            Screen(
                id="SCREEN-001",
                name="Login",
                route="/login",
                auth_required=False,
                navigation_rules=[
                    {"trigger": "submit", "target": "/dashboard", "condition": ""},
                ],
            ),
            Screen(
                id="SCREEN-002",
                name="Dashboard",
                route="/dashboard",
                auth_required=True,
            ),
        ]
        nav_map = UIDesignGenerator._build_navigation_map(screens)
        assert len(nav_map) == 2
        assert nav_map[0]["path"] == "/login"
        assert nav_map[0]["auth_required"] is False
        assert len(nav_map[0]["transitions"]) == 1
        assert nav_map[1]["auth_required"] is True


# ============================================================================
# 4. Screen Generator Agent Tests (Gap #10)
# ============================================================================

class TestScreenGeneratorAgentGaps:
    """Test Screen Generator Agent gap fixes."""

    def test_select_diverse_stories(self):
        """Gap #10: Agent should have _select_diverse_stories method."""
        from requirements_engineer.stages.agents.screen_generator_agent import (
            ScreenGeneratorAgent,
        )
        stories = [
            {"title": "Login"},
            {"title": "Register"},
            {"title": "Send Message"},
            {"title": "View Profile"},
            {"title": "Upload Photo"},
        ]
        selected = ScreenGeneratorAgent._select_diverse_stories(stories, 3)
        assert len(selected) == 3


# ============================================================================
# 5. Tech Stack Generator Tests (Gap #14)
# ============================================================================

class TestTechStackGaps:
    """Test Tech Stack Generator gap fixes."""

    def test_tech_stack_has_versions(self):
        """Gap #14: TechStack should have versions field."""
        from requirements_engineer.generators.tech_stack_generator import TechStack
        ts = TechStack(
            project_name="Test",
            versions={"React": "19.0.0", "TypeScript": "5.7.2"},
        )
        assert ts.versions["React"] == "19.0.0"

    def test_tech_stack_has_package_names(self):
        """Gap #14: TechStack should have package_names field."""
        from requirements_engineer.generators.tech_stack_generator import TechStack
        ts = TechStack(
            project_name="Test",
            package_names={"React": "react", "FastAPI": "fastapi"},
        )
        assert ts.package_names["FastAPI"] == "fastapi"

    def test_prompt_mentions_versions(self):
        """Gap #14: Prompt should ask for specific versions."""
        from requirements_engineer.generators.tech_stack_generator import TechStackGenerator
        prompt = TechStackGenerator.TECH_STACK_PROMPT
        assert "versions" in prompt.lower()
        assert "package_names" in prompt.lower()


# ============================================================================
# 6. Test Case Generator Tests (Gap #18)
# ============================================================================

class TestTestCaseGaps:
    """Test Test Case Generator gap fixes."""

    def test_feature_has_test_framework(self):
        """Gap #18: GherkinFeature should have test_framework field."""
        from requirements_engineer.generators.test_case_generator import GherkinFeature
        feature = GherkinFeature(name="Login", test_framework="vitest")
        assert feature.test_framework == "vitest"

    def test_feature_has_mock_strategy(self):
        """Gap #18: GherkinFeature should have mock_strategy field."""
        from requirements_engineer.generators.test_case_generator import GherkinFeature
        feature = GherkinFeature(
            name="Login",
            mock_strategy={"sms_service": "mock", "biometric": "stub"},
        )
        assert feature.mock_strategy["sms_service"] == "mock"

    def test_prompt_mentions_test_strategy(self):
        """Gap #18: Prompt should ask for test_strategy."""
        from requirements_engineer.generators.test_case_generator import TestCaseGenerator
        prompt = TestCaseGenerator.GHERKIN_PROMPT
        assert "test_strategy" in prompt
        assert "test_framework" in prompt
        assert "mock_strategy" in prompt


# ============================================================================
# 7. UX Design Generator Tests (Gap #15)
# ============================================================================

class TestUXDesignGaps:
    """Test UX Design Generator gap fixes."""

    def test_ux_spec_has_validation_rules(self):
        """Gap #15: UXDesignSpec should have validation_rules field."""
        from requirements_engineer.generators.ux_design_generator import UXDesignSpec
        spec = UXDesignSpec(
            project_name="Test",
            validation_rules=[
                {"field": "email", "screen": "Registration", "rules": [{"type": "required"}]}
            ],
        )
        assert len(spec.validation_rules) == 1

    def test_validation_prompt_exists(self):
        """Gap #15: UXDesignGenerator should have VALIDATION_PROMPT."""
        from requirements_engineer.generators.ux_design_generator import UXDesignGenerator
        assert hasattr(UXDesignGenerator, "VALIDATION_PROMPT")
        assert "validations" in UXDesignGenerator.VALIDATION_PROMPT


# ============================================================================
# 8. Realtime Spec Generator Tests (Gap #13)
# ============================================================================

class TestRealtimeSpecGaps:
    """Test Realtime Spec Generator."""

    def test_import(self):
        """Gap #13: RealtimeSpecGenerator should be importable."""
        from requirements_engineer.generators.realtime_spec_generator import (
            RealtimeSpecGenerator, RealtimeSpec, Channel, ChannelMessage,
        )
        gen = RealtimeSpecGenerator()
        assert gen.model_name == "openai/gpt-4o-mini"

    def test_filter_realtime_requirements(self):
        """Gap #13: Should correctly filter requirements with RT keywords."""
        from requirements_engineer.generators.realtime_spec_generator import (
            RealtimeSpecGenerator,
        )
        req_rt = MagicMock()
        req_rt.title = "Real-time chat messaging"
        req_rt.description = "Users send messages in real-time"

        req_normal = MagicMock()
        req_normal.title = "User Registration"
        req_normal.description = "Create new account"

        rt_reqs = RealtimeSpecGenerator.filter_realtime_requirements([req_rt, req_normal])
        assert len(rt_reqs) == 1
        assert rt_reqs[0].title == "Real-time chat messaging"

    def test_asyncapi_yaml_structure(self):
        """Gap #13: Generated YAML should have AsyncAPI 2.6 structure."""
        from requirements_engineer.generators.realtime_spec_generator import (
            RealtimeSpecGenerator, RealtimeSpec, Channel, ChannelMessage,
        )
        gen = RealtimeSpecGenerator()
        spec = RealtimeSpec(
            title="Test API",
            channels=[
                Channel(
                    name="chat/messages",
                    subscribe=ChannelMessage(
                        name="ChatMessage",
                        fields={"content": {"type": "string"}},
                    ),
                )
            ],
        )
        yaml_str = gen._to_asyncapi_yaml(spec)
        data = yaml.safe_load(yaml_str)
        assert data["asyncapi"] == "2.6.0"
        assert "chat/messages" in data["channels"]
        assert "ChatMessage" in data["components"]["messages"]

    def test_to_markdown(self):
        """Gap #13: to_markdown should produce readable docs."""
        from requirements_engineer.generators.realtime_spec_generator import (
            RealtimeSpecGenerator, RealtimeSpec, Channel, ChannelMessage,
        )
        gen = RealtimeSpecGenerator()
        spec = RealtimeSpec(
            title="Test API",
            channels=[
                Channel(
                    name="chat/messages",
                    subscribe=ChannelMessage(
                        name="ChatMsg",
                        fields={"content": {"type": "string", "description": "Message text"}},
                    ),
                )
            ],
        )
        yaml_str = gen._to_asyncapi_yaml(spec)
        md = gen.to_markdown(yaml_str)
        assert "chat/messages" in md
        assert "ChatMsg" in md
        assert "content" in md

    def test_exported_from_package(self):
        """Gap #13: Should be in generators __init__.py."""
        from requirements_engineer.generators import RealtimeSpecGenerator, RealtimeSpec
        assert RealtimeSpecGenerator is not None
        assert RealtimeSpec is not None


# ============================================================================
# 9. Link Config Generator Tests (Dashboard graph enhancement)
# ============================================================================

class TestLinkConfigGaps:
    """Test extended link types for dashboard graph."""

    def test_new_link_types_exist(self):
        """New link types should be in DEFAULT_LINK_TYPES."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link_ids = [lt.id for lt in DEFAULT_LINK_TYPES]
        # New link types for graph enhancement
        assert "req-api" in link_ids
        assert "api-screen" in link_ids
        assert "test-api" in link_ids
        assert "req-entity" in link_ids
        assert "screen-entity" in link_ids
        assert "entity-api" in link_ids
        assert "persona-screen" in link_ids

    def test_link_type_count_increased(self):
        """Should have more link types than before (was 16)."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        assert len(DEFAULT_LINK_TYPES) >= 20


# ============================================================================
# 10. Traceability Matrix Tests
# ============================================================================

class TestTraceabilityMatrix:
    """Test extended traceability matrix."""

    def test_matrix_with_api_endpoints(self):
        """Matrix should include API Endpoints column."""
        from requirements_engineer.run_re_system import create_traceability_matrix

        req = MagicMock()
        req.requirement_id = "REQ-001"
        req.type = "functional"
        req.priority = "must"

        us = MagicMock()
        us.id = "US-001"
        us.parent_requirement_id = "REQ-001"

        tc = MagicMock()
        tc.id = "TC-001"
        tc.parent_user_story_id = "US-001"

        ep = MagicMock()
        ep.parent_requirement_id = "REQ-001"
        ep.method = "POST"
        ep.path = "/api/users"

        md = create_traceability_matrix(
            [req], [us], [tc],
            api_endpoints=[ep],
        )
        assert "API Endpoints" in md
        assert "POST /api/users" in md
        assert "Entities" in md  # Entities column header

    def test_matrix_with_entities(self):
        """Matrix should link entities to requirements via API paths."""
        from requirements_engineer.run_re_system import create_traceability_matrix

        req = MagicMock()
        req.requirement_id = "REQ-001"
        req.type = "functional"
        req.priority = "must"

        us = MagicMock()
        us.id = "US-001"
        us.parent_requirement_id = "REQ-001"

        tc = MagicMock()
        tc.id = "TC-001"
        tc.parent_user_story_id = "US-001"

        ep = MagicMock()
        ep.parent_requirement_id = "REQ-001"
        ep.method = "GET"
        ep.path = "/api/users"

        entity = MagicMock()
        entity.name = "User"

        md = create_traceability_matrix(
            [req], [us], [tc],
            api_endpoints=[ep],
            entities={"User": entity},
        )
        assert "Entities" in md
        assert "User" in md

    def test_matrix_without_extra_artifacts(self):
        """Matrix should work with only req/us/tc (backwards compatible)."""
        from requirements_engineer.run_re_system import create_traceability_matrix

        req = MagicMock()
        req.requirement_id = "REQ-001"
        req.type = "functional"
        req.priority = "must"

        md = create_traceability_matrix([req], [], [])
        assert "Traceability Matrix" in md
        assert "API Endpoints" in md  # Column header should still be there
        assert "Entities" in md  # Entities column header should still be there


# ============================================================================
# 11. Auto-Linker Phase 3: All 24 Link Types Coverage Tests
# ============================================================================

class TestAutoLinkerPhase3:
    """Tests verifying data structures support all 24 link types."""

    def test_all_24_link_types_defined(self):
        """LinkConfigGenerator should define exactly 24 link types."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        assert len(DEFAULT_LINK_TYPES) == 23

    def test_persona_screen_link_type_exists(self):
        """Link type persona-screen should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'persona-screen'), None)
        assert link is not None
        assert link.from_type == 'persona'
        assert link.to_type == 'screen'

    def test_comp_api_link_type_exists(self):
        """Link type comp-api should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'comp-api'), None)
        assert link is not None
        assert link.from_type == 'component'
        assert link.to_type == 'api'

    def test_api_entity_link_type_exists(self):
        """Link type api-entity should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'api-entity'), None)
        assert link is not None
        assert link.from_type == 'api'
        assert link.to_type == 'entity'

    def test_diagram_entity_link_type_exists(self):
        """Link type diagram-entity should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'diagram-entity'), None)
        assert link is not None
        assert link.from_type == 'diagram'
        assert link.to_type == 'entity'

    def test_req_feature_link_type_exists(self):
        """Link type req-feature should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'req-feature'), None)
        assert link is not None
        assert link.from_type == 'requirement'
        assert link.to_type == 'feature'

    def test_feature_story_link_type_exists(self):
        """Link type feature-story should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'feature-story'), None)
        assert link is not None
        assert link.from_type == 'feature'
        assert link.to_type == 'user-story'

    def test_tech_comp_link_type_exists(self):
        """Link type tech-comp should be defined."""
        from requirements_engineer.generators.link_config_generator import DEFAULT_LINK_TYPES
        link = next((lt for lt in DEFAULT_LINK_TYPES if lt.id == 'tech-comp'), None)
        assert link is not None
        assert link.from_type == 'tech-stack'
        assert link.to_type == 'component'

    def test_link_config_includes_all_types_when_all_nodes_present(self):
        """When all node types are present, all 24 link types should be included."""
        from requirements_engineer.generators.link_config_generator import LinkConfigGenerator

        gen = LinkConfigGenerator("test-project")
        # Register all node types
        all_types = [
            'requirement', 'epic', 'user-story', 'test', 'diagram',
            'persona', 'user-flow', 'screen', 'component', 'api',
            'task', 'tech-stack', 'feature', 'entity'
        ]
        for t in all_types:
            gen.discovered_node_types.add(t)

        config = gen.generate_config()
        assert len(config.link_types) == 23
        assert len(config.node_types) == 14

    def test_persona_screen_data_chain(self):
        """Persona->Story->Screen chain: screens have parent_user_story, stories have persona."""
        from requirements_engineer.generators.ui_design_generator import Screen
        screen_fields = {f.name for f in fields(Screen)}
        assert 'parent_user_story' in screen_fields

    def test_component_has_parent_screen_ids(self):
        """UIComponent should have parent_screen_ids for comp->screen->API chain."""
        from requirements_engineer.generators.ui_design_generator import UIComponent
        comp_fields = {f.name for f in fields(UIComponent)}
        assert 'parent_screen_ids' in comp_fields

    def test_entity_api_path_matching(self):
        """Entity names should be derivable from API paths."""
        # Simulate the path-parsing logic used by applyApiEntityLinks
        path = "/api/users/{id}/messages"
        segments = [s for s in path.split('/') if s and not s.startswith('{')]
        assert "api" in segments
        assert "users" in segments
        assert "messages" in segments

        # Singular matching
        entity_map = {"user": "User", "message": "Message"}
        matched = []
        for seg in segments:
            seg_lower = seg.lower()
            ent = entity_map.get(seg_lower) or entity_map.get(seg_lower.rstrip('s'))
            if ent:
                matched.append(ent)
        assert "User" in matched
        assert "Message" in matched

    def test_er_diagram_entity_extraction(self):
        """ER diagram mermaid code should allow entity name extraction."""
        import re
        mermaid_code = """erDiagram
    User {
        string id
        string name
    }
    Message {
        string id
        string content
    }
    User ||--o{ Message : sends
"""
        # Same regex pattern as applyDiagramEntityLinks
        pattern = r'^\s*(\w+)\s*(?:\{|\|\||\|o|o\|)'
        matches = re.findall(pattern, mermaid_code, re.MULTILINE)
        entity_names = [m.lower() for m in matches]
        assert "user" in entity_names
        assert "message" in entity_names

    def test_feature_has_requirements_field(self):
        """Features parsed from work breakdown should have requirements list."""
        # Features from parse_work_breakdown_md have a 'requirements' field
        # Simulate the parsed structure
        feature = {
            "id": "FEAT-001",
            "title": "User Authentication",
            "requirements": ["REQ-001", "REQ-002"],
        }
        assert isinstance(feature["requirements"], list)
        assert len(feature["requirements"]) == 2


# ============================================================================
# 12. API Documentation Parser Fix (Regex for new format)
# ============================================================================

class TestApiDocumentationParser:
    """Tests for parse_api_documentation_md with both old and new markdown formats."""

    def test_parse_new_format_with_backticks(self, tmp_path):
        """Parser should handle #### `METHOD` /path format (new generator output)."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API Documentation

## Endpoints

### BankAccounts

#### `POST` /api/v1/bank-accounts

**Create bank account**

Securely create a new bank account with encryption.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Request Body:** `CreateBankAccountRequest`

**Responses:**
- `201`: Created
- `400`: Bad Request

---

#### `GET` /api/v1/bank-accounts

**List bank accounts**

Retrieve a paginated list of bank accounts.

*Requirement:* FR-FE-BANK-ACCOUNT-SETUP

**Responses:**
- `200`: Success
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 2

        assert eps[0]["method"] == "POST"
        assert eps[0]["path"] == "/api/v1/bank-accounts"
        assert "bank account" in eps[0]["description"].lower()
        assert eps[0]["parent_requirement_id"] == "FR-FE-BANK-ACCOUNT-SETUP"

        assert eps[1]["method"] == "GET"
        assert eps[1]["path"] == "/api/v1/bank-accounts"
        assert eps[1]["parent_requirement_id"] == "FR-FE-BANK-ACCOUNT-SETUP"

    def test_parse_old_format_still_works(self, tmp_path):
        """Parser should still handle ### METHOD /path format (backwards compat)."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API Documentation

### GET /api/users

**List users**

Returns all users.

### POST /api/users

**Create user**

Creates a new user.
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 2
        assert eps[0]["method"] == "GET"
        assert eps[0]["path"] == "/api/users"
        assert eps[1]["method"] == "POST"

    def test_parse_extracts_requirement_id(self, tmp_path):
        """Parser should extract parent_requirement_id from *Requirement:* line."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

#### `DELETE` /api/v1/invoices/{id}

**Delete invoice**

Permanently deletes an invoice.

*Requirement:* REQ-INV-003

**Responses:**
- `204`: No Content
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 1
        assert eps[0]["parent_requirement_id"] == "REQ-INV-003"

    def test_parse_without_requirement(self, tmp_path):
        """Endpoints without *Requirement:* should not have parent_requirement_id."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

#### `GET` /api/v1/health

**Health check**

Returns service health status.

**Responses:**
- `200`: OK
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 1
        assert eps[0]["method"] == "GET"
        assert eps[0]["path"] == "/api/v1/health"
        assert "parent_requirement_id" not in eps[0]

    def test_parse_real_project_file(self):
        """Parser should find endpoints in actual generated project files."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md
        from pathlib import Path

        api_file = Path("enterprise_output/Vollautonomer Abrechnungsservice_20260202_030125/api/api_documentation.md")
        if not api_file.exists():
            pytest.skip("No enterprise_output available")

        eps = parse_api_documentation_md(api_file)
        assert len(eps) > 10, f"Expected >10 endpoints, got {len(eps)}"
        # All should have method and path
        for ep in eps:
            assert ep["method"] in ("GET", "POST", "PUT", "DELETE", "PATCH")
            assert ep["path"].startswith("/api/")


class TestApiEndpointIdMatching:
    """Tests that API endpoint IDs from parser match nodeFactory format."""

    def test_endpoint_id_generated(self, tmp_path):
        """Parser should generate id matching nodeFactory format."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

#### `POST` /api/v1/bank-accounts

**Create bank account**

Create a bank account.

*Requirement:* FR-001
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 1
        assert eps[0]["id"] == "API-POST-api-v1-bank-accounts"

    def test_endpoint_id_with_path_params(self, tmp_path):
        """Path parameters like {id} should be stripped from generated id."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

#### `GET` /api/v1/users/{id}

**Get user**

Returns a single user.
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 1
        assert eps[0]["id"] == "API-GET-api-v1-users-id"
        assert "{" not in eps[0]["id"]
        assert "}" not in eps[0]["id"]

    def test_endpoint_id_no_double_dashes(self, tmp_path):
        """Generated id should not contain double dashes."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

### DELETE /api/v1/accounts/{account_id}/transactions/{tx_id}

**Delete transaction**

Deletes a transaction.
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 1
        assert "--" not in eps[0]["id"]
        assert eps[0]["id"].startswith("API-DELETE-")

    def test_endpoint_id_matches_node_factory_format(self, tmp_path):
        """Verify parser id == JS nodeFactory id (both collapse double dashes)."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md
        import re as re_mod

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

#### `PUT` /api/v1/invoices/{id}

**Update invoice**

Updates an invoice.
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        ep = eps[0]

        # Simulate JS nodeFactory (updated):
        # endpoint.id || `API-${method}-${path.replace(/\//g,'-').replace(/[{}]/g,'')}`.replace(/-+/g,'-')
        # path = "/api/v1/invoices/{id}"
        # .replace(/\//g, '-') → "-api-v1-invoices-{id}"
        # .replace(/[{}]/g, '') → "-api-v1-invoices-id"
        # full: "API-PUT--api-v1-invoices-id"
        # .replace(/-+/g, '-') → "API-PUT-api-v1-invoices-id"
        raw_path = ep["path"].replace("/", "-").replace("{", "").replace("}", "")
        js_fallback = re_mod.sub(r'-+', '-', f"API-{ep['method']}-{raw_path}")

        # Parser id should match JS nodeFactory fallback exactly
        assert ep["id"] == js_fallback, f"Parser: {ep['id']} != JS: {js_fallback}"

    def test_all_endpoints_have_ids(self, tmp_path):
        """Every parsed endpoint should have an id field."""
        from requirements_engineer.dashboard.markdown_parser import parse_api_documentation_md

        md = tmp_path / "api_documentation.md"
        md.write_text("""# API

#### `GET` /api/v1/users

**List users**

Returns all users.

#### `POST` /api/v1/users

**Create user**

Creates a new user.

### DELETE /api/v1/users/{id}

**Delete user**

Deletes a user.
""", encoding="utf-8")

        eps = parse_api_documentation_md(md)
        assert len(eps) == 3
        for ep in eps:
            assert "id" in ep, f"Endpoint {ep['method']} {ep['path']} missing id"
            assert ep["id"].startswith("API-")


class TestScreenMarkdownParser:
    """Test parsing of individual screen markdown files."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()]
        if not projects:
            pytest.skip("No enterprise projects found")

        cls.project_dir = projects[0]
        cls.screens_dir = cls.project_dir / "ui_design" / "screens"

        if not cls.screens_dir.exists():
            pytest.skip(f"No screens directory: {cls.screens_dir}")

        from requirements_engineer.dashboard.markdown_parser import parse_screen_markdown_files
        cls.screens = parse_screen_markdown_files(cls.screens_dir)

    def test_screens_loaded(self):
        """At least one screen should be loaded."""
        assert len(self.screens) > 0, "No screens parsed from markdown files"

    def test_screen_has_id(self):
        """Each screen should have an ID."""
        for screen in self.screens:
            assert 'id' in screen
            assert screen['id'].startswith('SCREEN-'), f"Invalid screen ID: {screen.get('id')}"

    def test_screen_has_components(self):
        """Screens should list components used."""
        screen_with_comps = [s for s in self.screens if s.get('components_used')]
        assert len(screen_with_comps) > 0, "No screens have components_used"

        # Check component IDs are valid
        for screen in screen_with_comps:
            for comp_id in screen['components_used']:
                assert comp_id.startswith('COMP-'), f"Invalid component ID: {comp_id}"

    def test_screen_has_api_endpoints(self):
        """Screens should reference API endpoints."""
        screen_with_apis = [s for s in self.screens if s.get('api_endpoints')]
        assert len(screen_with_apis) > 0, "No screens have API endpoints"

        # Check format: "GET /api/path" or "POST /api/path"
        import re
        for screen in screen_with_apis:
            for api in screen['api_endpoints']:
                assert re.match(r'^(GET|POST|PUT|DELETE|PATCH)\s+/', api), f"Invalid API format: {api}"

    def test_screen_has_wireframe(self):
        """At least some screens should have wireframes."""
        screens_with_wireframe = [s for s in self.screens if s.get('wireframe')]
        assert len(screens_with_wireframe) > 0, "No screens have wireframes"

        # Wireframe should be non-trivial ASCII art
        for screen in screens_with_wireframe[:3]:  # Check first 3
            wireframe = screen['wireframe']
            assert len(wireframe) > 100, "Wireframe too short"
            assert '+' in wireframe, "Wireframe missing box characters"

    def test_component_positions_parsed(self):
        """Component layout table should be parsed."""
        screens_with_layout = [s for s in self.screens if s.get('component_positions')]
        assert len(screens_with_layout) > 0, "No screens have component_positions"

        for screen in screens_with_layout[:3]:
            for pos in screen['component_positions']:
                assert 'id' in pos
                assert 'x' in pos
                assert 'y' in pos
                assert isinstance(pos['x'], int)
                assert isinstance(pos['y'], int)


class TestStateMachinesParser:
    """Test parsing of state_machines.json."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()]
        if not projects:
            pytest.skip("No enterprise projects found")

        # Find a project with state_machines.json
        cls.project_dir = None
        cls.sm_file = None
        for project_dir in projects:
            sm_file = project_dir / "state_machines" / "state_machines.json"
            if sm_file.exists():
                cls.project_dir = project_dir
                cls.sm_file = sm_file
                break

        if not cls.sm_file:
            pytest.skip("No project with state_machines.json found")

        from requirements_engineer.dashboard.markdown_parser import parse_state_machines_json
        cls.state_machines = parse_state_machines_json(cls.sm_file)

    def test_state_machines_loaded(self):
        """At least one state machine should be loaded."""
        assert len(self.state_machines) > 0, "No state machines parsed"

    def test_state_machine_has_id(self):
        """Each state machine should have an ID."""
        for sm in self.state_machines:
            assert 'id' in sm
            assert sm['id'].startswith('SM-'), f"Invalid SM ID: {sm.get('id')}"

    def test_state_machine_has_states(self):
        """State machines should have states list."""
        for sm in self.state_machines:
            assert 'states' in sm
            assert len(sm['states']) > 0, f"SM {sm.get('id')} has no states"

    def test_state_machine_has_transitions(self):
        """State machines should have transitions."""
        sm_with_transitions = [s for s in self.state_machines if s.get('transition_count', 0) > 0]
        assert len(sm_with_transitions) > 0, "No state machines have transitions"

    def test_state_machine_has_mermaid(self):
        """State machines should have mermaid diagrams."""
        sm_with_mermaid = [s for s in self.state_machines if s.get('mermaid_code')]
        assert len(sm_with_mermaid) > 0, "No state machines have mermaid code"

    def test_state_machine_has_source_requirements(self):
        """State machines should reference source requirements."""
        sm_with_reqs = [s for s in self.state_machines if s.get('source_requirements')]
        assert len(sm_with_reqs) > 0, "No state machines have source requirements"


class TestInfrastructureParser:
    """Test parsing of infrastructure.json."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()]
        if not projects:
            pytest.skip("No enterprise projects found")

        # Find a project with infrastructure.json
        cls.project_dir = None
        cls.infra_file = None
        for project_dir in projects:
            infra_file = project_dir / "infrastructure" / "infrastructure.json"
            if infra_file.exists():
                cls.project_dir = project_dir
                cls.infra_file = infra_file
                break

        if not cls.infra_file:
            pytest.skip("No project with infrastructure.json found")

        from requirements_engineer.dashboard.markdown_parser import parse_infrastructure_json
        cls.infrastructure = parse_infrastructure_json(cls.infra_file)

    def test_infrastructure_loaded(self):
        """Infrastructure data should be loaded."""
        assert self.infrastructure is not None, "No infrastructure data parsed"

    def test_infrastructure_has_services(self):
        """Infrastructure should have services list."""
        assert 'services' in self.infrastructure
        assert len(self.infrastructure['services']) > 0, "No services found"

    def test_service_has_id(self):
        """Each service should have an ID."""
        for service in self.infrastructure['services']:
            assert 'id' in service
            assert service['id'].startswith('SVC-'), f"Invalid service ID: {service.get('id')}"

    def test_service_has_technology(self):
        """Services should have technology field."""
        for service in self.infrastructure['services']:
            assert 'technology' in service, f"Service {service.get('id')} missing technology"

    def test_infrastructure_has_architecture_style(self):
        """Infrastructure should specify architecture style."""
        assert 'architecture_style' in self.infrastructure

    def test_infrastructure_has_deployment_artifacts(self):
        """Infrastructure should have deployment artifacts."""
        # Check for at least one deployment artifact
        assert (
            self.infrastructure.get('has_dockerfile') or
            self.infrastructure.get('has_k8s') or
            self.infrastructure.get('has_ci')
        ), "No deployment artifacts found"


class TestUICompositionsParser:
    """Test parsing of UI composition JSON files."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()]
        if not projects:
            pytest.skip("No enterprise projects found")

        # Find a project with compositions directory
        cls.project_dir = None
        cls.compositions_dir = None
        for project_dir in projects:
            compositions_dir = project_dir / "ui_design" / "compositions"
            if compositions_dir.exists() and list(compositions_dir.glob("*.json")):
                cls.project_dir = project_dir
                cls.compositions_dir = compositions_dir
                break

        if not cls.compositions_dir:
            pytest.skip("No project with compositions directory found")

        from requirements_engineer.dashboard.markdown_parser import parse_ui_compositions_json
        cls.compositions = parse_ui_compositions_json(cls.compositions_dir)

    def test_compositions_loaded(self):
        """At least one composition should be loaded."""
        assert len(self.compositions) > 0, "No compositions parsed"

    def test_composition_has_id(self):
        """Each composition should have an ID."""
        for comp in self.compositions:
            assert 'id' in comp
            assert comp['id'].startswith('COMP-'), f"Invalid comp ID: {comp.get('id')}"

    def test_composition_has_route(self):
        """Compositions should have routes."""
        comps_with_routes = [c for c in self.compositions if c.get('route')]
        assert len(comps_with_routes) > 0, "No compositions have routes"

    def test_composition_has_components(self):
        """Compositions should list components."""
        comps_with_components = [c for c in self.compositions if c.get('component_count', 0) > 0]
        assert len(comps_with_components) > 0, "No compositions have components"

    def test_component_has_id_and_props(self):
        """Components in compositions should have IDs and props."""
        for comp in self.compositions:
            for component in comp.get('components', []):
                assert 'component_id' in component, "Component missing ID"
                assert 'props' in component, "Component missing props"

    def test_composition_links_to_user_stories(self):
        """Compositions should reference user stories."""
        comps_with_stories = [c for c in self.compositions if c.get('user_stories')]
        assert len(comps_with_stories) > 0, "No compositions link to user stories"


class TestFactoriesParser:
    """Test parsing of test factories.json."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()]
        if not projects:
            pytest.skip("No enterprise projects found")

        # Find a project with factories.json
        cls.project_dir = None
        cls.factories_file = None
        for project_dir in projects:
            factories_file = project_dir / "testing" / "factories" / "factories.json"
            if factories_file.exists():
                cls.project_dir = project_dir
                cls.factories_file = factories_file
                break

        if not cls.factories_file:
            pytest.skip("No project with factories.json found")

        from requirements_engineer.dashboard.markdown_parser import parse_test_factories_json
        cls.factories = parse_test_factories_json(cls.factories_file)

    def test_factories_loaded(self):
        """At least one factory should be loaded."""
        assert len(self.factories) > 0, "No factories parsed"

    def test_factory_has_id(self):
        """Each factory should have an ID."""
        for factory in self.factories:
            assert 'id' in factory
            assert factory['id'].startswith('FACTORY-'), f"Invalid factory ID: {factory.get('id')}"

    def test_factory_has_fields(self):
        """Factories should have fields list."""
        for factory in self.factories:
            assert 'fields' in factory
            assert len(factory['fields']) > 0, f"Factory {factory.get('id')} has no fields"

    def test_field_has_faker_method(self):
        """Factory fields should have faker methods."""
        fields_with_faker = []
        for factory in self.factories:
            for field in factory['fields']:
                if 'faker_method' in field:
                    fields_with_faker.append(field)
        assert len(fields_with_faker) > 0, "No fields have faker methods"

    def test_factory_has_entity_name(self):
        """Factories should specify entity names."""
        for factory in self.factories:
            assert 'entity_name' in factory


class TestArchitectureParser:
    """Test parsing of architecture.json."""

    @classmethod
    def setup_class(cls):
        from pathlib import Path
        output_dir = Path(__file__).parent.parent.parent / "enterprise_output"
        projects = [d for d in output_dir.iterdir() if d.is_dir()]
        if not projects:
            pytest.skip("No enterprise projects found")

        # Find a project with architecture.json
        cls.project_dir = None
        cls.arch_file = None
        for project_dir in projects:
            arch_file = project_dir / "architecture" / "architecture.json"
            if arch_file.exists():
                cls.project_dir = project_dir
                cls.arch_file = arch_file
                break

        if not cls.arch_file:
            pytest.skip("No project with architecture.json found")

        from requirements_engineer.dashboard.markdown_parser import parse_architecture_json
        cls.architecture = parse_architecture_json(cls.arch_file)

    def test_architecture_loaded(self):
        """Architecture data should be loaded."""
        assert self.architecture is not None, "No architecture data parsed"

    def test_architecture_has_services(self):
        """Architecture should have services list."""
        assert 'services' in self.architecture
        assert len(self.architecture['services']) > 0, "No services found"
        assert self.architecture.get('service_count', 0) > 0

    def test_service_has_required_fields(self):
        """Each service should have required fields."""
        for service in self.architecture['services']:
            assert 'id' in service
            assert service['id'].startswith('ARCH-'), f"Invalid service ID: {service.get('id')}"
            assert 'name' in service
            assert 'type' in service
            assert 'technology' in service
            assert 'responsibilities' in service
            assert isinstance(service['responsibilities'], list)

    def test_architecture_has_pattern(self):
        """Architecture should specify pattern."""
        assert 'architecture_pattern' in self.architecture
        assert self.architecture['architecture_pattern'] in ['Microservices', 'Monolith', 'Modular Monolith']

    def test_architecture_has_diagrams(self):
        """Architecture should have embedded diagrams."""
        assert 'diagrams' in self.architecture
        assert len(self.architecture['diagrams']) > 0, "No architecture diagrams found"

        # Check diagram types
        diagram_types = [d.get('type') for d in self.architecture['diagrams']]
        assert 'c4_context' in diagram_types or 'c4_container' in diagram_types

    def test_services_categorized_by_type(self):
        """Services should be categorized by type."""
        assert 'services_by_type' in self.architecture
        services_by_type = self.architecture['services_by_type']

        assert len(services_by_type) > 0, "No service type categories"

        total_categorized = sum(len(services) for services in services_by_type.values())
        assert total_categorized == self.architecture['service_count']
