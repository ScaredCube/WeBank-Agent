"""Synthetic migration/rollback rehearsal stays isolated from all configured databases."""
from pathlib import Path

import pytest

from scripts.rehearse_chat_schema import exercise_migration, restore_to_new_file


def test_synthetic_upgrade_and_rollback_are_identical(tmp_path):
    report = exercise_migration(tmp_path)
    assert report["result"] == "PASS"
    assert report["production_database_modified"] is False
    assert "rollback_to_separate_file" in report["verified"]


def test_restore_will_not_overwrite_an_existing_destination(tmp_path):
    backup = tmp_path / "backup.sqlite"
    backup.write_bytes(b"synthetic")
    destination = tmp_path / "existing.sqlite"
    destination.write_bytes(b"must-not-change")
    with pytest.raises(FileExistsError):
        restore_to_new_file(backup, destination)
    assert destination.read_bytes() == b"must-not-change"


def test_restore_requires_existing_backup(tmp_path):
    with pytest.raises(FileNotFoundError):
        restore_to_new_file(tmp_path / "missing.sqlite", tmp_path / "new.sqlite")
    assert not (tmp_path / "new.sqlite").exists()
