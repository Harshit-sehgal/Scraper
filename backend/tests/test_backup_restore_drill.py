"""Backup and restore drill tests."""

import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest


def test_sqlite_backup_and_restore():
    """Verify SQLite backup can be restored."""
    # Create a temporary directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"
        backup_file = Path(tmpdir) / "test.db.backup"

        # Create a database with test data
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT
            )
        """)
        cursor.execute(
            "INSERT INTO jobs VALUES (?, ?, ?)",
            ("job_123", "test_job", "2026-06-22T00:00:00Z"),
        )
        conn.commit()

        # Backup the database
        backup_conn = sqlite3.connect(str(backup_file))
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()

        # Verify backup exists and is not empty
        assert backup_file.exists()
        assert backup_file.stat().st_size > 0, "Backup file is empty"

        # Restore from backup into a new file
        restored_file = Path(tmpdir) / "test_restored.db"
        shutil.copy(backup_file, restored_file)

        # Verify restored data
        restored_conn = sqlite3.connect(str(restored_file))
        cursor = restored_conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", ("job_123",))
        row = cursor.fetchone()
        restored_conn.close()

        assert row is not None, "Restored data not found"
        assert row[0] == "job_123"
        assert row[1] == "test_job"


def test_backup_file_integrity():
    """Verify backup file is readable and valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"
        backup_file = Path(tmpdir) / "test.db.backup"

        # Create and backup
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test (id INTEGER, data TEXT)")
        cursor.execute("INSERT INTO test VALUES (1, 'data1'), (2, 'data2')")
        conn.commit()

        backup_conn = sqlite3.connect(str(backup_file))
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()

        # Verify backup can be opened and read
        try:
            verify_conn = sqlite3.connect(str(backup_file))
            verify_cursor = verify_conn.cursor()
            verify_cursor.execute("SELECT COUNT(*) FROM test")
            count = verify_cursor.fetchone()[0]
            verify_conn.close()

            assert count == 2, f"Expected 2 rows, got {count}"
        except sqlite3.DatabaseError as e:
            pytest.fail(f"Backup file is corrupted: {e}")


def test_partial_restore_preserves_integrity():
    """Verify restore doesn't lose critical job data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"
        backup_file = Path(tmpdir) / "test.db.backup"

        # Create jobs table with multiple records
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                created_at TEXT
            )
        """)

        test_data = [
            ("job_1", "scrape_1", "completed", "2026-06-01"),
            ("job_2", "scrape_2", "failed", "2026-06-15"),
            ("job_3", "scrape_3", "pending", "2026-06-22"),
        ]

        for job_id, name, status, created_at in test_data:
            cursor.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?)",
                (job_id, name, status, created_at),
            )

        conn.commit()

        # Backup
        backup_conn = sqlite3.connect(str(backup_file))
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()

        # Restore and verify all records
        restored_file = Path(tmpdir) / "restored.db"
        shutil.copy(backup_file, restored_file)

        restored_conn = sqlite3.connect(str(restored_file))
        cursor = restored_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        count = cursor.fetchone()[0]

        assert count == 3, f"Expected 3 rows after restore, got {count}"

        # Verify each record is intact
        for job_id, expected_name, expected_status, _ in test_data:
            cursor.execute(
                "SELECT name, status FROM jobs WHERE id = ?",
                (job_id,),
            )
            row = cursor.fetchone()
            assert row is not None, f"Job {job_id} not found"
            assert row[0] == expected_name
            assert row[1] == expected_status

        restored_conn.close()
