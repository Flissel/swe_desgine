"""Tests for the 5 factory generator bug fixes.

Bug 1: FK refs use .id but entities have named PKs
Bug 2: _to_class_name() re-applied corrupts PascalCase FK names
Bug 3: *_url, emoji fields get faker.lorem.words(3)
Bug 4: Self-referencing FK causes infinite recursion
Bug 5: Non-FK ID-suffix fields get lorem instead of UUID
"""

import pytest
from unittest.mock import MagicMock
from requirements_engineer.generators.test_factory_generator import (
    TestFactoryGenerator, EntityFactory, FieldFactory,
    _to_class_name, _to_camel_case, _suffix_faker, _id_suffix_faker,
)


def _make_entity(name, fields, deps=None):
    """Helper: create an EntityFactory with FieldFactory list."""
    return EntityFactory(
        entity_name=name,
        table_name=name.lower(),
        fields=[FieldFactory(**f) for f in fields],
        dependencies=deps or [],
    )


@pytest.fixture
def gen_with_chat_schema():
    """Generator with User and GroupChat entities (FK between them)."""
    gen = TestFactoryGenerator()
    gen.lang = "node.js"
    gen.db = "postgresql"
    gen.factories = [
        _make_entity("User", [
            {"name": "user_id", "data_type": "uuid"},
            {"name": "email", "data_type": "string"},
            {"name": "created_at", "data_type": "datetime"},
        ]),
        _make_entity("GroupChat", [
            {"name": "group_chat_id", "data_type": "uuid"},
            {"name": "group_name", "data_type": "string"},
            {"name": "created_at", "data_type": "datetime"},
        ]),
        _make_entity("GroupMember", [
            {"name": "group_member_id", "data_type": "uuid"},
            {"name": "group_chat_id", "data_type": "uuid", "is_fk": True,
             "fk_factory": "GroupChatFactory"},
            {"name": "user_id", "data_type": "uuid", "is_fk": True,
             "fk_factory": "UserFactory"},
            {"name": "role", "data_type": "string"},
        ], deps=["GroupChat", "User"]),
    ]
    return gen


@pytest.fixture
def gen_with_self_ref():
    """Generator with a self-referencing entity (Message.parent_message_id → Message)."""
    gen = TestFactoryGenerator()
    gen.lang = "node.js"
    gen.db = "postgresql"
    gen.factories = [
        _make_entity("Message", [
            {"name": "message_id", "data_type": "uuid"},
            {"name": "content", "data_type": "text"},
            {"name": "parent_message_id", "data_type": "uuid", "is_fk": True,
             "fk_factory": "MessageFactory"},
        ]),
    ]
    return gen


@pytest.fixture
def gen_with_url_fields():
    """Generator with fields that should match suffix-based faker."""
    gen = TestFactoryGenerator()
    gen.lang = "node.js"
    gen.db = "postgresql"
    gen.factories = [
        _make_entity("MediaItem", [
            {"name": "media_id", "data_type": "uuid"},
            {"name": "media_url", "data_type": "string"},
            {"name": "file_url", "data_type": "string"},
            {"name": "emoji", "data_type": "string"},
            {"name": "sender_user_id", "data_type": "string"},  # non-FK ID field
        ]),
    ]
    return gen


# ── Bug 1: FK PK field resolution ────────────────────────────────────────────

class TestFix1_FKPKResolution:
    def test_ts_fk_uses_named_pk(self, gen_with_chat_schema):
        ts = gen_with_chat_schema.to_typescript_factories()
        # GroupMember.group_chat_id should use createGroupChat().groupChatId
        assert "createGroupChat().groupChatId" in ts
        # GroupMember.user_id should use createUser().userId
        assert "createUser().userId" in ts

    def test_ts_fk_does_not_use_dot_id(self, gen_with_chat_schema):
        ts = gen_with_chat_schema.to_typescript_factories()
        # No .id references (except in interface property definitions)
        lines = [l for l in ts.split("\n") if "create" in l and ".id" in l]
        assert lines == [], f"Found .id in factory calls: {lines}"

    def test_go_fk_uses_named_pk(self, gen_with_chat_schema):
        gen_with_chat_schema.lang = "go"
        go = gen_with_chat_schema.to_go_factories()
        assert "NewGroupChat().GroupChatId" in go
        assert "NewUser().UserId" in go

    def test_java_fk_uses_named_pk(self, gen_with_chat_schema):
        gen_with_chat_schema.lang = "java"
        java = gen_with_chat_schema.to_java_factories()
        assert "createGroupChat().groupChatId" in java
        assert "createUser().userId" in java

    def test_get_pk_field_returns_first_uuid(self, gen_with_chat_schema):
        pk = gen_with_chat_schema._get_pk_field("User")
        assert pk == "user_id"

    def test_get_pk_field_unknown_entity_returns_id(self, gen_with_chat_schema):
        pk = gen_with_chat_schema._get_pk_field("NonExistent")
        assert pk == "id"


# ── Bug 2: _to_class_name FK name corruption ────────────────────────────────

