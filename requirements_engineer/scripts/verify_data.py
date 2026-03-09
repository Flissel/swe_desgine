"""Quick verification script for data loading."""
import json
from pathlib import Path

project_dir = Path('enterprise_output/whatsapp-messaging-service_20260211_025459')

# Check API spec
api_path = project_dir / 'api' / 'openapi_spec.json'
if api_path.exists():
    with open(api_path) as f:
        spec = json.load(f)
    paths = spec.get('paths', {})
    endpoints = []
    for path_str, methods in paths.items():
        for method, detail in methods.items():
            if method.lower() in ('get','post','put','delete','patch','options','head'):
                endpoints.append({'path': path_str, 'method': method.upper()})
    print(f'Total API endpoints: {len(endpoints)}')

    # Group by resource
    pkgs = {}
    for ep in endpoints:
        path = ep['path']
        segments = [s for s in path.strip('/').split('/') if s and not s.startswith('{')]
        resource = segments[0] if segments else 'root'
        pkgs.setdefault(resource, []).append(ep)
    print(f'API packages: {len(pkgs)}')
    for tag in sorted(pkgs.keys()):
        print(f'  {tag}: {len(pkgs[tag])} endpoints')

# Check tasks
task_path = project_dir / 'tasks' / 'task_breakdown.json'
if task_path.exists():
    with open(task_path) as f:
        td = json.load(f)
    if isinstance(td, dict):
        features = td.get('features', td)
        if isinstance(features, list):
            print(f'Tasks: flat list of {len(features)}')
        elif isinstance(features, dict):
            print(f'Task features: {len(features)} groups')
            for fid in list(features.keys())[:5]:
                tasks_list = features[fid]
                if isinstance(tasks_list, list):
                    print(f'  {fid}: {len(tasks_list)} tasks')
    elif isinstance(td, list):
        print(f'Tasks: flat list of {len(td)}')

# Check services
arch_path = project_dir / 'architecture' / 'architecture.json'
if arch_path.exists():
    with open(arch_path) as f:
        arch = json.load(f)
    svcs = arch.get('services', [])
    print(f'Services: {len(svcs)}')
    for s in svcs[:3]:
        print(f'  - {s.get("id", s.get("name", "?"))}')

# Check state machines
sm_path = project_dir / 'state_machines'
if sm_path.exists():
    sm_files = list(sm_path.glob('*.json'))
    print(f'State machine JSON files: {len(sm_files)}')
    for f in sm_files[:3]:
        print(f'  - {f.name}')

# Check new loaders
for fname in ['llm_usage_summary.json', 'pipeline_manifest.json', 'content_analysis.json', 'html_review_report.json']:
    fp = project_dir / fname
    if fp.exists():
        with open(fp) as f:
            data = json.load(f)
        print(f'{fname}: OK ({len(str(data))} chars)')
    else:
        print(f'{fname}: MISSING')
