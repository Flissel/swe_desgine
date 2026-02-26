"""Check what data the server sends for services, state machines, infra, tokens."""
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from requirements_engineer.dashboard.server import DashboardServer

server = DashboardServer.__new__(DashboardServer)
server._loaded_project = None
project_dir = Path('enterprise_output/whatsapp-messaging-service_20260211_025459')
data = server._load_folder_format(project_dir)

print("=" * 60)
print("=== SERVICES (architecture.services) ===")
arch = data.get('architecture', {})
services = arch.get('services', [])
print(f"Count: {len(services)}")
if services:
    s = services[0]
    print(f"Sample keys: {list(s.keys())}")
    print(f"Sample: {json.dumps(s, indent=2, default=str)[:500]}")

print("\n=== STATE MACHINES ===")
sms = data.get('state_machines', [])
print(f"Count: {len(sms)}")
if sms:
    sm = sms[0]
    print(f"Sample keys: {list(sm.keys())}")
    print(f"entity: {sm.get('entity')}")
    print(f"states count: {len(sm.get('states', []))}")
    print(f"transitions count: {len(sm.get('transitions', []))}")
    print(f"states sample: {sm.get('states', [])[:3]}")
    print(f"transitions sample: {json.dumps(sm.get('transitions', [])[:2], default=str)}")

print("\n=== INFRASTRUCTURE ===")
infra = data.get('infrastructure')
print(f"Type: {type(infra)}")
if infra:
    print(f"Keys: {list(infra.keys()) if isinstance(infra, dict) else 'not a dict'}")
    print(f"Preview: {json.dumps(infra, indent=2, default=str)[:500]}")
else:
    print("  MISSING or None!")
    # Check where it might be
    if 'architecture' in data:
        a = data['architecture']
        print(f"  architecture keys: {list(a.keys()) if isinstance(a, dict) else type(a)}")
        if 'infrastructure' in a:
            print(f"  architecture.infrastructure: {type(a['infrastructure'])}")
            print(f"    {json.dumps(a['infrastructure'], indent=2, default=str)[:500]}")

print("\n=== DESIGN TOKENS ===")
tokens = data.get('design_tokens')
print(f"Type: {type(tokens)}")
if tokens:
    print(f"Keys: {list(tokens.keys()) if isinstance(tokens, dict) else 'not a dict'}")
    print(f"Preview: {json.dumps(tokens, indent=2, default=str)[:500]}")
else:
    print("  MISSING or None!")
    # Check in ux_design
    ux = data.get('ux_design', {})
    if isinstance(ux, dict) and 'design_tokens' in ux:
        print(f"  Found in ux_design.design_tokens: {type(ux['design_tokens'])}")
        print(f"    {json.dumps(ux['design_tokens'], indent=2, default=str)[:500]}")
