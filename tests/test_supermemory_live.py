"""Live Test mit echtem Supermemory API."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lade .env falls vorhanden
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass


async def test_supermemory_live():
    from requirements_engineer.memory.supermemory_client import SupermemoryClient

    api_key = os.environ.get('SUPERMEMORY_API_KEY')
    if not api_key or api_key == 'your-supermemory-api-key-here':
        print('[FAIL] Kein gueltiger SUPERMEMORY_API_KEY gefunden')
        print('       Setze SUPERMEMORY_API_KEY in .env oder Environment')
        return 1

    print(f'[OK] API Key gefunden: {api_key[:10]}...')

    client = SupermemoryClient(api_key=api_key)

    # 1. Neuen User erstellen
    print('\n1. Erstelle neuen User...')
    user_tag = await client.create_user(project_id='test_dedup')
    print(f'   [OK] User erstellt: {user_tag}')

    # 2. Test Story speichern
    print('\n2. Speichere Test Story...')
    story_text = 'Als Benutzer moechte ich mich einloggen um auf mein Konto zuzugreifen'
    memory_id = await client.add_story('US-TEST-001', story_text, 'REQ-TEST-001')
    print(f'   [OK] Story gespeichert: {memory_id}')

    # 3. Nach Duplikat suchen (sollte gefunden werden)
    print('\n3. Suche nach aehnlicher Story...')
    similar_text = 'Als Kunde moechte ich mich anmelden um mein Benutzerkonto zu sehen'
    result = await client.search_similar_story(similar_text)
    print(f'   is_duplicate: {result.is_duplicate}')
    print(f'   similarity_score: {result.similarity_score:.2%}')
    print(f'   existing_story_id: {result.existing_story_id}')

    # 4. Link hinzufuegen wenn Duplikat
    if result.is_duplicate:
        print('\n4. Fuege Link hinzu...')
        success = await client.update_story_links(
            result.existing_story_id,
            'REQ-TEST-002',
            result.linked_requirements
        )
        print(f'   [OK] Link hinzugefuegt: {success}')
    else:
        print('\n4. Kein Duplikat gefunden (Similarity unter Threshold)')

    # 5. Liste Stories im User-Space
    print('\n5. Liste alle Stories...')
    stories = await client.list_user_stories()
    print(f'   Gefunden: {len(stories)} Stories')

    await client.close()
    print('\n' + '=' * 50)
    print('[OK] Supermemory Live Test erfolgreich!')
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(test_supermemory_live()))
