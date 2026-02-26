"""
Script to slice Unnamed_Project_input.json into standalone service JSON files
based on the source_file field.
"""
import json
from pathlib import Path
from collections import defaultdict

# Read the large JSON file
input_file = Path(__file__).parent / "Unnamed_Project_input.json"
output_dir = Path(__file__).parent / "services"
output_dir.mkdir(exist_ok=True)

print(f"Reading {input_file}...")
with open(input_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Group requirements by source_file
requirements_by_source = defaultdict(list)
for req in data.get('requirements', []):
    source = req.get('source_file', 'unknown')
    requirements_by_source[source].append(req)

# Service name mapping (German -> English service names)
service_names = {
    'Integration_API_Gateway.md': 'api-gateway-service',
    'Benutzer_Rollenverwaltung.md': 'user-role-management-service',
    'Disposition.md': 'dispatch-planning-service',
    'POD_Management.md': 'pod-management-service',
    'Transport_Tracking.md': 'transport-tracking-service',
    'Abrechnung.md': 'billing-service',
    'Auftragsmanagement.md': 'order-management-service',
    'SERVICE_ARCHITECTURE.md': 'service-architecture',
    'Geschaeftspartner.md': 'business-partner-service',
    'FEATURES.md': 'features-overview',
    'README.md': 'project-overview'
}

# Create standalone service files
print(f"\nCreating service files in {output_dir}...")
summary = []

for source_file, requirements in sorted(requirements_by_source.items(),
                                         key=lambda x: -len(x[1])):
    service_name = service_names.get(source_file, source_file.replace('.md', '').lower())

    # Convert requirements to RE-System expected format
    imported_reqs = []
    for req in requirements:
        imported_reqs.append({
            "requirement_id": req.get('id', 'REQ-XXX'),
            "title": req.get('title', 'Untitled'),
            "description": req.get('description', ''),
            "type": "functional" if req.get('category') == 'functional' else (
                "non_functional" if req.get('category') in ['performance', 'security'] else "constraint"
            ),
            "priority": req.get('priority', 'should'),
            "source": req.get('source_file', source_file)
        })

    # Categorize requirements
    categories = defaultdict(int)
    priorities = defaultdict(int)
    for req in requirements:
        categories[req.get('category', 'unknown')] += 1
        priorities[req.get('priority', 'unknown')] += 1

    # Create RE-System compatible JSON structure
    service_data = {
        "Name": service_name,
        "Domain": "freight-forwarding",
        "Context": {
            "source_file": source_file,
            "requirement_count": len(requirements),
            "categories": dict(categories),
            "priorities": dict(priorities)
        },
        "Stakeholders": [
            {"name": "Dispatcher", "role": "primary_user"},
            {"name": "Transport Manager", "role": "stakeholder"},
            {"name": "System Admin", "role": "admin"}
        ],
        "Constraints": {
            "technical": ["FastAPI backend", "React frontend", "PostgreSQL database"],
            "business": ["German freight forwarding regulations", "GDPR compliance"]
        },
        "_imported_requirements": imported_reqs
    }

    # Write service file
    output_file = output_dir / f"{service_name}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(service_data, f, indent=2, ensure_ascii=False)

    summary.append({
        "service": service_name,
        "source": source_file,
        "requirements": len(requirements),
        "categories": dict(categories),
        "file": str(output_file)
    })
    print(f"  [OK] {service_name}.json ({len(requirements)} requirements)")

# Write summary file
summary_file = output_dir / "_service_summary.json"
with open(summary_file, 'w', encoding='utf-8') as f:
    json.dump({
        "total_services": len(summary),
        "total_requirements": sum(s["requirements"] for s in summary),
        "services": summary
    }, f, indent=2, ensure_ascii=False)

print(f"\n[OK] Created {len(summary)} service files")
print(f"[OK] Summary written to {summary_file}")
