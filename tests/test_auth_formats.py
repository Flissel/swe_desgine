"""Test verschiedene Supermemory Auth-Formate."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

import httpx

key = os.environ.get('SUPERMEMORY_API_KEY')
if not key:
    print('[FAIL] Kein API Key')
    sys.exit(1)

print(f'Key: {key[:15]}...')

# Test verschiedene Header-Formate
headers_options = [
    ('x-api-key', {'x-api-key': key, 'Content-Type': 'application/json'}),
    ('Authorization Bearer', {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}),
    ('api-key', {'api-key': key, 'Content-Type': 'application/json'}),
    ('X-API-Key (uppercase)', {'X-API-Key': key, 'Content-Type': 'application/json'}),
]

for name, headers in headers_options:
    print(f'\nTest: {name}')
    try:
        r = httpx.post(
            'https://v2.api.supermemory.ai/add',
            headers=headers,
            json={'content': 'test', 'containerTag': 'test123'},
            timeout=10
        )
        print(f'  Status: {r.status_code}')
        if r.status_code != 401:
            print(f'  [OK] Funktioniert!')
            print(f'  Response: {r.text[:200]}')
        else:
            print(f'  [FAIL] Unauthorized')
    except Exception as e:
        print(f'  Error: {e}')
