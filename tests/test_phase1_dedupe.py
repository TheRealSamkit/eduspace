"""
Tests for Phase 1: SHA-256 duplicate detection, cross-university privacy, and removed-file blocklist.
"""

import io
import os
import tempfile
import pytest

from app import create_app
from db import get_db


@pytest.fixture
def app():
    """Create isolated test app with two partner universities."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    upload_dir = tempfile.mkdtemp()
    test_app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'UPLOAD_FOLDER': upload_dir,
        'SECRET_KEY': 'dedupe-test-secret',
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
            ('bob@xyz.edu', 'bob', pwd, xyz_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 0)",
            ('david@abc.edu', 'david', pwd, abc_id)
        )
        db.execute(
            "INSERT INTO users (email, username, password_hash, university_id, credits, is_admin) VALUES (?, ?, ?, ?, 20, 1)",
            ('admin@xyz.edu', 'admin_xyz', pwd, xyz_id)
        )
        for uid in (1, 2, 3, 4):
            db.execute("INSERT INTO consents (user_id) VALUES (?)", (uid,))
        db.commit()
    yield test_app
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


def _upload(client, content, filename='notes.pdf', title='Test Notes'):
    return client.post(
        '/upload',
        data={
            'title': title,
            'subject': 'Computer Science',
            'semester': '1',
            'type': 'Lecture Notes',
            'description': 'Test description',
            'confirm_copyright': 'on',
            'file': (io.BytesIO(content), filename),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )


def test_duplicate_blocked_same_university(app):
    """Exact duplicate in the same university is blocked with no credit or ledger row."""
    client = app.test_client()
    payload = b'%PDF-1.4\nunique-lecture-bytes-1'

    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})
    res1 = _upload(client, payload, 'first.pdf', 'First Upload')
    assert res1.status_code == 200
    assert b'earned 10 credits' in res1.data

    client.post('/logout')
    client.post('/login', data={'email': 'bob@xyz.edu', 'password': 'password123'})
    res2 = _upload(client, payload, 'second.pdf', 'Second Upload')
    assert res2.status_code == 200
    assert b'This exact file is already in the library' in res2.data
    assert b'/file/1' in res2.data

    with app.app_context():
        db = get_db()
        bob = db.execute("SELECT credits FROM users WHERE email = 'bob@xyz.edu'").fetchone()
        assert bob['credits'] == 20
        bob_ledger = db.execute(
            "SELECT COUNT(*) FROM ledger WHERE user_id = (SELECT id FROM users WHERE email = 'bob@xyz.edu')"
        ).fetchone()[0]
        assert bob_ledger == 0
        evt = db.execute("SELECT * FROM events WHERE event_type = 'duplicate_blocked'").fetchone()
        assert evt is not None


def test_cross_university_private_match_allowed(app):
    """Identical file uploaded privately to another university must succeed without leaking."""
    client = app.test_client()
    payload = b'%PDF-1.4\ncross-uni-bytes'

    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})
    res1 = _upload(client, payload, 'xyz.pdf', 'XYZ Copy')
    assert b'earned 10 credits' in res1.data

    client.post('/logout')
    client.post('/login', data={'email': 'david@abc.edu', 'password': 'password123'})
    res2 = _upload(client, payload, 'abc.pdf', 'ABC Copy')
    assert b'earned 10 credits' in res2.data
    assert b'already in the library' not in res2.data


def test_removed_file_hash_blocklisted(app):
    """Re-uploading a file removed by moderators in the same scope is blocked."""
    client = app.test_client()
    payload = b'%PDF-1.4\nremoved-by-mod-bytes'

    client.post('/login', data={'email': 'alice@xyz.edu', 'password': 'password123'})
    _upload(client, payload, 'bad.pdf', 'Bad File')

    client.post('/logout')
    client.post('/login', data={'email': 'admin@xyz.edu', 'password': 'password123'})
    client.post('/admin/file/1/remove', follow_redirects=True)

    client.post('/logout')
    client.post('/login', data={'email': 'bob@xyz.edu', 'password': 'password123'})
    res = _upload(client, payload, 'reupload.pdf', 'Reupload')
    assert b'removed by moderators' in res.data
