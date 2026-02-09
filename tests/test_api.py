#!/usr/bin/env python
"""Test script for dashboard API."""
import json
from pathlib import Path

output_dir = Path('enterprise_output')
projects = []

for project_dir in sorted(output_dir.iterdir(), reverse=True):
    if project_dir.is_dir():
        journal_path = project_dir / 'journal.json'
        if journal_path.exists():
            with open(journal_path, encoding='utf-8') as f:
                journal = json.load(f)
            parts = project_dir.name.rsplit('_', 2)
            created = f'{parts[-2]}_{parts[-1]}' if len(parts) >= 3 else project_dir.name
            projects.append({
                'id': project_dir.name,
                'name': journal.get('project_name', project_dir.name),
                'node_count': len(journal.get('nodes', {})),
                'created': created
            })

print('API Response would be:')
print(json.dumps({'projects': projects}, indent=2, ensure_ascii=False))
