"""
Tests for Phase 2: Bookmarks API, Saved page, isolation, and removed-file exclusion.
"""

import os
import tempfile
import pytest

from app import create_app
from db import get_db


@pytest.fixture
def app():
    """Create isolated test app with users and files across two universities."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'bookmark-test-secret',
        'ADMIN_EMAIL': 'admin@xyz.edu',
        'ALLOWED_DOMAINS': {
            'xyz.edu': 'XYZ University',
            'abc.edu': 'ABC College',
        },
    })
    with test_app.app_context():
        db = get_db()
        from werkzeug.security import generate_password_hash
        pwd = generate_password_hash('password123')
        xyz_id = db.execute("SELECT id FROM universities WHERE domain = 'xyz.edu'").fetchone()['id']
        abc_id = db.execute("SELECT id FROM universities WHERE domain = 'abc.edu'").fetchone()['id']
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('alice@xyz.edu', 'alice', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('david@abc.edu', 'david', pwd, abc_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 1)",
            ('admin@xyz.edu', 'admin_xyz', pwd, xyz_id)
        )
        for uid in (1, 2, 3):
            db.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility) "
            "VALUES (1, ?, 'XYZ Calculus', 'Math', 1, 'Summaries', 'f1.pdf', 'f1.pdf', 100, 'active', 'university')",
            (xyz_id,)
        )
        db.execute(
            "INSERT INTO files (uploader_id, university_id, title, subject, semester, type, stored_name, original_name, size, status, visibility) "
            "VALUES (2, ?, 'ABC Biology', 'Biology', 1, 'Summaries', 'f2.pdf', 'f2.pdf', 100, 'active', 'university')",
            (abc_id,)
        )
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_bookmark_toggle_and_saved_page(app):
    """Toggle bookmark via API, verify Saved page, and verify removed files are excluded."""
    client = app.test_client()
    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})

    # Toggle on
    res = client.post('/api/bookmark/1')
    assert res.status_code == 200
    data = res.get_json()
    assert data == {'bookmarked': True, 'count': 1}

    # Saved page shows XYZ Calculus
    saved_res = client.get('/saved')
    assert saved_res.status_code == 200
    assert b'XYZ Calculus' in saved_res.data

    # Cannot bookmark another university's file
    res_other = client.post('/api/bookmark/2')
    assert res_other.status_code == 404

    # Toggle off
    res2 = client.post('/api/bookmark/1')
    assert res2.status_code == 200
    assert res2.get_json() == {'bookmarked': False, 'count': 0}

    # Re-add then admin removes file -> excluded from Saved
    client.post('/api/bookmark/1')
    client.post('/logout')
    client.post('/login', data={'email': 'admin@xyz.edu', 'password': 'password123'})
    client.post('/admin/file/1/remove')
    client.post('/logout')

    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})
    saved_after = client.get('/saved')
    assert b'XYZ Calculus' not in saved_after.data
    assert b'No saved materials yet' in saved_after.data
