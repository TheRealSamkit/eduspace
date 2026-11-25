"""
Tests for Phase 0: Foundation, schema migrations, and centralised visibility matrix.
"""

import os
import sqlite3
import tempfile
import pytest

from app import create_app
from db import init_db
from eduspace.services.visibility import (
    can_view_file,
    file_visibility_where,
    can_view_request,
    is_public_member,
)


def test_visibility_matrix():
    """Verify can_view_file across all user roles, file visibilities, and statuses."""
    guest = None
    xyz_student = {'id': 10, 'university_id': 1, 'university_kind': 'partner', 'is_admin': 0}
    abc_student = {'id': 20, 'university_id': 2, 'university_kind': 'partner', 'is_admin': 0}
    public_user = {'id': 30, 'university_id': 3, 'university_kind': 'public', 'is_admin': 0}
    xyz_admin = {'id': 40, 'university_id': 1, 'university_kind': 'partner', 'is_admin': 1}
    uploader_xyz = {'id': 11, 'university_id': 1, 'university_kind': 'partner', 'is_admin': 0}
    uploader_pub = {'id': 31, 'university_id': 3, 'university_kind': 'public', 'is_admin': 0}

    priv_active = {'id': 1, 'uploader_id': 11, 'university_id': 1, 'visibility': 'university', 'status': 'active'}
    priv_hidden = {'id': 2, 'uploader_id': 11, 'university_id': 1, 'visibility': 'university', 'status': 'hidden'}
    priv_removed = {'id': 3, 'uploader_id': 11, 'university_id': 1, 'visibility': 'university', 'status': 'removed'}

    pub_active = {'id': 4, 'uploader_id': 31, 'university_id': 3, 'visibility': 'public', 'status': 'active'}
    pub_hidden = {'id': 5, 'uploader_id': 31, 'university_id': 3, 'visibility': 'public', 'status': 'hidden'}
    pub_removed = {'id': 6, 'uploader_id': 31, 'university_id': 3, 'visibility': 'public', 'status': 'removed'}

    assert is_public_member(public_user) is True
    assert is_public_member(xyz_student) is False
    assert is_public_member(guest) is False

    # Private active
    assert can_view_file(guest, priv_active) is False
    assert can_view_file(xyz_student, priv_active) is True
    assert can_view_file(abc_student, priv_active) is False
    assert can_view_file(public_user, priv_active) is False
    assert can_view_file(xyz_admin, priv_active) is True

    # Private hidden / removed
    for hidden_or_removed in (priv_hidden, priv_removed):
        assert can_view_file(guest, hidden_or_removed) is False
        assert can_view_file(xyz_student, hidden_or_removed) is False
        assert can_view_file(abc_student, hidden_or_removed) is False
        assert can_view_file(public_user, hidden_or_removed) is False
        assert can_view_file(uploader_xyz, hidden_or_removed) is True
        assert can_view_file(xyz_admin, hidden_or_removed) is True

    # Public active
    assert can_view_file(guest, pub_active) is True
    assert can_view_file(xyz_student, pub_active) is True
    assert can_view_file(abc_student, pub_active) is True
    assert can_view_file(public_user, pub_active) is True
    assert can_view_file(xyz_admin, pub_active) is True

    # Public hidden / removed
    for hidden_or_removed in (pub_hidden, pub_removed):
        assert can_view_file(guest, hidden_or_removed) is False
        assert can_view_file(xyz_student, hidden_or_removed) is False
        assert can_view_file(abc_student, hidden_or_removed) is False
        assert can_view_file(public_user, hidden_or_removed) is False
        assert can_view_file(uploader_pub, hidden_or_removed) is True
        assert can_view_file(xyz_admin, hidden_or_removed) is True

    # Query builder checks
    sql, params = file_visibility_where(public_user, scope='university')
    assert sql == "1 = 0" and params == []
    sql, params = file_visibility_where(xyz_student, scope='university')
    assert "f.university_id = ?" in sql and params == [1]
    sql, params = file_visibility_where(guest, scope='public')
    assert "f.visibility = 'public'" in sql and params == []


def test_request_visibility_matrix():
    """Verify can_view_request enforces institutional isolation and public member boundaries."""
    xyz_student = {'id': 10, 'university_id': 1, 'university_kind': 'partner'}
    abc_student = {'id': 20, 'university_id': 2, 'university_kind': 'partner'}
    public_user = {'id': 30, 'university_id': 3, 'university_kind': 'public'}

    priv_req = {'id': 1, 'university_id': 1, 'visibility': 'university'}
    pub_req = {'id': 2, 'university_id': 3, 'visibility': 'public'}

    assert can_view_request(None, pub_req) is False
    assert can_view_request(xyz_student, priv_req) is True
    assert can_view_request(abc_student, priv_req) is False
    assert can_view_request(public_user, priv_req) is False
    assert can_view_request(xyz_student, pub_req) is True
    assert can_view_request(abc_student, pub_req) is True
    assert can_view_request(public_user, pub_req) is True


def test_old_schema_migration_preserves_data():
    """Verify init_db safely upgrades an old-schema SQLite DB without losing rows."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    os.close(db_fd)

    try:
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE universities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                domain TEXT UNIQUE NOT NULL
            );
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                university_id INTEGER NOT NULL REFERENCES universities(id),
                credits INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uploader_id INTEGER NOT NULL REFERENCES users(id),
                university_id INTEGER NOT NULL REFERENCES universities(id),
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                semester INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                stored_name TEXT NOT NULL,
                original_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'removed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL CHECK(reason IN ('signup', 'upload', 'download', 'reversal')),
                file_id INTEGER REFERENCES files(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO universities (name, domain) VALUES ('XYZ University', 'xyz.edu');
            INSERT INTO users (email, username, password_hash, university_id, credits) VALUES ('a@xyz.edu', 'alice', 'hash', 1, 30);
            INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size)
                VALUES (1, 1, 'Old Notes', 'CS', 1, 'Summaries', 'old.pdf', 'old.pdf', 123);
            INSERT INTO ledger (user_id, amount, reason, file_id) VALUES (1, 10, 'upload', 1);
        """)
        conn.close()

        test_file_path = os.path.join(upload_dir, 'old.pdf')
        with open(test_file_path, 'wb') as f:
            f.write(b'%PDF-1.4\nold content')

        app = create_app({
            'TESTING': True,
            'DATABASE': db_path,
            'UPLOAD_FOLDER': upload_dir,
        })
        assert app is not None

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        file_row = conn.execute("SELECT * FROM files WHERE id = 1").fetchone()
        assert file_row['title'] == 'Old Notes'
        assert file_row['visibility'] == 'university'
        assert file_row['content_hash'] is not None

        # Verify new CHECK constraints work
        conn.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility) "
            "VALUES (1, 1, 'Hidden', 'CS', 1, 'Summaries', 'h.pdf', 'h.pdf', 10, 'hidden', 'public')"
        )
        conn.execute(
            "INSERT INTO ledger (user_id, amount, reason) VALUES (1, 15, 'request_reward')"
        )
        pub_uni = conn.execute("SELECT * FROM universities WHERE kind = 'public'").fetchone()
        assert pub_uni is not None
        assert pub_uni['domain'] == 'eduspace.public'
        conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
