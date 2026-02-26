"""Verify all new node types have correct data for frontend rendering."""
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from requirements_engineer.dashboard.server import DashboardServer

server = DashboardServer.__new__(DashboardServer)
server._loaded_project = None
project_dir = Path('enterprise_output/whatsapp-messaging-service_20260211_025459')
data = server._load_folder_format(project_dir)

print("=" * 60)
print("NODE TYPE RENDERING VERIFICATION")
print("=" * 60)

errors = []

# 1. Services
print("\n[SERVICE NODES]")
arch = data.get('architecture', {})
services = arch.get('services', [])
print(f"  Count: {len(services)}")
if services:
    s = services[0]
    fields = {'name': s.get('name'), 'type': s.get('type'), 'technology': s.get('technology'),
              'id': s.get('id'), 'responsibilities': len(s.get('responsibilities', [])),
              'dependencies': len(s.get('dependencies', []))}
    print(f"  Sample: {fields}")
    if not s.get('id'):
        errors.append("Service missing 'id'")
    if not s.get('name'):
        errors.append("Service missing 'name'")
else:
    errors.append("No services found")

# 2. State Machines
print("\n[STATE MACHINE NODES]")
sms = data.get('state_machines', [])
print(f"  Count: {len(sms)}")
if sms:
    sm = sms[0]
    fields = {'entity': sm.get('entity'), 'states': len(sm.get('states', [])),
              'transitions': len(sm.get('transitions', [])),
              'initial_state': sm.get('initial_state'),
              'mermaid_code': bool(sm.get('mermaid_code'))}
    print(f"  Sample: {fields}")
    if not sm.get('entity'):
        errors.append("State machine missing 'entity'")
else:
    errors.append("No state machines found")

# 3. Infrastructure
print("\n[INFRASTRUCTURE NODE]")
infra = data.get('infrastructure')
if infra:
    fields = {'architecture_style': infra.get('architecture_style'),
              'has_dockerfile': infra.get('has_dockerfile'),
              'has_k8s': infra.get('has_k8s'),
              'has_ci': infra.get('has_ci'),
              'service_count': infra.get('service_count'),
              'services': len(infra.get('services', []))}
    print(f"  Data: {fields}")
    # Verify nodeFactory expects the right keys
    style = infra.get('architecture_style', '')
    svc_count = infra.get('service_count', 0)
    flags = []
    if infra.get('has_dockerfile'): flags.append('Docker')
    if infra.get('has_k8s'): flags.append('K8s')
    if infra.get('has_ci'): flags.append('CI/CD')
    summary = ' | '.join(filter(None, [style, f"{svc_count} services" if svc_count else '', '+'.join(flags) if flags else '']))
    print(f"  Rendered summary: '{summary}'")
    if summary == 'N/A' or not summary:
        errors.append("Infrastructure would render as N/A")
else:
    errors.append("No infrastructure data found")

# 4. Design Tokens
print("\n[DESIGN TOKENS NODE]")
tokens = data.get('design_tokens')
if tokens:
    fields = {k: len(v) if isinstance(v, dict) else type(v).__name__
              for k, v in tokens.items()}
    print(f"  Data: {fields}")
    color_count = len(tokens.get('colors', {}))
    typo_count = len(tokens.get('typography', {}))
    print(f"  Rendered: '{color_count} colors | {typo_count} typography'")
    if color_count == 0 and typo_count == 0:
        errors.append("Design tokens has no colors or typography")
else:
    errors.append("No design_tokens data found")

# 5. API Packages
print("\n[API PACKAGE NODES]")
pkgs = data.get('api_packages', {})
print(f"  Count: {len(pkgs)}")
if pkgs:
    sample = list(pkgs.items())[0]
    tag, pkg = sample
    print(f"  Sample: tag={tag}, endpoints={len(pkg['endpoints'])}, methods={pkg['method_counts']}")
else:
    errors.append("No api_packages found")

# 6. Task Groups
print("\n[TASK GROUP NODES]")
tasks = data.get('tasks', {})
print(f"  Type: {type(tasks).__name__}, Groups: {len(tasks) if isinstance(tasks, dict) else 0}")
if isinstance(tasks, dict):
    for fid in list(tasks.keys())[:3]:
        tlist = tasks[fid]
        if isinstance(tlist, list):
            total_h = sum(t.get('estimated_hours', 0) for t in tlist)
            print(f"    {fid}: {len(tlist)} tasks, {total_h}h")
else:
    errors.append("Tasks is not a dict (cannot group by feature)")

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL CHECKS PASSED - All 6 new node types have correct data")
print("=" * 60)
