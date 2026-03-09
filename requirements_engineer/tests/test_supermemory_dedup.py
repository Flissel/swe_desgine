"""
Tests für die Supermemory User Story Deduplizierung.

Testet:
1. SupermemoryClient Import und Initialisierung
2. UserStoryGenerator mit Deduplizierung
3. UserStory Dataclass Erweiterungen
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_supermemory_client_import():
    """Test: SupermemoryClient kann importiert werden."""
    print("Test 1: SupermemoryClient Import...")
    try:
        from requirements_engineer.memory.supermemory_client import (
            SupermemoryClient,
            DeduplicationResult
        )
        print("  [OK] Import erfolgreich")
        return True
    except ImportError as e:
        print(f"  [FAIL] Import fehlgeschlagen: {e}")
        return False


def test_supermemory_client_init():
    """Test: SupermemoryClient Initialisierung ohne API Key."""
    print("\nTest 2: SupermemoryClient Initialisierung...")
    try:
        from requirements_engineer.memory.supermemory_client import SupermemoryClient

        # Ohne API Key (sollte Warning loggen, aber nicht crashen)
        client = SupermemoryClient(api_key=None)
        print(f"  [OK] Client erstellt mit container_tag: {client.container_tag}")
        print(f"  [OK] Similarity threshold: {client.similarity_threshold}")
        return True
    except Exception as e:
        print(f"  [FAIL] Initialisierung fehlgeschlagen: {e}")
        return False


def test_deduplication_result():
    """Test: DeduplicationResult Dataclass."""
    print("\nTest 3: DeduplicationResult Dataclass...")
    try:
        from requirements_engineer.memory.supermemory_client import DeduplicationResult

        # Kein Duplikat
        result1 = DeduplicationResult(is_duplicate=False)
        print(f"  [OK] Kein Duplikat: {result1}")

        # Duplikat gefunden
        result2 = DeduplicationResult(
            is_duplicate=True,
            existing_story_id="US-001",
            similarity_score=0.92,
            linked_requirements=["REQ-001", "REQ-002"]
        )
        print(f"  [OK] Duplikat: {result2}")
        return True
    except Exception as e:
        print(f"  [FAIL] DeduplicationResult fehlgeschlagen: {e}")
        return False


def test_user_tag_generation():
    """Test: User Tag Generierung."""
    print("\nTest 4: User Tag Generierung...")
    try:
        from requirements_engineer.memory.supermemory_client import SupermemoryClient

        tag1 = SupermemoryClient.generate_user_tag()
        print(f"  [OK] Default Tag: {tag1}")

        tag2 = SupermemoryClient.generate_user_tag(project_id="freight", user_id="test123")
        print(f"  [OK] Custom Tag: {tag2}")

        assert tag1.startswith("sw_eng_"), "Tag sollte mit sw_eng_ beginnen"
        assert "freight" in tag2, "Tag sollte project_id enthalten"
        print("  [OK] Tag Format korrekt")
        return True
    except Exception as e:
        print(f"  [FAIL] Tag Generierung fehlgeschlagen: {e}")
        return False


def test_user_story_generator_import():
    """Test: UserStoryGenerator Import mit Deduplizierung."""
    print("\nTest 5: UserStoryGenerator Import...")
    try:
        from requirements_engineer.generators.user_story_generator import (
            UserStoryGenerator,
            UserStory,
            AcceptanceCriterion
        )
        print("  [OK] Import erfolgreich")
        return True
    except ImportError as e:
        print(f"  [FAIL] Import fehlgeschlagen: {e}")
        return False


def test_user_story_generator_init():
    """Test: UserStoryGenerator Initialisierung mit Deduplizierung."""
    print("\nTest 6: UserStoryGenerator Initialisierung...")
    try:
        from requirements_engineer.generators.user_story_generator import UserStoryGenerator

        # Mit Deduplizierung
        generator = UserStoryGenerator(
            enable_deduplication=True,
            similarity_threshold=0.85,
            project_id="test_project"
        )
        print(f"  [OK] Generator erstellt")
        print(f"  [OK] Deduplication enabled: {generator.enable_deduplication}")
        print(f"  [OK] Supermemory client: {'Ja' if generator.supermemory else 'Nein (kein API Key)'}")
        print(f"  [OK] Project ID: {generator.project_id}")
        return True
    except Exception as e:
        print(f"  [FAIL] Initialisierung fehlgeschlagen: {e}")
        return False


def test_user_story_dataclass():
    """Test: UserStory Dataclass mit neuen Feldern."""
    print("\nTest 7: UserStory Dataclass Erweiterungen...")
    try:
        from requirements_engineer.generators.user_story_generator import (
            UserStory,
            AcceptanceCriterion
        )

        # Normale Story
        story1 = UserStory(
            id="US-001",
            title="Test Story",
            persona="user",
            action="do something",
            benefit="achieve goal",
            parent_requirement_id="REQ-001"
        )
        print(f"  [OK] Normale Story erstellt: {story1.id}")
        print(f"    linked_requirement_ids: {story1.linked_requirement_ids}")
        print(f"    is_merged: {story1.is_merged}")

        # Merged Story
        story2 = UserStory(
            id="US-002",
            title="Merged Story",
            persona="admin",
            action="manage users",
            benefit="maintain system",
            parent_requirement_id="REQ-002",
            linked_requirement_ids=["REQ-002", "REQ-003", "REQ-004"],
            is_merged=True,
            merge_count=3
        )
        print(f"  [OK] Merged Story erstellt: {story2.id}")
        print(f"    linked_requirement_ids: {story2.linked_requirement_ids}")
        print(f"    is_merged: {story2.is_merged}")
        print(f"    merge_count: {story2.merge_count}")

        # Test Markdown Output
        md = story2.to_markdown()
        assert "Linked Requirements:" in md, "Markdown sollte Linked Requirements enthalten"
        assert "Merged from 3 requirements" in md, "Markdown sollte Merge-Info enthalten"
        print("  [OK] Markdown Output korrekt")

        return True
    except Exception as e:
        print(f"  [FAIL] UserStory Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_supermemory_client_async():
    """Test: Async Methoden des SupermemoryClient (ohne echten API Call)."""
    print("\nTest 8: SupermemoryClient Async Methoden...")
    try:
        from requirements_engineer.memory.supermemory_client import SupermemoryClient

        client = SupermemoryClient(api_key=None)  # Kein API Key = keine echten Calls

        # Test search (sollte False zurückgeben ohne API Key)
        result = await client.search_similar_story("Test story text")
        print(f"  [OK] search_similar_story: is_duplicate={result.is_duplicate}")
        assert not result.is_duplicate, "Ohne API Key sollte kein Duplikat gefunden werden"

        # Test add (sollte None zurückgeben ohne API Key)
        memory_id = await client.add_story("US-001", "Test story", "REQ-001")
        print(f"  [OK] add_story: memory_id={memory_id}")
        assert memory_id is None, "Ohne API Key sollte keine Memory-ID zurückkommen"

        # Test update (sollte False zurückgeben ohne API Key)
        success = await client.update_story_links("US-001", "REQ-002", ["REQ-001"])
        print(f"  [OK] update_story_links: success={success}")
        assert not success, "Ohne API Key sollte Update fehlschlagen"

        await client.close()
        print("  [OK] Client geschlossen")
        return True
    except Exception as e:
        print(f"  [FAIL] Async Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Führe alle Tests aus."""
    print("=" * 60)
    print("Supermemory User Story Deduplizierung - Tests")
    print("=" * 60)

    results = []

    # Synchrone Tests
    results.append(("Import SupermemoryClient", test_supermemory_client_import()))
    results.append(("Init SupermemoryClient", test_supermemory_client_init()))
    results.append(("DeduplicationResult", test_deduplication_result()))
    results.append(("User Tag Generation", test_user_tag_generation()))
    results.append(("Import UserStoryGenerator", test_user_story_generator_import()))
    results.append(("Init UserStoryGenerator", test_user_story_generator_init()))
    results.append(("UserStory Dataclass", test_user_story_dataclass()))

    # Async Tests
    results.append(("Async Methods", asyncio.run(test_supermemory_client_async())))

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)

    for name, result in results:
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"  {status}: {name}")

    print(f"\nErgebnis: {passed}/{len(results)} Tests bestanden")

    if failed == 0:
        print("\n[OK] Alle Tests erfolgreich!")
        return 0
    else:
        print(f"\n[FAIL] {failed} Test(s) fehlgeschlagen!")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
