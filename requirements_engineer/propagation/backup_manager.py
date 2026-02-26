"""
Backup Manager - Creates timestamped backups before any file modifications.

Ensures non-destructive changes with easy restore capability.
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import json

from .models import BackupInfo


class BackupManager:
    """
    Creates timestamped backups before any modifications.

    Backups are stored in: {project_path}/.backups/{filename}_{timestamp}.bak
    """

    def __init__(self, project_path: Path):
        """
        Initialize the backup manager.

        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path)
        self.backup_dir = self.project_path / ".backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Index file for tracking backups
        self.index_file = self.backup_dir / "backup_index.json"
        self._load_index()

    def _load_index(self):
        """Load the backup index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._index = {"backups": []}
        else:
            self._index = {"backups": []}

    def _save_index(self):
        """Save the backup index to disk."""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2, ensure_ascii=False)

    def create_backup(self, file_path: Path) -> Optional[BackupInfo]:
        """
        Create a backup of the file before modification.

        Args:
            file_path: Path to the file to backup

        Returns:
            BackupInfo if successful, None if file doesn't exist
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return None

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}.bak"

        # Create subdirectory structure mirroring original path
        try:
            relative_path = file_path.relative_to(self.project_path)
            backup_subdir = self.backup_dir / relative_path.parent
        except ValueError:
            # File is outside project path
            backup_subdir = self.backup_dir / "external"

        backup_subdir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_subdir / backup_name

        # Copy the file
        shutil.copy2(file_path, backup_path)

        # Get file size
        size_bytes = backup_path.stat().st_size

        # Create backup info
        backup_info = BackupInfo(
            original_path=str(file_path),
            backup_path=str(backup_path),
            created_at=datetime.now().isoformat(),
            size_bytes=size_bytes
        )

        # Add to index
        self._index["backups"].append(backup_info.to_dict())
        self._save_index()

        return backup_info

    def restore_backup(self, backup_path: Path, original_path: Optional[Path] = None) -> bool:
        """
        Restore a file from backup.

        Args:
            backup_path: Path to the backup file
            original_path: Path to restore to (if None, uses original location from index)

        Returns:
            True if successful, False otherwise
        """
        backup_path = Path(backup_path)

        if not backup_path.exists():
            return False

        # Find original path from index if not provided
        if original_path is None:
            for backup in self._index["backups"]:
                if backup["backup_path"] == str(backup_path):
                    original_path = Path(backup["original_path"])
                    break

            if original_path is None:
                return False

        # Backup the current file before restoring (safety)
        if original_path.exists():
            self.create_backup(original_path)

        # Restore the file
        shutil.copy2(backup_path, original_path)
        return True

    def list_backups(self, file_path: Optional[Path] = None) -> List[BackupInfo]:
        """
        List all backups, optionally filtered by original file path.

        Args:
            file_path: If provided, only list backups for this file

        Returns:
            List of BackupInfo objects
        """
        backups = []

        for backup_data in self._index["backups"]:
            if file_path is None or backup_data["original_path"] == str(file_path):
                backup_info = BackupInfo(
                    original_path=backup_data["original_path"],
                    backup_path=backup_data["backup_path"],
                    created_at=backup_data["created_at"],
                    size_bytes=backup_data.get("size_bytes", 0)
                )

                # Only include if backup file still exists
                if Path(backup_info.backup_path).exists():
                    backups.append(backup_info)

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x.created_at, reverse=True)
        return backups

    def get_latest_backup(self, file_path: Path) -> Optional[BackupInfo]:
        """
        Get the most recent backup for a file.

        Args:
            file_path: Path to the original file

        Returns:
            BackupInfo if found, None otherwise
        """
        backups = self.list_backups(file_path)
        return backups[0] if backups else None

    def cleanup_old_backups(self, max_age_days: int = 7, max_backups_per_file: int = 10):
        """
        Remove backups older than threshold or exceeding count limit.

        Args:
            max_age_days: Maximum age of backups to keep
            max_backups_per_file: Maximum number of backups per file
        """
        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        # Group backups by original file
        backups_by_file = {}
        for backup_data in self._index["backups"]:
            original = backup_data["original_path"]
            if original not in backups_by_file:
                backups_by_file[original] = []
            backups_by_file[original].append(backup_data)

        # Process each file's backups
        new_backups = []
        for original, file_backups in backups_by_file.items():
            # Sort by creation time, newest first
            file_backups.sort(key=lambda x: x["created_at"], reverse=True)

            kept = 0
            for backup_data in file_backups:
                backup_path = Path(backup_data["backup_path"])
                created_at = datetime.fromisoformat(backup_data["created_at"])

                # Check if should be removed
                should_remove = (
                    created_at < cutoff_date or
                    kept >= max_backups_per_file
                )

                if should_remove:
                    # Delete the backup file
                    if backup_path.exists():
                        try:
                            backup_path.unlink()
                        except OSError:
                            pass
                else:
                    new_backups.append(backup_data)
                    kept += 1

        # Update index
        self._index["backups"] = new_backups
        self._save_index()

        # Clean up empty directories
        self._cleanup_empty_dirs()

    def _cleanup_empty_dirs(self):
        """Remove empty subdirectories in backup folder."""
        for dirpath, dirnames, filenames in os.walk(self.backup_dir, topdown=False):
            dir_path = Path(dirpath)
            if dir_path != self.backup_dir and not any(dir_path.iterdir()):
                try:
                    dir_path.rmdir()
                except OSError:
                    pass

    def get_total_backup_size(self) -> int:
        """Get total size of all backups in bytes."""
        total = 0
        for backup_data in self._index["backups"]:
            backup_path = Path(backup_data["backup_path"])
            if backup_path.exists():
                total += backup_path.stat().st_size
        return total
