"""Test script for the Universal Requirements Importer."""

import asyncio
import sys
sys.path.insert(0, '.')

from requirements_engineer.importers.registry import ImporterRegistry
from requirements_engineer.importers.billing_spec_importer import BillingSpecImporter


async def main():
    test_path = r'C:\Users\User\Desktop\Coding_engine\Data\all_services\abrechnung-service\docs\requirements\autonomous_billing_spec.json'

    print("=" * 60)
    print("Universal Requirements Importer - Test")
    print("=" * 60)

    print("\n1. Testing importer detection...")
    importer = ImporterRegistry.get_importer(test_path)
    if importer:
        print(f"   [OK] Found importer: {importer.name}")
    else:
        print("   [FAIL] No importer found")
        return

    print("\n2. Testing can_import...")
    print(f"   BillingSpecImporter.can_import: {BillingSpecImporter.can_import(test_path)}")

    print("\n3. Running import...")
    result = await importer.import_requirements(test_path)

    print(f"\n4. Import Results:")
    print(f"   [OK] Imported {result.get_requirement_count()} requirements")
    print(f"   Project: {result.project_name}")
    print(f"   Domain: {result.domain}")
    print(f"   Source Format: {result.source_format}")

    print("\n   Requirements by type:")
    by_type = result.get_requirements_by_type()
    for t, reqs in by_type.items():
        print(f"     - {t}: {len(reqs)} requirements")

    print("\n   First 5 requirements:")
    for req in result.requirements[:5]:
        title = req.title[:50] if req.title else "Untitled"
        print(f"     * {req.requirement_id}: {title}...")

    print("\n   Metadata keys:", list(result.metadata.keys()))

    print("\n5. Converting to standard format...")
    standard = result.to_standard_format()
    print(f"   [OK] Standard format keys: {list(standard.keys())}")

    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