class TestFix2_FKNameCasing:
    def test_ts_calls_createGroupChat_not_createGroupchat(self, gen_with_chat_schema):
        ts = gen_with_chat_schema.to_typescript_factories()
        assert "createGroupChat(" in ts
        assert "createGroupchat(" not in ts

    def test_go_calls_NewGroupChat_not_NewGroupchat(self, gen_with_chat_schema):
        gen_with_chat_schema.lang = "go"
        go = gen_with_chat_schema.to_go_factories()
        assert "NewGroupChat()" in go
        assert "NewGroupchat()" not in go

    def test_java_calls_createGroupChat_not_createGroupchat(self, gen_with_chat_schema):
        gen_with_chat_schema.lang = "java"
        java = gen_with_chat_schema.to_java_factories()
        assert "createGroupChat()" in java
        assert "createGroupchat()" not in java


# ── Bug 3: Suffix-based faker matching ───────────────────────────────────────

class TestFix3_SuffixFaker:
    def test_media_url_gets_internet_url(self, gen_with_url_fields):
        ts = gen_with_url_fields.to_typescript_factories()
        assert "mediaUrl: faker.internet.url()" in ts

    def test_file_url_gets_internet_url(self, gen_with_url_fields):
        ts = gen_with_url_fields.to_typescript_factories()
        assert "fileUrl: faker.internet.url()" in ts

    def test_emoji_gets_internet_emoji(self, gen_with_url_fields):
        ts = gen_with_url_fields.to_typescript_factories()
        assert "emoji: faker.internet.emoji()" in ts

    def test_no_lorem_words_for_urls(self, gen_with_url_fields):
        ts = gen_with_url_fields.to_typescript_factories()
        # mediaUrl and fileUrl should NOT use faker.lorem.words
        for line in ts.split("\n"):
            if "Url:" in line and "faker.lorem" in line:
                pytest.fail(f"URL field using lorem: {line.strip()}")

    def test_suffix_faker_url(self):
        assert _suffix_faker("media_url", "js") == "faker.internet.url()"
        assert _suffix_faker("profile_image_url", "js") == "faker.internet.url()"
        assert _suffix_faker("url", "js") == "faker.internet.url()"

    def test_suffix_faker_email(self):
        assert _suffix_faker("contact_email", "js") == "faker.internet.email()"

    def test_suffix_faker_no_match(self):
        assert _suffix_faker("description", "js") is None

    def test_go_suffix_faker(self, gen_with_url_fields):
        gen_with_url_fields.lang = "go"
        go = gen_with_url_fields.to_go_factories()
        assert "gofakeit.URL()" in go

    def test_java_suffix_faker(self, gen_with_url_fields):
        gen_with_url_fields.lang = "java"
        java = gen_with_url_fields.to_java_factories()
        assert "faker.internet().url()" in java


# ── Bug 4: Self-referencing FK ───────────────────────────────────────────────

class TestFix4_SelfReference:
    def test_ts_self_ref_is_null(self, gen_with_self_ref):
        ts = gen_with_self_ref.to_typescript_factories()
        assert "parentMessageId: null" in ts

    def test_ts_self_ref_no_recursive_call(self, gen_with_self_ref):
        ts = gen_with_self_ref.to_typescript_factories()
        # createMessage should NOT call createMessage() for parentMessageId
        lines = [l for l in ts.split("\n") if "parentMessageId" in l and "createMessage()" in l]
        assert lines == [], f"Self-reference calling factory: {lines}"

    def test_go_self_ref_is_empty_string(self, gen_with_self_ref):
        gen_with_self_ref.lang = "go"
        go = gen_with_self_ref.to_go_factories()
        assert 'ParentMessageId: ""' in go

    def test_java_self_ref_is_null(self, gen_with_self_ref):
        gen_with_self_ref.lang = "java"
        java = gen_with_self_ref.to_java_factories()
        assert "obj.parentMessageId = null;" in java


# ── Bug 5: ID-suffix fields → UUID ──────────────────────────────────────────

class TestFix5_IDSuffixUUID:
    def test_sender_user_id_gets_uuid(self, gen_with_url_fields):
        ts = gen_with_url_fields.to_typescript_factories()
        assert "senderUserId: faker.string.uuid()" in ts

    def test_id_suffix_faker_helper(self):
        ff = FieldFactory(name="sender_user_id", data_type="string")
        assert _id_suffix_faker(ff, "js") == "faker.string.uuid()"
        assert _id_suffix_faker(ff, "go") == "uuid.New().String()"
        assert _id_suffix_faker(ff, "java") == "UUID.randomUUID().toString()"

    def test_id_suffix_not_applied_to_fk(self):
        ff = FieldFactory(name="user_id", data_type="uuid", is_fk=True,
                          fk_factory="UserFactory")
        assert _id_suffix_faker(ff, "js") is None

    def test_id_suffix_not_applied_to_non_uuid_types(self):
        ff = FieldFactory(name="some_id", data_type="integer")
        assert _id_suffix_faker(ff, "js") is None

    def test_go_id_suffix(self, gen_with_url_fields):
        gen_with_url_fields.lang = "go"
        go = gen_with_url_fields.to_go_factories()
        assert "uuid.New().String()" in go

    def test_java_id_suffix(self, gen_with_url_fields):
        gen_with_url_fields.lang = "java"
        java = gen_with_url_fields.to_java_factories()
        assert "UUID.randomUUID().toString()" in java
