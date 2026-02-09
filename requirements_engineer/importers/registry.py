"""
Importer Registry - Auto-detection and management of importers.

Provides a central registry for all available importers and
auto-detection based on file content.
"""

from typing import List, Type, Optional
import os


class ImporterRegistry:
    """
    Registry of available requirement importers.

    Provides:
    - Registration of new importers
    - Auto-detection of appropriate importer for a file
    - Listing of available importers
    """

    _importers: List[Type['BaseImporter']] = []

    @classmethod
    def register(cls, importer: Type['BaseImporter']) -> None:
        """
        Register a new importer.

        Args:
            importer: Importer class to register
        """
        if importer not in cls._importers:
            cls._importers.append(importer)
            print(f"  Registered importer: {importer.name}")

    @classmethod
    def unregister(cls, importer: Type['BaseImporter']) -> None:
        """
        Unregister an importer.

        Args:
            importer: Importer class to unregister
        """
        if importer in cls._importers:
            cls._importers.remove(importer)

    @classmethod
    def get_importer(cls, file_path: str) -> Optional['BaseImporter']:
        """
        Get the appropriate importer for a file.

        Tries each registered importer in order until one
        reports it can handle the file.

        Args:
            file_path: Path to the file to import

        Returns:
            Importer instance or None if no importer found
        """
        if not os.path.exists(file_path):
            print(f"  Warning: File not found: {file_path}")
            return None

        for importer_cls in cls._importers:
            try:
                if importer_cls.can_import(file_path):
                    return importer_cls()
            except Exception as e:
                # Skip this importer if it fails to check
                print(f"  Warning: {importer_cls.name} check failed: {e}")
                continue

        return None

    @classmethod
    def get_importer_by_name(cls, name: str) -> Optional[Type['BaseImporter']]:
        """
        Get an importer by its name.

        Args:
            name: Name of the importer

        Returns:
            Importer class or None if not found
        """
        for importer_cls in cls._importers:
            if importer_cls.name.lower() == name.lower():
                return importer_cls
        return None

    @classmethod
    def list_importers(cls) -> List[str]:
        """
        List all registered importers.

        Returns:
            List of importer names
        """
        return [imp.name for imp in cls._importers]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered importers."""
        cls._importers.clear()


# Delayed import to avoid circular imports
def _register_default_importers():
    """Register all default importers."""
    from .standard_importer import StandardImporter
    from .billing_spec_importer import BillingSpecImporter

    ImporterRegistry.register(StandardImporter)
    ImporterRegistry.register(BillingSpecImporter)

    # Register arch_team importer if available
    try:
        from .arch_team_importer import ArchTeamImporter
        ImporterRegistry.register(ArchTeamImporter)
    except ImportError as e:
        # arch_team not available - this is fine, it's optional
        pass


# Auto-register default importers when module is imported
try:
    _register_default_importers()
except ImportError as e:
    print(f"  Warning: Could not register default importers: {e}")
