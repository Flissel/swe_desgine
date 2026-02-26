import urllib.request
import json
import urllib.parse

project_id = 'Vollautonomer Abrechnungsservice_20260202_030125'
url = f'http://localhost:8085/api/projects/{urllib.parse.quote(project_id)}'
r = urllib.request.urlopen(url)
d = json.loads(r.read())

print('=== Requirements (first 5) ===')
for r in d.get('requirements', [])[:5]:
    print(f"  {r['id']}: {r['title'][:40]}...")

print()
print('=== User Stories (first 5) ===')
for us in d.get('user_stories', [])[:5]:
    print(f"  {us['id']}: linked_requirement={us.get('linked_requirement')}")

print()
print('=== Tests (first 5) ===')
for t in d.get('tests', [])[:5]:
    print(f"  {t['id']}: linked_user_story={t.get('linked_user_story')}")

print()
print('=== Traceability (first 3) ===')
for tr in d.get('traceability', [])[:3]:
    tests = tr.get('test_cases', [])[:3] if tr.get('test_cases') else []
    print(f"  req={tr['req_id']}, us={tr.get('user_stories')}, tests={tests}...")

print()
print('=== Epics (first 3) ===')
for e in d.get('epics', [])[:3]:
    print(f"  {e['id']}: linked_reqs={e.get('linked_requirements', [])[:3]}, linked_stories={e.get('linked_user_stories', [])[:3]}")
